"""Head tracking (3DoF orientation) for the shell.

Three sources, in order of preference:
  * XRDriverTracker  — read orientation from wheaney/XRLinuxDriver's IMU output if running
                       (recommended: it already supports the XREAL One/One Pro).
  * HidRawTracker    — read the glasses IMU directly over /dev/hidraw and fuse it ourselves.
                       NOTE: the exact One Pro report layout must be confirmed from a live
                       capture (see docs/08 + docs/09); the parser below defaults to the
                       publicly documented Air-2 layout and is marked TODO where uncertain.
  * StubTracker      — no hardware; returns identity (or a gentle sway in --preview) so the
                       shell runs anywhere for development.

All trackers expose the same tiny interface: get_orientation() -> Quat, recenter(), close().
"""
from __future__ import annotations

import glob
import math
import os
import struct
import time
from typing import Optional

from . import mathutil as m
from .mathutil import Quat


class HeadTracker:
    def get_orientation(self) -> Quat:
        return m.QUAT_IDENTITY

    def recenter(self) -> None:
        pass

    def close(self) -> None:
        pass


class StubTracker(HeadTracker):
    """Identity orientation, or a slow yaw/pitch sway when `sway=True` (dev/preview)."""

    def __init__(self, sway: bool = False):
        self.sway = sway
        self._t0 = time.monotonic()

    def get_orientation(self) -> Quat:
        if not self.sway:
            return m.QUAT_IDENTITY
        t = time.monotonic() - self._t0
        yaw = math.radians(25.0 * math.sin(t * 0.4))
        pitch = math.radians(8.0 * math.sin(t * 0.27))
        qy = m.q_from_axis_angle((0, 1, 0), yaw)
        qx = m.q_from_axis_angle((1, 0, 0), pitch)
        return m.q_mul(qy, qx)


class _Recenterable(HeadTracker):
    """Mixin: apply a recenter offset so 'straight ahead' is where you were looking."""

    def __init__(self):
        self._offset: Quat = m.QUAT_IDENTITY
        self._raw: Quat = m.QUAT_IDENTITY

    def _apply_recenter(self, raw: Quat) -> Quat:
        self._raw = raw
        return m.q_mul(m.q_conj(self._offset), raw)

    def recenter(self) -> None:
        # After recenter, current raw yaw becomes zero.
        self._offset = self._raw


def find_hidraw(vid: int) -> Optional[str]:
    """Return the /dev/hidraw* node belonging to a USB device with the given VID."""
    for uevent in glob.glob("/sys/class/hidraw/*/device/uevent"):
        try:
            with open(uevent) as fh:
                txt = fh.read()
        except OSError:
            continue
        # HID_ID looks like: 0003:00003318:00000435  (bus:VID:PID, hex, zero-padded)
        for line in txt.splitlines():
            if line.startswith("HID_ID="):
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        if int(parts[1], 16) == vid:
                            node = os.path.basename(os.path.dirname(os.path.dirname(uevent)))
                            return f"/dev/{node}"
                    except ValueError:
                        pass
    return None


def parse_imu_report(buf: bytes) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """Parse one HID IMU report -> (gyro_rad_s, accel_m_s2).

    TODO(one-pro): confirm offsets/scale from a live hidraw capture (docs/08). The layout
    below follows the publicly reverse-engineered XREAL Air 2 report: a 64-byte report
    whose gyro/accel are little-endian int16 triplets with fixed scales. Treat as a
    starting point, not ground truth for the One Pro.
    """
    if len(buf) < 32:
        return None
    # Air-2-style example offsets (PLACEHOLDER — verify per model):
    gx, gy, gz = struct.unpack_from("<hhh", buf, 8)
    ax, ay, az = struct.unpack_from("<hhh", buf, 16)
    GYRO_SCALE = math.radians(2000.0) / 32768.0   # rad/s per LSB (±2000 dps)
    ACCEL_SCALE = (8.0 * 9.80665) / 32768.0        # m/s^2 per LSB (±8 g)
    gyro = (gx * GYRO_SCALE, gy * GYRO_SCALE, gz * GYRO_SCALE)
    accel = (ax * ACCEL_SCALE, ay * ACCEL_SCALE, az * ACCEL_SCALE)
    return gyro, accel


class HidRawTracker(_Recenterable):
    """Gyro-integration + accelerometer tilt correction (complementary filter)."""

    def __init__(self, hidraw_path: str, alpha: float = 0.02):
        super().__init__()
        self._fd = os.open(hidraw_path, os.O_RDONLY | os.O_NONBLOCK)
        self._q: Quat = m.QUAT_IDENTITY
        self._last = time.monotonic()
        self._alpha = alpha  # accel correction strength (0 = pure gyro)

    def _integrate(self, gyro, accel, dt) -> None:
        # Gyro integration: q += 0.5 * q * (0, w) * dt
        wq = (0.0, gyro[0], gyro[1], gyro[2])
        dq = m.q_mul(self._q, wq)
        self._q = m.q_norm((
            self._q[0] + 0.5 * dq[0] * dt,
            self._q[1] + 0.5 * dq[1] * dt,
            self._q[2] + 0.5 * dq[2] * dt,
            self._q[3] + 0.5 * dq[3] * dt,
        ))
        # Tilt correction: nudge so measured gravity aligns with world -Y.
        an = m.v_norm(accel)
        if an != (0.0, 0.0, 0.0) and self._alpha > 0:
            grav_world = m.q_rotate(self._q, an)        # gravity in world frame
            axis = m.v_cross(grav_world, (0.0, -1.0, 0.0))
            angle = math.asin(max(-1.0, min(1.0, m.v_len(axis))))
            if angle > 1e-5:
                corr = m.q_from_axis_angle(axis, angle * self._alpha)
                self._q = m.q_norm(m.q_mul(corr, self._q))

    def _pump(self) -> None:
        now = time.monotonic()
        dt = now - self._last
        got = False
        while True:
            try:
                buf = os.read(self._fd, 64)
            except BlockingIOError:
                break
            except OSError:
                break
            if not buf:
                break
            parsed = parse_imu_report(buf)
            if parsed:
                self._integrate(parsed[0], parsed[1], dt if not got else 0.0)
                got = True
        if got:
            self._last = now

    def get_orientation(self) -> Quat:
        self._pump()
        return self._apply_recenter(self._q)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


# ---- wheaney/XRLinuxDriver integration --------------------------------------
# Two channels (verified against the driver source, vendor/XRLinuxDriver):
#  * opentrack UDP (FREE, our default): config `external_mode=opentrack` makes the
#    driver send packets of 6 native-endian doubles [x_cm, y_cm, z_cm, yaw_deg,
#    pitch_deg, roll_deg] + uint32 frame counter to 127.0.0.1:4242
#    (src/plugins/opentrack_source.c).
#  * /dev/shm/breezy_desktop_imu (requires a Breezy "productivity" license):
#    version byte 5; current quaternion as float32 x,y,z,w at byte offset 121;
#    uint64 epoch-ms at 113; XOR parity of bytes 113..184 at 185
#    (src/plugins/breezy_desktop.c, src/buffer.c).

OPENTRACK_PORT = 4242
BREEZY_SHM = "/dev/shm/breezy_desktop_imu"
XR_DRIVER_STATE_FILE = "/dev/shm/xr_driver_state"


def parse_opentrack_packet(buf: bytes) -> tuple[float, ...] | None:
    """One opentrack UDP packet -> (x_cm, y_cm, z_cm, yaw_deg, pitch_deg, roll_deg)."""
    if len(buf) < 48:
        return None
    return struct.unpack_from("<6d", buf, 0)


# NWU (x fwd, y left, z up) -> beamshell (X right, Y up, -Z fwd): the driver's
# yaw axis (z-up) maps to our +Y, but its pitch axis (y-left) maps to our -X and
# its roll axis (x-fwd) to our -Z, so pitch and roll need flipping. Hardware-
# verified 2026-07-19: yaw correct, pitch inverted without the flip (roll flip
# follows from the same axis mapping; check by tilting your head).
DEFAULT_OT_SIGNS = (1.0, -1.0, -1.0)


def opentrack_to_quat(yaw_deg: float, pitch_deg: float, roll_deg: float,
                      signs: tuple[float, float, float] = DEFAULT_OT_SIGNS) -> Quat:
    """Driver euler (NWU frame, degrees) -> beamshell quat (Y up, -Z forward,
    head_yaw positive = looking right). See DEFAULT_OT_SIGNS for the axis-sign
    reasoning; override live via BEAMSHELL_OT_SIGNS="1,-1,-1" if needed.
    """
    qy = m.q_from_axis_angle((0.0, 1.0, 0.0), math.radians(yaw_deg) * signs[0])
    qx = m.q_from_axis_angle((1.0, 0.0, 0.0), math.radians(pitch_deg) * signs[1])
    qz = m.q_from_axis_angle((0.0, 0.0, 1.0), math.radians(roll_deg) * signs[2])
    return m.q_norm(m.q_mul(qy, m.q_mul(qx, qz)))


def parse_breezy_imu(buf: bytes, now_ms: int | None = None,
                     max_age_ms: int = 500) -> Quat | None:
    """The breezy_desktop shm file -> current quat (w,x,y,z), or None if the
    layout version is wrong, the parity check fails (torn write) or it's stale."""
    if len(buf) < 186 or buf[0] != 5:
        return None
    parity = 0
    for b in buf[113:185]:          # uint64 imu_date_ms + float32x16 orientation
        parity ^= b
    if parity != buf[185]:
        return None
    (date_ms,) = struct.unpack_from("<Q", buf, 113)
    if now_ms is not None and abs(now_ms - date_ms) > max_age_ms:
        return None
    x, y, z, w = struct.unpack_from("<4f", buf, 121)   # newest snapshot, w-last
    return m.q_norm((w, x, y, z))


class XRDriverTracker(_Recenterable):
    """3DoF orientation from wheaney/XRLinuxDriver (see format notes above).

    Listens on the opentrack UDP port (the free channel; beamshell's packaged
    config enables it) and falls back to the Breezy shm file when it is present,
    fresh and parity-clean (licensed installs). Raises when the driver doesn't
    appear to be installed/running so `--tracker auto` can fall through.
    """

    def __init__(self, port: int | None = None):
        super().__init__()
        import socket
        self._q: Quat = m.QUAT_IDENTITY
        self._breezy = os.path.exists(BREEZY_SHM)
        if not self._breezy and not os.path.exists(XR_DRIVER_STATE_FILE):
            raise FileNotFoundError(
                "XRLinuxDriver not detected (no /dev/shm/xr_driver_state)")
        signs = os.environ.get("BEAMSHELL_OT_SIGNS", "")
        try:
            s = tuple(float(v) for v in signs.split(","))
            self._signs = s if len(s) == 3 else DEFAULT_OT_SIGNS
        except ValueError:
            self._signs = DEFAULT_OT_SIGNS
        port = port or int(os.environ.get("BEAMSHELL_OPENTRACK_PORT", OPENTRACK_PORT))
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", port))
        self._sock.setblocking(False)

    def get_orientation(self) -> Quat:
        latest = None
        while True:                      # drain: keep only the newest packet
            try:
                buf = self._sock.recv(64)
            except (BlockingIOError, OSError):
                break
            parsed = parse_opentrack_packet(buf)
            if parsed:
                latest = parsed
        if latest is not None:
            self._q = opentrack_to_quat(latest[3], latest[4], latest[5], self._signs)
        elif self._breezy:
            try:
                with open(BREEZY_SHM, "rb") as fh:
                    q = parse_breezy_imu(fh.read(), now_ms=int(time.time() * 1000))
                if q:
                    self._q = q
            except OSError:
                pass
        return self._apply_recenter(self._q)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def open_tracker(kind: str, vid: int | None = None, sway: bool = False) -> HeadTracker:
    """Factory. kind: 'auto' | 'xrdriver' | 'hidraw' | 'stub'."""
    # In auto mode only use the driver when glasses are actually attached (vid set)
    # — the driver service idles 24/7, and preview should keep its stub sway.
    if kind == "xrdriver" or (kind == "auto" and vid is not None):
        try:
            return XRDriverTracker()
        except Exception:
            if kind == "xrdriver":
                raise
    if kind in ("auto", "hidraw") and vid is not None:
        node = find_hidraw(vid)
        if node:
            try:
                return HidRawTracker(node)
            except Exception:
                if kind == "hidraw":
                    raise
    return StubTracker(sway=sway)
