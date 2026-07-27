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
uniform vec2 uv_offset;
uniform vec2 uv_scale;
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = uv_offset + in_uv * uv_scale;
    gl_Position = mvp * vec4(in_pos, 0.0, 1.0);
}
"""

PANEL_FS = """
#version 330
uniform sampler2D tex;
uniform float selected;   // 1.0 if this panel is focused
uniform float border;     // border half-width in uv units
in vec2 v_uv;
out vec4 frag;
void main() {
    vec4 c = texture(tex, v_uv);
    // Accent border when selected; scaled by the card's alpha so it hugs the
    // rounded silhouette instead of drawing a square frame over the corners.
    vec2 d = min(v_uv, 1.0 - v_uv);
    float edge = 1.0 - smoothstep(border * 0.6, border * 1.6, min(d.x, d.y));
    vec3 accent = vec3(0.20, 0.85, 0.95);
    frag = mix(c, vec4(accent, c.a), edge * selected * 0.9 * c.a);
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
        self.cursor_prog = ctx.program(vertex_shader=PANEL_VS, fragment_shader=CURSOR_FS)
        self.cursor_vao = ctx.vertex_array(
            self.cursor_prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        self.cursor_prog["uv_offset"].value = (0.0, 0.0)
        self.cursor_prog["uv_scale"].value = (1.0, 1.0)
        self.panel_prog["border"].value = 0.015
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

    def render(self, fb_size, panels_models, eyes: tuple[EyeMatrices, EyeMatrices],
               floor_model, selected_id: str | None, target=None, cursor=None):
        """cursor: optional (yaw_deg, pitch_deg) of the controller ray; drawn as a
        glowing dot on the panel cylinder."""
        ctx = self.ctx
        fbo = target if target is not None else ctx.screen
        fbo.use()
        ctx.clear(0.02, 0.03, 0.05, 1.0)
        for eye_index, eye in enumerate(eyes):
            ctx.viewport = eye.viewport.as_tuple()
            vp = _mul(eye.proj, eye.view)  # proj * view
            # floor grid
            self.grid_prog["mvp"].write(_m4(_mul(vp, floor_model)))
            self.grid_prog["model"].write(_m4(floor_model))
            self.grid_vao.render(self.moderngl.TRIANGLES)
            # panels
            for panel, model in panels_models:
                tex, uv_off, uv_scale = self._eye_texture(panel, eye_index)
                if tex is None:
                    continue
                tex.use(location=0)
                self.panel_prog["tex"].value = 0
                self.panel_prog["mvp"].write(_m4(_mul(vp, model)))
                self.panel_prog["uv_offset"].value = uv_off
                self.panel_prog["uv_scale"].value = uv_scale
                self.panel_prog["selected"].value = 1.0 if panel.id == selected_id else 0.0
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
