"""Minimal 3D math (pure Python, no numpy) so the core is dependency-free and testable.

Matrices are 16-element lists in OpenGL **column-major** order: element (row, col) is
m[col * 4 + row]. Vectors are 3-tuples. Quaternions are (w, x, y, z) tuples.
"""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # (w, x, y, z)
Mat4 = list[float]


# --- vectors ---------------------------------------------------------------
def v_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def v_len(a: Vec3) -> float:
    return math.sqrt(v_dot(a, a))


def v_norm(a: Vec3) -> Vec3:
    n = v_len(a)
    return a if n == 0.0 else v_scale(a, 1.0 / n)


# --- quaternions -----------------------------------------------------------
QUAT_IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def q_norm(q: Quat) -> Quat:
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n == 0.0:
        return QUAT_IDENTITY
    return (w / n, x / n, y / n, z / n)


def q_conj(q: Quat) -> Quat:
    w, x, y, z = q
    return (w, -x, -y, -z)


def q_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def q_from_axis_angle(axis: Vec3, angle_rad: float) -> Quat:
    ax, ay, az = v_norm(axis)
    h = angle_rad * 0.5
    s = math.sin(h)
    return (math.cos(h), ax * s, ay * s, az * s)


def q_rotate(q: Quat, v: Vec3) -> Vec3:
    """Rotate vector v by unit quaternion q."""
    w, x, y, z = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    # v' = v + w*t + cross(q.xyz, t)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


# --- matrices --------------------------------------------------------------
def mat4_identity() -> Mat4:
    return [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


def mat4_mul(a: Mat4, b: Mat4) -> Mat4:
    """Return a * b (both column-major); applies b first, then a."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = (
                a[0 * 4 + row] * b[col * 4 + 0] +
                a[1 * 4 + row] * b[col * 4 + 1] +
                a[2 * 4 + row] * b[col * 4 + 2] +
                a[3 * 4 + row] * b[col * 4 + 3]
            )
    return out


def mat4_translate(v: Vec3) -> Mat4:
    m = mat4_identity()
    m[12], m[13], m[14] = v[0], v[1], v[2]
    return m


def mat4_from_quat(q: Quat) -> Mat4:
    w, x, y, z = q_norm(q)
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    # column-major rotation matrix
    return [
        1 - 2 * (yy + zz), 2 * (xy + wz),     2 * (xz - wy),     0.0,
        2 * (xy - wz),     1 - 2 * (xx + zz), 2 * (yz + wx),     0.0,
        2 * (xz + wy),     2 * (yz - wx),     1 - 2 * (xx + yy), 0.0,
        0.0,               0.0,               0.0,               1.0,
    ]


def mat4_perspective(fovy_rad: float, aspect: float, near: float, far: float) -> Mat4:
    f = 1.0 / math.tan(fovy_rad * 0.5)
    m = [0.0] * 16
    m[0] = f / aspect
    m[5] = f
    m[10] = (far + near) / (near - far)
    m[11] = -1.0
    m[14] = (2.0 * far * near) / (near - far)
    return m


def mat4_rigid_inverse(rot: Quat, pos: Vec3) -> Mat4:
    """View matrix for a camera with orientation `rot` at world position `pos`.

    world_to_view = R^-1 * Translate(-pos).
    """
    return mat4_mul(mat4_from_quat(q_conj(rot)), mat4_translate(v_scale(pos, -1.0)))
