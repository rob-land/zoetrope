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
    texture: object | None = None  # renderer-specific handle (moderngl.Texture)
    stereo_mode: str = "mono"      # "mono" | "sbs" (texture already L|R) | "pair"
    texture_right: object | None = None  # for "pair": right-eye texture
    data: dict = field(default_factory=dict)


@dataclass
class CylinderLayout:
    radius_m: float = 1.8
    arc_span_deg: float = 90.0     # max total horizontal spread of the launcher row
    step_deg: float = 22.0         # preferred spacing between tiles

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
        return (self.radius_m * math.sin(a), panel.y_m, -self.radius_m * math.cos(a))

    def model_matrix(self, panel: Panel) -> Mat4:
        """Panel transform: translate onto the cylinder, yaw to face the center."""
        pos = self.position(panel)
        rot = m.mat4_from_quat(
            m.q_from_axis_angle((0.0, 1.0, 0.0), math.radians(panel.yaw_deg))
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

    def __init__(self, layout: CylinderLayout | None = None):
        self.layout = layout or CylinderLayout()
        self.rows: list[list[Panel]] = []
        self.row: int = 0
        self._col: dict[int, int] = {}   # per-row focus memory

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

    def _relayout_row(self, i: int, row: list[Panel]) -> None:
        n = len(row)
        span = self.layout.step_deg * (n - 1)
        if span <= self.layout.arc_span_deg:
            for j, p in enumerate(row):
                p.yaw_deg = self.layout.yaw_for_index(j, n)
        else:
            # Leanback scroll: center the focused column; neighbours
            # step outward, clamped by nothing (off-arc cards are simply
            # behind the viewer until scrolled to).
            sel = self._col.get(i, 0)
            for j, p in enumerate(row):
                p.yaw_deg = self.layout.step_deg * (j - sel)

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
        """Select the current row's panel nearest `yaw_deg` (pointer)."""
        if not self.rows:
            return -1
        row = self.rows[self.row]
        best_j, best_d = 0, float("inf")
        for j, p in enumerate(row):
            d = abs(_wrap180(yaw_deg - p.yaw_deg))
            if d < best_d:
                best_j, best_d = j, d
        self._col[self.row] = best_j
        self._relayout_row(self.row, row)
        return best_j

    def select_by_gaze(self, pose: HeadPose) -> int:
        """Gaze gravity: pick the row by head pitch, the column by yaw —
        the gaze snaps to the card grid, never a free cursor."""
        if not self.rows:
            return -1
        pitch = math.degrees(head_pitch(pose))
        best_i, best_d = self.row, float("inf")
        for i, row in enumerate(self.rows):
            row_pitch = math.degrees(
                math.atan2(row[0].y_m, self.layout.radius_m))
            d = abs(pitch - row_pitch)
            if d < best_d:
                best_i, best_d = i, d
        self.row = best_i
        return self.select_by_yaw(math.degrees(head_yaw(pose)))


def _wrap180(deg: float) -> float:
    """Wrap an angle to (-180, 180]."""
    return (deg + 180.0) % 360.0 - 180.0
