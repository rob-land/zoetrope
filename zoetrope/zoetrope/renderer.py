"""moderngl stereo renderer: draws the floating panels + a floor grid, once per eye.

Renders into whatever framebuffer the window provides, using the per-eye viewports and
view/projection matrices from `stereo`. For side-by-side (SBS) panel content the correct
half of the texture is sampled per eye; for a stereo "pair" the correct eye texture is
chosen. moderngl / numpy are imported lazily so the rest of the package stays importable.
"""
from __future__ import annotations

import struct

from .scene import Panel
from .stereo import EyeMatrices

# Column-major mat4 -> bytes for a moderngl mat4 uniform.
def _m4(mat) -> bytes:
    return struct.pack("16f", *mat)


PANEL_VS = """
#version 330
uniform mat4 mvp;
uniform mat4 model;
uniform vec2 uv_offset;
uniform vec2 uv_scale;
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
out vec3 v_world;
void main() {
    v_uv = uv_offset + in_uv * uv_scale;
    v_world = (model * vec4(in_pos, 0.0, 1.0)).xyz;
    gl_Position = mvp * vec4(in_pos, 0.0, 1.0);
}
"""

PANEL_FS = """
#version 330
uniform sampler2D tex;
uniform float selected;   // 1.0 if this panel is focused
uniform float border;     // border half-width in uv units
uniform float feather;    // edge fade half-width in uv units (0 = off)
uniform float arc_limit;  // slab half-arc (deg); cards fade at the rim
uniform float arc_fade;   // fade band width (deg)
in vec2 v_uv;
in vec3 v_world;
out vec4 frag;
void main() {
    vec4 c = texture(tex, v_uv);
    // Clip at the slab's rim: a peeking card (one past the scroll
    // window) fades out over the last few degrees instead of poking
    // past the panel (doc 17 §2 wants the next card peeking ~25%).
    float az = degrees(atan(v_world.x, -v_world.z));
    c.a *= 1.0 - smoothstep(arc_limit - arc_fade, arc_limit, abs(az));
    // Feathered frame: soften the panel edges so stereo content doesn't
    // present a hard stereo-window violation (doc 17 §5).
    if (feather > 0.0) {
        vec2 fd = min(v_uv, 1.0 - v_uv);
        c.a *= smoothstep(0.0, feather, min(fd.x, fd.y));
    }
    // Accent border when selected; scaled by the card's alpha so it hugs the
    // rounded silhouette instead of drawing a square frame over the corners.
    vec2 d = min(v_uv, 1.0 - v_uv);
    float edge = 1.0 - smoothstep(border * 0.6, border * 1.6, min(d.x, d.y));
    vec3 accent = vec3(0.208, 0.518, 0.894);   // suite token color.accent #3584e4
    frag = mix(c, vec4(accent, c.a), edge * selected * c.a);
}
"""

BACKDROP_VS = """
#version 330
uniform mat4 mvp;
in vec3 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = mvp * vec4(in_pos, 1.0);
}
"""

BACKDROP_FS = """
#version 330
uniform vec2 size_m;      // slab (arc-length, height) in meters
in vec2 v_uv;
out vec4 frag;
void main() {
    // Rounded-rect SDF in meters so the corner radius is physical, not
    // stretched by the slab's aspect (doc 17 §2b).
    float corner = 0.06;
    vec2 p = (v_uv - 0.5) * size_m;
    vec2 q = abs(p) - (0.5 * size_m - corner);
    float sdf = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - corner;
    // Glass fill (token color.glass-fill), top-lit like the cards, cut
    // off outside the rounded silhouette with a soft edge.
    float inside = 1.0 - smoothstep(-0.004, 0.004, sdf);
    float fill = (0.13 - 0.05 * v_uv.y) * inside;
    // Glass stroke hugging the silhouette (token color.glass-stroke).
    float stroke = (1.0 - smoothstep(0.0015, 0.006, abs(sdf))) * 0.35;
    frag = vec4(vec3(1.0), fill + stroke);
}
"""

CURSOR_FS = """
#version 330
in vec2 v_uv;
out vec4 frag;
void main() {
    // Soft glowing dot: bright core, cyan halo.
    float r = length(v_uv - 0.5) * 2.0;
    float halo = 1.0 - smoothstep(0.35, 1.0, r);
    float core = 1.0 - smoothstep(0.0, 0.35, r);
    vec3 col = mix(vec3(0.20, 0.85, 0.95), vec3(1.0), core);
    frag = vec4(col, halo * 0.9);
}
"""

GRID_VS = """
#version 330
uniform mat4 mvp;
uniform mat4 model;
in vec2 in_pos;
out vec3 v_world;
void main() {
    vec4 w = model * vec4(in_pos, 0.0, 1.0);
    v_world = w.xyz;
    gl_Position = mvp * vec4(in_pos, 0.0, 1.0);
}
"""

GRID_FS = """
#version 330
in vec3 v_world;
out vec4 frag;
void main() {
    vec2 g = abs(fract(v_world.xz * 2.0 - 0.5) - 0.5) / fwidth(v_world.xz * 2.0);
    float line = min(min(g.x, g.y), 1.0);
    float glow = 1.0 - line;
    float fade = clamp(1.0 - length(v_world.xz) / 6.0, 0.0, 1.0);
    vec3 col = mix(vec3(0.03, 0.05, 0.08), vec3(0.10, 0.35, 0.45), glow) * fade;
    frag = vec4(col, 0.85);
}
"""

# Unit quad in XY, centered, UV top-left origin (v flipped so images are upright).
_QUAD = [
    # x, y, u, v
    -0.5, -0.5, 0.0, 1.0,
     0.5, -0.5, 1.0, 1.0,
     0.5,  0.5, 1.0, 0.0,
    -0.5, -0.5, 0.0, 1.0,
     0.5,  0.5, 1.0, 0.0,
    -0.5,  0.5, 0.0, 0.0,
]

# Positions only (for the grid program, which has no `in_uv`).
_QUAD_POS = [
    -0.5, -0.5,  0.5, -0.5,  0.5, 0.5,
    -0.5, -0.5,  0.5,  0.5, -0.5, 0.5,
]


class StereoRenderer:
    def __init__(self, ctx):
        import moderngl  # lazy
        self.ctx = ctx
        self.moderngl = moderngl
        self.panel_prog = ctx.program(vertex_shader=PANEL_VS, fragment_shader=PANEL_FS)
        self.grid_prog = ctx.program(vertex_shader=GRID_VS, fragment_shader=GRID_FS)
        vbo = ctx.buffer(struct.pack(f"{len(_QUAD)}f", *_QUAD))
        self.panel_vao = ctx.vertex_array(
            self.panel_prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        # The grid shader only has `in_pos` (GLSL drops the unused `in_uv`), so bind a
        # positions-only buffer rather than naming an attribute moderngl can't resolve.
        pos_vbo = ctx.buffer(struct.pack(f"{len(_QUAD_POS)}f", *_QUAD_POS))
        self.grid_vao = ctx.vertex_array(self.grid_prog, [(pos_vbo, "2f", "in_pos")])
        self.backdrop_prog = ctx.program(vertex_shader=BACKDROP_VS,
                                         fragment_shader=BACKDROP_FS)
        self._backdrop_key = None
        self._backdrop_vbo = None
        self._backdrop_vao = None
        self.cursor_prog = ctx.program(vertex_shader=PANEL_VS, fragment_shader=CURSOR_FS)
        self.cursor_vao = ctx.vertex_array(
            self.cursor_prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        self.cursor_prog["uv_offset"].value = (0.0, 0.0)
        self.cursor_prog["uv_scale"].value = (1.0, 1.0)
        # Focus-ring width in card-UV units. 0.015 read as a hairline on
        # the glasses (hardware feedback 2026-07-31) — doubled, and drawn
        # at full accent opacity.
        self.panel_prog["border"].value = 0.03
        ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def _eye_texture(self, panel: Panel, eye_index: int):
        """Return (texture, uv_offset, uv_scale) for this eye. eye_index: 0=left, 1=right."""
        if panel.stereo_mode == "sbs" and panel.texture is not None:
            off = (0.0, 0.0) if eye_index == 0 else (0.5, 0.0)
            return panel.texture, off, (0.5, 1.0)
        if panel.stereo_mode == "pair":
            tex = panel.texture if eye_index == 0 else (panel.texture_right or panel.texture)
            return tex, (0.0, 0.0), (1.0, 1.0)
        return panel.texture, (0.0, 0.0), (1.0, 1.0)

    def _ensure_backdrop(self, backdrop) -> bool:
        """Upload the slab mesh when it changes (keyed by revision);
        True when there is a slab to draw."""
        if backdrop is None:
            return False
        key, verts, size_m, _half_arc = backdrop
        if key != self._backdrop_key:
            if self._backdrop_vao is not None:
                self._backdrop_vao.release()
                self._backdrop_vbo.release()
            self._backdrop_vbo = self.ctx.buffer(
                struct.pack(f"{len(verts)}f", *verts))
            self._backdrop_vao = self.ctx.vertex_array(
                self.backdrop_prog, [(self._backdrop_vbo, "3f 2f",
                                      "in_pos", "in_uv")])
            self._backdrop_key = key
        self.backdrop_prog["size_m"].value = size_m
        return True

    def render(self, fb_size, panels_models, eyes: tuple[EyeMatrices, EyeMatrices],
               floor_model, selected_id: str | None, target=None, cursor=None,
               void_theater: bool = False, backdrop=None):
        """cursor: optional (yaw_deg, pitch_deg) of the controller ray; drawn as a
        glowing dot on the panel cylinder. void_theater blanks everything but
        the panels (pure black on the additive display = nothing drawn) for
        cinema purity (doc 17 §5). backdrop: optional (key, vertices,
        (w_m, h_m)) dashboard slab from Shell.backdrop(), drawn behind
        the rails."""
        ctx = self.ctx
        fbo = target if target is not None else ctx.screen
        fbo.use()
        if void_theater:
            ctx.clear(0.0, 0.0, 0.0, 1.0)
        else:
            ctx.clear(0.02, 0.03, 0.05, 1.0)
        draw_backdrop = not void_theater and self._ensure_backdrop(backdrop)
        if draw_backdrop:
            # Cards clip against the slab rim (small inset keeps the
            # fade inside the rounded corner).
            self.panel_prog["arc_limit"].value = backdrop[3] - 0.5
            self.panel_prog["arc_fade"].value = 2.5
        else:
            self.panel_prog["arc_limit"].value = 1000.0   # no slab: no clip
            self.panel_prog["arc_fade"].value = 1.0
        for eye_index, eye in enumerate(eyes):
            ctx.viewport = eye.viewport.as_tuple()
            vp = _mul(eye.proj, eye.view)  # proj * view
            if not void_theater:
                # floor grid (the anchor layer)
                self.grid_prog["mvp"].write(_m4(_mul(vp, floor_model)))
                self.grid_prog["model"].write(_m4(floor_model))
                self.grid_vao.render(self.moderngl.TRIANGLES)
            if draw_backdrop:
                # The slab sits behind the rails; its vertices are
                # already in world space (model = identity).
                self.backdrop_prog["mvp"].write(_m4(vp))
                self._backdrop_vao.render(self.moderngl.TRIANGLES)
            # panels
            for panel, model in panels_models:
                tex, uv_off, uv_scale = self._eye_texture(panel, eye_index)
                if tex is None:
                    continue
                tex.use(location=0)
                self.panel_prog["tex"].value = 0
                self.panel_prog["mvp"].write(_m4(_mul(vp, model)))
                self.panel_prog["model"].write(_m4(model))
                self.panel_prog["uv_offset"].value = uv_off
                self.panel_prog["uv_scale"].value = uv_scale
                self.panel_prog["selected"].value = 1.0 if panel.id == selected_id else 0.0
                self.panel_prog["feather"].value = float(panel.data.get("feather", 0.0))
                self.panel_vao.render(self.moderngl.TRIANGLES)
            if cursor is not None:
                ctx.disable(self.moderngl.DEPTH_TEST)   # always visible on top
                self.cursor_prog["mvp"].write(_m4(_mul(vp, _cursor_model(*cursor))))
                self.cursor_vao.render(self.moderngl.TRIANGLES)
                ctx.enable(self.moderngl.DEPTH_TEST)


def _cursor_model(yaw_deg: float, pitch_deg: float,
                  radius: float = 1.75, size: float = 0.035):
    """Place a small billboard on the cylinder (just inside the panels) where the
    controller points, facing the viewer."""
    import math

    from . import mathutil as m
    # q_from_axis_angle(+Y, a) maps forward to -sin(a); negate for yaw-right-positive.
    q = m.q_mul(m.q_from_axis_angle((0.0, 1.0, 0.0), -math.radians(yaw_deg)),
                m.q_from_axis_angle((1.0, 0.0, 0.0), math.radians(pitch_deg)))
    pos = m.v_scale(m.q_rotate(q, (0.0, 0.0, -1.0)), radius)
    scale = m.mat4_identity()
    scale[0] = scale[5] = size
    return m.mat4_mul(m.mat4_translate(pos), m.mat4_mul(m.mat4_from_quat(q), scale))


def _mul(a, b):
    from . import mathutil as m
    return m.mat4_mul(a, b)
