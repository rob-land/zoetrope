"""Google Daydream controller as a BLE pointer/remote for the shell.

The Daydream controller is a ~60 Hz BLE peripheral (name "Daydream controller",
service 0xFE55). Once notifications are enabled on its data characteristic it
streams 20-byte packets carrying orientation (axis-angle), accel, gyro, a 2-axis
touchpad and five buttons. Layout follows the public reverse engineering
(mrdoob/daydream-controller.js); note our xOri decode uses `byte3 & 0xE0` — the
upstream JS has `& 0x80`, which drops the field's two low bits (byte 3 splits
[7:5]=xOri[2:0], [4:0]=yOri[12:8], so 0xE0 is the structurally consistent mask).

Split, like tracking.py, into pure logic (parser, gesture detection, pointer
gating — unit-tested, no deps) and a `DaydreamController` transport that needs
`bleak` (pip install -e '.[controller]') and runs asyncio in a daemon thread.

Controls (see gestures below): point to select, click = open, app = back,
home = recenter head + pointer, swipe or volume keys = prev/next.

The controller must be paired/woken first: hold Home until the LED blinks,
`bluetoothctl scan on` + `connect <MAC>` once; afterwards it reconnects on wake.

Axis frame: the axis-angle vector is right-handed, Y up, -Z forward — the same
convention as zoetrope — so the default mapping is identity. Signs are a
best guess until tried on hardware; tune live via ZOETROPE_DD_SIGNS="1,1,1".
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

from . import mathutil as m
from .mathutil import Quat, Vec3

DAYDREAM_NAME = "Daydream controller"
DAYDREAM_SERVICE_UUID = "0000fe55-0000-1000-8000-00805f9b34fb"
DAYDREAM_DATA_UUID = "00000001-1000-1000-8000-00805f9b34fb"

_ORI_SCALE = 2.0 * math.pi / 4095.0
_ACC_SCALE = 8.0 * 9.8 / 4095.0
_GYRO_SCALE = (2048.0 / 180.0) * math.pi / 4095.0


@dataclass
class DaydreamState:
    """One decoded notification packet."""
    seq: int
    ori: Vec3                  # axis-angle, radians (axis * angle)
    accel: Vec3                # m/s^2
    gyro: Vec3                 # rad/s
    touch: tuple[float, float]  # 0..1; (0,0) means finger off the pad
    click: bool                # touchpad pressed in
    app: bool
    home: bool
    vol_up: bool
    vol_down: bool

    @property
    def touching(self) -> bool:
        return self.touch != (0.0, 0.0)


def _s13(v: int) -> int:
    """Sign-extend a 13-bit field."""
    return v - 0x2000 if v & 0x1000 else v


def parse_daydream_packet(buf: bytes) -> DaydreamState | None:
    """Decode one 20-byte Daydream notification, or None if too short."""
    if len(buf) < 20:
        return None
    b = buf
    seq = (b[1] & 0x7C) >> 2
    xo = _s13((b[1] & 0x03) << 11 | b[2] << 3 | (b[3] & 0xE0) >> 5)
    yo = _s13((b[3] & 0x1F) << 8 | b[4])
    zo = _s13(b[5] << 5 | (b[6] & 0xF8) >> 3)
    xa = _s13((b[6] & 0x07) << 10 | b[7] << 2 | (b[8] & 0xC0) >> 6)
    ya = _s13((b[8] & 0x3F) << 7 | (b[9] & 0xFE) >> 1)
    za = _s13((b[9] & 0x01) << 12 | b[10] << 4 | (b[11] & 0xF0) >> 4)
    xg = _s13((b[11] & 0x0F) << 9 | b[12] << 1 | (b[13] & 0x80) >> 7)
    yg = _s13((b[13] & 0x7F) << 6 | (b[14] & 0xFC) >> 2)
    zg = _s13((b[14] & 0x03) << 11 | b[15] << 3 | (b[16] & 0xE0) >> 5)
    xt = ((b[16] & 0x1F) << 3 | (b[17] & 0xE0) >> 5) / 255.0
    yt = ((b[17] & 0x1F) << 3 | (b[18] & 0xE0) >> 5) / 255.0
    return DaydreamState(
        seq=seq,
        ori=(xo * _ORI_SCALE, yo * _ORI_SCALE, zo * _ORI_SCALE),
        accel=(xa * _ACC_SCALE, ya * _ACC_SCALE, za * _ACC_SCALE),
        gyro=(xg * _GYRO_SCALE, yg * _GYRO_SCALE, zg * _GYRO_SCALE),
        touch=(xt, yt),
        click=bool(b[18] & 0x1),
        home=bool(b[18] & 0x2),
        app=bool(b[18] & 0x4),
        vol_down=bool(b[18] & 0x8),
        vol_up=bool(b[18] & 0x10),
    )


def _signs_from_env(var: str) -> Vec3:
    try:
        s = tuple(float(v) for v in os.environ.get(var, "").split(","))
        return s if len(s) == 3 else (1.0, 1.0, 1.0)
    except ValueError:
        return (1.0, 1.0, 1.0)


def orientation_quat(ori: Vec3, signs: Vec3 | None = None) -> Quat:
    """Axis-angle vector -> zoetrope quat (Y up, -Z forward)."""
    if signs is None:
        signs = _signs_from_env("ZOETROPE_DD_SIGNS")
    v = (ori[0] * signs[0], ori[1] * signs[1], ori[2] * signs[2])
    angle = m.v_len(v)
    if angle < 1e-9:
        return m.QUAT_IDENTITY
    return m.q_from_axis_angle(v, angle)


def pointer_yaw_pitch_deg(q: Quat) -> tuple[float, float]:
    """Where the controller points: yaw (positive = right, same convention as
    stereo.head_yaw) and pitch (positive = up), in degrees."""
    fwd = m.q_rotate(q, (0.0, 0.0, -1.0))
    yaw = math.degrees(math.atan2(fwd[0], -fwd[2]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, fwd[1]))))
    return yaw, pitch


# --- gestures (pure logic) --------------------------------------------------

SWIPE_MIN_DX = 0.30      # touchpad fraction to count a horizontal swipe
SWIPE_MAX_DY = 0.35      # reject diagonal drags
POINTER_MOVE_DEG = 1.0   # pointer must move this far to count as "active"
POINTER_ACTIVE_S = 0.6   # ...within this window, else gaze takes over


class ControllerGestures:
    """Turn a stream of DaydreamState into discrete shell events.

    feed(state) -> list of: 'activate' 'back' 'recenter' 'prev' 'next' 'up' 'down'.
    Buttons emit on the press edge. A touch that travels mostly along one axis
    emits a swipe when the finger lifts: horizontal -> prev/next, vertical ->
    up/down (touchpad y grows downward, so a downward drag emits 'down'). A
    click during the touch suppresses the swipe, so click-to-open never swipes.
    """

    def __init__(self):
        self._prev: DaydreamState | None = None
        self._touch_start: tuple[float, float] | None = None
        self._touch_clicked = False

    def feed(self, s: DaydreamState) -> list[str]:
        p, self._prev = self._prev, s
        events: list[str] = []

        def pressed(name: str) -> bool:
            return getattr(s, name) and not (p is not None and getattr(p, name))

        if pressed("click"):
            events.append("activate")
        if pressed("app"):
            events.append("back")
        if pressed("home"):
            events.append("recenter")
        if pressed("vol_up"):
            events.append("next")
        if pressed("vol_down"):
            events.append("prev")

        if s.touching:
            if self._touch_start is None:
                self._touch_start = s.touch
                self._touch_clicked = False
            if s.click:
                self._touch_clicked = True
        elif self._touch_start is not None:
            start, self._touch_start = self._touch_start, None
            end = p.touch if (p is not None and p.touching) else start
            dx, dy = end[0] - start[0], end[1] - start[1]
            if not self._touch_clicked:
                if abs(dx) >= SWIPE_MIN_DX and abs(dy) <= SWIPE_MAX_DY:
                    events.append("next" if dx > 0 else "prev")
                elif abs(dy) >= SWIPE_MIN_DX and abs(dx) <= SWIPE_MAX_DY:
                    events.append("down" if dy > 0 else "up")
        return events


class PointerGate:
    """Only let the pointer drive selection while the controller is moving.

    A controller lying on the desk streams a constant orientation; without
    gating it would pin the selection and head gaze would never win.
    """

    def __init__(self, move_deg: float = POINTER_MOVE_DEG,
                 window_s: float = POINTER_ACTIVE_S):
        self._move_deg = move_deg
        self._window_s = window_s
        self._last: tuple[float, float] | None = None
        self._active_until = -math.inf

    def feed(self, yaw_deg: float, pitch_deg: float, now: float) -> bool:
        if self._last is not None:
            dy = abs(yaw_deg - self._last[0])
            dp = abs(pitch_deg - self._last[1])
            if max(dy, dp) >= self._move_deg:
                self._active_until = now + self._window_s
        self._last = (yaw_deg, pitch_deg)
        return now <= self._active_until


# --- BLE transport (needs bleak) --------------------------------------------

class DaydreamController:
    """Background BLE client: scans for the controller, subscribes, reconnects.

    Same spirit as the trackers: construct it and poll from the render loop.
      poll()          -> latest DaydreamState (None if never seen / stale)
      poll_events()   -> drained gesture events ('activate', 'back', ...)
      pointer()       -> (yaw_deg, pitch_deg) after recentering, or None when
                         the controller is idle/stale (PointerGate)
      recenter()      -> current pointing direction becomes yaw 0
      close()
    """

    STALE_S = 0.5

    def __init__(self, address: str | None = None, name: str = DAYDREAM_NAME):
        import bleak  # noqa: F401  (fail fast when the extra isn't installed)
        self._address = address or os.environ.get("ZOETROPE_DD_ADDRESS") or None
        self._name = name
        self._lock = threading.Lock()
        self._state: DaydreamState | None = None
        self._state_at = -math.inf
        self._events: deque[str] = deque(maxlen=32)
        self._gestures = ControllerGestures()
        self._gate = PointerGate()
        self._yaw_offset = 0.0
        self._connected = False
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="daydream-ble", daemon=True)
        self._thread.start()

    # -- consumer side (render loop) --
    @property
    def connected(self) -> bool:
        return self._connected

    def poll(self) -> DaydreamState | None:
        with self._lock:
            if time.monotonic() - self._state_at > self.STALE_S:
                return None
            return self._state

    def poll_events(self) -> list[str]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    def pointer(self) -> tuple[float, float] | None:
        s = self.poll()
        if s is None:
            return None
        yaw, pitch = pointer_yaw_pitch_deg(orientation_quat(s.ori))
        if not self._gate.feed(yaw, pitch, time.monotonic()):
            return None
        return yaw - self._yaw_offset, pitch

    def recenter(self) -> None:
        s = self.poll()
        if s is not None:
            yaw, _ = pointer_yaw_pitch_deg(orientation_quat(s.ori))
            self._yaw_offset = yaw

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    # -- BLE side (daemon thread) --
    def _on_notify(self, _handle, data: bytearray) -> None:
        s = parse_daydream_packet(bytes(data))
        if s is None:
            return
        events = self._gestures.feed(s)
        with self._lock:
            self._state = s
            self._state_at = time.monotonic()
            self._events.extend(events)

    def _run(self) -> None:
        import asyncio
        asyncio.run(self._ble_loop())

    async def _ble_loop(self) -> None:
        import asyncio
        from bleak import BleakClient, BleakScanner
        while not self._stop.is_set():
            try:
                address = self._address
                if address is None:
                    dev = await BleakScanner.find_device_by_name(
                        self._name, timeout=5.0)
                    if dev is None:
                        await asyncio.sleep(2.0)
                        continue
                    address = dev.address
                async with BleakClient(address) as client:
                    await client.start_notify(DAYDREAM_DATA_UUID, self._on_notify)
                    self._connected = True
                    print(f"[controller] Daydream connected ({address})")
                    while not self._stop.is_set() and client.is_connected:
                        await asyncio.sleep(0.25)
                    if client.is_connected:
                        await client.stop_notify(DAYDREAM_DATA_UUID)
            except Exception as e:
                if not self._stop.is_set():
                    print(f"[controller] BLE error, retrying: {e}")
                    await asyncio.sleep(2.0)
            finally:
                if self._connected:
                    print("[controller] Daydream disconnected")
                self._connected = False


def open_controller(kind: str) -> DaydreamController | None:
    """Factory. kind: 'auto' | 'daydream' | 'none'.

    'auto' returns None when bleak isn't installed; 'daydream' raises instead.
    """
    if kind == "none":
        return None
    try:
        return DaydreamController()
    except Exception:
        if kind == "daydream":
            raise
        return None
