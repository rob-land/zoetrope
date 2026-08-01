"""The spatial scene: floating panels laid out on a cylinder, and gaze selection.

This is the Nebula-like layout core. A `Panel` is a flat quad placed on an arc around
the viewer, always facing inward. `LauncherScene` arranges N panels and picks the one
the head is pointing at.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import mathutil as m
from .mathutil import Mat4, Vec3
from .stereo import HeadPose, head_pitch, head_yaw


@dataclass
class Panel:
    id: str
    title: str
    yaw_deg: float                 # azimuth on the cylinder (0 = straight ahead)
    width_m: float = 0.9           # physical size in meters at the cylinder surface
    height_m: float = 0.55
    y_m: float = 0.0               # vertical offset
    radius_bias: float = 0.0       # small per-row radius offset (kills z-fighting)
    texture: object | None = None  # renderer-specific handle (moderngl.Texture)
    stereo_mode: str = "mono"      # "mono" | "sbs" (texture already L|R) | "pair"
    texture_right: object | None = None  # for "pair": right-eye texture
    data: dict = field(default_factory=dict)


@dataclass
class CylinderLayout:
    radius_m: float = 1.8
    arc_span_deg: float = 90.0     # max total horizontal spread of the launcher row
    step_deg: float = 22.0         # preferred spacing between tiles
    #: rail ends bend *toward* the viewer: radius shrinks quadratically
    #: with azimuth, up to this much at 45 deg. On the fixed-focus
    #: optics a true constant-radius arc reads as "ends curving away";
    #: pulling the ends in makes the rail feel equidistant as the head
    #: turns (hardware feedback 2026-07-29).
    end_pull_m: float = 0.25

    def yaw_for_index(self, index: int, count: int) -> float:
        """Symmetric, centered layout. Uses `step_deg` spacing but never exceeds
        `arc_span_deg` total, so a couple of tiles sit near the center (in view) rather
        than at the far edges."""
        if count <= 1:
            return 0.0
        step = min(self.step_deg, self.arc_span_deg / (count - 1))
        return -step * (count - 1) / 2.0 + step * index

    def position(self, panel: Panel) -> Vec3:
        a = math.radians(panel.yaw_deg)
        pull = self.end_pull_m * min(1.0, (abs(panel.yaw_deg) / 45.0) ** 2)
        r = self.radius_m + panel.radius_bias - pull
        return (r * math.sin(a), panel.y_m, -r * math.cos(a))

    def model_matrix(self, panel: Panel) -> Mat4:
        """Panel transform: translate onto the cylinder, yaw to face the center.

        q_from_axis_angle(+Y, a) turns the quad's +Z normal to
        (sin a, 0, cos a); at azimuth `yaw` (position +x for +yaw) facing
        the origin needs (-sin, 0, cos), i.e. a rotation by *minus* the
        azimuth — same negation _cursor_model documents. The old +yaw
        turned tiles away from the viewer by 2x their azimuth (edge-on
        sliver by ~45 deg; unnoticed while everything sat near center).
        """
        pos = self.position(panel)
        rot = m.mat4_from_quat(
            m.q_from_axis_angle((0.0, 1.0, 0.0), -math.radians(panel.yaw_deg))
        )
        scale = m.mat4_identity()
        scale[0] = panel.width_m
        scale[5] = panel.height_m
        return m.mat4_mul(m.mat4_translate(pos), m.mat4_mul(rot, scale))


class LauncherScene:
    """Stacked leanback rails on the cylinder (doc 17 §2).

    Rows scroll horizontally with per-row focus memory; a long row
    re-centers on its focused column so the selection stays inside the
    comfort cone. ``set_panels`` remains as the single-row shorthand.
    """

    #: a row must beat the current one by this much head pitch to steal
    #: focus (stops rail flapping at the boundary)
    ROW_HYSTERESIS_DEG = 2.0

    def __init__(self, layout: CylinderLayout | None = None):
        self.layout = layout or CylinderLayout()
        self.rows: list[list[Panel]] = []
        self.row: int = 0
        self._col: dict[int, int] = {}   # per-row focus memory
        self._off: dict[int, int] = {}   # per-row scroll-window offset

    # -- content -------------------------------------------------------------

    def set_rows(self, rows: list[list[Panel]]) -> None:
        self.rows = [r for r in rows if r]
        self.row = min(self.row, max(0, len(self.rows) - 1))
        for i, r in enumerate(self.rows):
            self._col[i] = min(self._col.get(i, 0), len(r) - 1)
        self._relayout()

    def set_panels(self, panels: list[Panel]) -> None:
        """Single-row shorthand (kept for pages that are one rail)."""
        self.set_rows([panels] if panels else [])

    @property
    def panels(self) -> list[Panel]:
        return [p for r in self.rows for p in r]

    # -- layout --------------------------------------------------------------

    def _relayout(self) -> None:
        for i, row in enumerate(self.rows):
            self._relayout_row(i, row)

    def _row_step(self, row: list[Panel]) -> float:
        """Per-row tile spacing: narrow cards (posters) pack tighter.
        Angular card width + ~3.5 deg gap, capped at the layout step."""
        width = max(p.width_m for p in row)
        return min(self.layout.step_deg,
                   math.degrees(width / self.layout.radius_m) + 3.5)

    def _relayout_row(self, i: int, row: list[Panel]) -> None:
        n = len(row)
        step = self._row_step(row)
        if step * (n - 1) <= self.layout.arc_span_deg:
            step = min(step, self.layout.step_deg)
            for j, p in enumerate(row):
                p.yaw_deg = -step * (n - 1) / 2.0 + step * j
                p.data["offstage"] = False
            self._off[i] = 0
            return
        # Windowed leanback scroll: the window shifts only when the
        # selection walks past its edge (never on gaze — see
        # select_by_yaw), so cards don't stream past a stationary head.
        half = self.layout.arc_span_deg / 2.0
        w = max(1, int(half / step))
        sel = self._col.get(i, 0)
        off = self._off.get(i, w)
        off = min(max(off, sel - w), sel + w)      # keep sel inside window
        off = min(max(off, w), n - 1 - w)          # pin rail ends
        self._off[i] = off
        for j, p in enumerate(row):
            p.yaw_deg = step * (j - off)
            # Off-window cards are unselectable (select_by_yaw skips
            # them) — and undrawable: rendered, they poke past the slab
            # and pile up near ±90° where sin() flattens their spacing.
            p.data["offstage"] = abs(p.yaw_deg) > half

    # -- selection -----------------------------------------------------------

    @property
    def selected(self) -> int:
        """Flat index of the selection (renderer/back-compat)."""
        flat = 0
        for i, r in enumerate(self.rows):
            if i == self.row:
                return flat + self._col.get(i, 0)
            flat += len(r)
        return -1

    @property
    def selected_panel(self) -> Panel | None:
        if not self.rows:
            return None
        r = self.rows[self.row]
        return r[min(self._col.get(self.row, 0), len(r) - 1)]

    def move_selection(self, delta: int) -> int:
        if not self.rows:
            return -1
        r = self.rows[self.row]
        col = max(0, min(len(r) - 1, self._col.get(self.row, 0) + delta))
        self._col[self.row] = col
        self._relayout_row(self.row, r)
        return col

    def move_row(self, delta: int) -> int:
        if not self.rows:
            return -1
        self.row = max(0, min(len(self.rows) - 1, self.row + delta))
        return self.row

    def select_by_yaw(self, yaw_deg: float) -> int:
        """Select the current row's *visible* panel nearest `yaw_deg`.

        Gaze/pointer never scrolls the rail (that caused a feedback
        loop: recentering moved a different card under the stationary
        gaze). Off-arc cards are reached with prev/next, which shifts
        the window deterministically."""
        if not self.rows:
            return -1
        row = self.rows[self.row]
        half = self.layout.arc_span_deg / 2.0
        best_j, best_d = None, float("inf")
        for j, p in enumerate(row):
            if abs(p.yaw_deg) > half:
                continue
            d = abs(_wrap180(yaw_deg - p.yaw_deg))
            if d < best_d:
                best_j, best_d = j, d
        if best_j is None:
            return self._col.get(self.row, 0)
        self._col[self.row] = best_j
        return best_j

    def select_by_gaze(self, pose: HeadPose) -> int:
        """Gaze gravity: pick the row by head pitch, the column by yaw —
        the gaze snaps to the card grid, never a free cursor."""
        if not self.rows:
            return -1
        pitch = math.degrees(head_pitch(pose))

        def row_dist(i: int) -> float:
            row_pitch = math.degrees(
                math.atan2(self.rows[i][0].y_m, self.layout.radius_m))
            return abs(pitch - row_pitch)

        best_i = min(range(len(self.rows)), key=row_dist)
        # Hysteresis: the new row must clearly win, or the current stays.
        if (best_i != self.row
                and row_dist(self.row) - row_dist(best_i)
                < self.ROW_HYSTERESIS_DEG):
            best_i = self.row
        self.row = best_i
        return self.select_by_yaw(math.degrees(head_yaw(pose)))


def _wrap180(deg: float) -> float:
    """Wrap an angle to (-180, 180]."""
    return (deg + 180.0) % 360.0 - 180.0


def backdrop_mesh(layout: CylinderLayout, half_arc_deg: float,
                  y_bottom: float, y_top: float,
                  radius_bias: float = 0.08, segments: int = 48):
    """The dashboard slab: one curved surface behind the rails (SteamVR-
    dashboard form, doc 17 §2b).

    Returns ``(vertices, (width_m, height_m))`` where vertices is a flat
    triangle list of (x, y, z, u, v) in world space. The strip follows
    the same end-pull radius warp as the tiles (sitting `radius_bias`
    behind them everywhere), u sweeps the arc, v sweeps bottom→top;
    width_m is the arc length so the shader can round corners in meters.
    """
    verts: list[float] = []

    def rim(yaw_deg: float) -> tuple[float, float]:
        a = math.radians(yaw_deg)
        pull = layout.end_pull_m * min(1.0, (abs(yaw_deg) / 45.0) ** 2)
        r = layout.radius_m + radius_bias - pull
        return r * math.sin(a), -r * math.cos(a)

    cols = []
    for s in range(segments + 1):
        u = s / segments
        yaw = -half_arc_deg + 2.0 * half_arc_deg * u
        x, z = rim(yaw)
        cols.append((x, z, u))
    for (x0, z0, u0), (x1, z1, u1) in zip(cols, cols[1:]):
        quad = [(x0, y_bottom, z0, u0, 0.0), (x1, y_bottom, z1, u1, 0.0),
                (x1, y_top, z1, u1, 1.0), (x0, y_top, z0, u0, 1.0)]
        for i in (0, 1, 2, 0, 2, 3):
            verts.extend(quad[i])
    width_m = layout.radius_m * math.radians(2.0 * half_arc_deg)
    return verts, (width_m, y_top - y_bottom)
