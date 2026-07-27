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
from .stereo import HeadPose, head_yaw


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
    def __init__(self, layout: CylinderLayout | None = None):
        self.layout = layout or CylinderLayout()
        self.panels: list[Panel] = []
        self.selected: int = 0

    def set_panels(self, panels: list[Panel]) -> None:
        self.panels = panels
        self._relayout()
        self.selected = min(self.selected, max(0, len(panels) - 1))

    def _relayout(self) -> None:
        n = len(self.panels)
        for i, p in enumerate(self.panels):
            p.yaw_deg = self.layout.yaw_for_index(i, n)

    def select_by_yaw(self, yaw_deg: float) -> int:
        """Select (and return) the panel whose azimuth is nearest `yaw_deg`."""
        if not self.panels:
            return -1
        best_i, best_d = 0, float("inf")
        for i, p in enumerate(self.panels):
            d = abs(_wrap180(yaw_deg - p.yaw_deg))
            if d < best_d:
                best_i, best_d = i, d
        self.selected = best_i
        return best_i

    def select_by_gaze(self, pose: HeadPose) -> int:
        """Select the panel the head is pointing at."""
        return self.select_by_yaw(math.degrees(head_yaw(pose)))

    def move_selection(self, delta: int) -> int:
        if not self.panels:
            return -1
        self.selected = max(0, min(len(self.panels) - 1, self.selected + delta))
        return self.selected

    @property
    def selected_panel(self) -> Panel | None:
        if 0 <= self.selected < len(self.panels):
            return self.panels[self.selected]
        return None


def _wrap180(deg: float) -> float:
    """Wrap an angle to (-180, 180]."""
    return (deg + 180.0) % 360.0 - 180.0
