"""Stereo camera math: per-eye view/projection matrices and side-by-side viewports.

The XREAL glasses in 3D mode take one wide frame (e.g. 3840x1080) and show the left
half to the left eye and the right half to the right eye. We render the scene twice,
once into each half, from a camera offset by half the IPD.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import mathutil as m
from .mathutil import Mat4, Quat, Vec3

LEFT = -1
RIGHT = +1


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


def sbs_viewports(width: int, height: int) -> tuple[Rect, Rect]:
    """Split a full SBS frame into (left_eye_rect, right_eye_rect)."""
    half = width // 2
    return Rect(0, 0, half, height), Rect(half, 0, half, height)


@dataclass
class HeadPose:
    orientation: Quat = m.QUAT_IDENTITY
    position: Vec3 = (0.0, 0.0, 0.0)


@dataclass
class EyeMatrices:
    view: Mat4
    proj: Mat4
    viewport: Rect


def eye_position(pose: HeadPose, ipd_m: float, eye: int) -> Vec3:
    """World position of an eye = head position + head-rotated lateral offset."""
    offset = m.q_rotate(pose.orientation, (eye * ipd_m * 0.5, 0.0, 0.0))
    return m.v_add(pose.position, offset)


def eye_matrices(
    pose: HeadPose,
    width: int,
    height: int,
    fov_h_deg: float,
    ipd_m: float,
    near: float = 0.05,
    far: float = 100.0,
) -> tuple[EyeMatrices, EyeMatrices]:
    """Build (left, right) view+projection+viewport for an SBS frame."""
    left_vp, right_vp = sbs_viewports(width, height)
    aspect = left_vp.w / left_vp.h
    fov_v = 2.0 * math.atan(math.tan(math.radians(fov_h_deg) * 0.5) / aspect)
    proj = m.mat4_perspective(fov_v, aspect, near, far)

    def build(eye: int, vp: Rect) -> EyeMatrices:
        pos = eye_position(pose, ipd_m, eye)
        view = m.mat4_rigid_inverse(pose.orientation, pos)
        return EyeMatrices(view=view, proj=proj, viewport=vp)

    return build(LEFT, left_vp), build(RIGHT, right_vp)


def mono_matrices(
    pose: HeadPose,
    width: int,
    height: int,
    fov_h_deg: float,
    near: float = 0.05,
    far: float = 100.0,
) -> tuple[EyeMatrices]:
    """Single full-frame camera (no SBS split, no IPD offset) for a 2D display.

    Used when the glasses only expose a 2D 1920x1080 mode (i.e. the proprietary
    side-by-side 3D mode has not been enabled on the glasses).
    """
    aspect = width / height
    fov_v = 2.0 * math.atan(math.tan(math.radians(fov_h_deg) * 0.5) / aspect)
    proj = m.mat4_perspective(fov_v, aspect, near, far)
    view = m.mat4_rigid_inverse(pose.orientation, pose.position)
    return (EyeMatrices(view=view, proj=proj, viewport=Rect(0, 0, width, height)),)


def head_forward(pose: HeadPose) -> Vec3:
    """Unit vector the head is looking along (-Z in view space)."""
    return m.q_rotate(pose.orientation, (0.0, 0.0, -1.0))


def head_yaw(pose: HeadPose) -> float:
    """Azimuth (radians) of the head's forward direction; 0 = straight ahead (-Z)."""
    fx, _, fz = head_forward(pose)
    return math.atan2(fx, -fz)
