"""Detect XREAL glasses: over USB (sysfs / udev) and as a DisplayPort output (EDID).

Pure functions (`scan_sysfs`, `edid_pnp_id`, `find_glasses_output_from_edids`) are
dependency-free and unit-tested. The live `monitor()` uses pyudev (lazy import).
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from . import config
from .config import GlassesProfile


@dataclass
class UsbGlasses:
    sysfs_path: str
    vid: int
    pid: int
    profile: GlassesProfile


def _read_hex(path: str) -> int | None:
    try:
        with open(path) as fh:
            return int(fh.read().strip(), 16)
    except (OSError, ValueError):
        return None


def is_xreal(vid: int, pid: int) -> bool:
    """True only for XREAL *glasses* — VID 0x3318 AND a glasses-range product id.

    (VID alone also matches XREAL hosts such as the Beam Pro's own USB gadget.)
    """
    return vid == config.XREAL_VID and config.is_glasses_pid(pid)


def profile_for(vid: int, pid: int) -> GlassesProfile | None:
    if not is_xreal(vid, pid):
        return None
    return config.profile_for_pid(pid) or config.GENERIC


def scan_sysfs(root: str = "/sys/bus/usb/devices") -> list[UsbGlasses]:
    """Scan connected USB devices for XREAL glasses. Works with a fake `root` in tests."""
    found: list[UsbGlasses] = []
    for entry in sorted(glob.glob(os.path.join(root, "*"))):
        vid = _read_hex(os.path.join(entry, "idVendor"))
        pid = _read_hex(os.path.join(entry, "idProduct"))
        if vid is None or pid is None:
            continue
        if not is_xreal(vid, pid):
            continue
        prof = profile_for(vid, pid)
        if prof is not None:
            found.append(UsbGlasses(entry, vid, pid, prof))
    return found


# --- EDID ------------------------------------------------------------------
def edid_pnp_id(edid: bytes) -> str | None:
    """Decode the 3-letter PnP manufacturer id from EDID bytes 8-9 (VESA)."""
    if len(edid) < 10:
        return None
    man = (edid[8] << 8) | edid[9]
    a = ((man >> 10) & 0x1F)
    b = ((man >> 5) & 0x1F)
    c = (man & 0x1F)
    if not all(1 <= v <= 26 for v in (a, b, c)):
        return None
    return chr(a + 64) + chr(b + 64) + chr(c + 64)


def edid_product_id(edid: bytes) -> int | None:
    """Product code from EDID bytes 10-11 (little-endian)."""
    if len(edid) < 12:
        return None
    return edid[10] | (edid[11] << 8)


@dataclass
class GlassesOutput:
    connector: str            # DRM connector name, e.g. "card0-DP-1"
    pnp_id: str | None
    product_id: int | None
    profile: GlassesProfile | None


def find_glasses_output_from_edids(edids: dict[str, bytes]) -> GlassesOutput | None:
    """Given {connector_name: edid_bytes}, return the XREAL display if present.

    Passed explicitly so this is testable; `read_drm_edids()` supplies the real data.
    """
    for name, blob in edids.items():
        pnp = edid_pnp_id(blob)
        if pnp not in config.XREAL_EDID_PNP:
            continue
        prod = edid_product_id(blob)
        prof = config.profile_for_edid_product(prod) if prod is not None else None
        return GlassesOutput(name, pnp, prod, prof or config.GENERIC)
    return None


def read_drm_edids(drm_root: str = "/sys/class/drm") -> dict[str, bytes]:
    """Read EDID blobs for all connected DRM connectors (best-effort; may need perms)."""
    out: dict[str, bytes] = {}
    for edid_path in glob.glob(os.path.join(drm_root, "*", "edid")):
        conn = os.path.basename(os.path.dirname(edid_path))
        try:
            with open(edid_path, "rb") as fh:
                blob = fh.read()
        except OSError:
            continue
        if blob:
            out[conn] = blob
    return out


def find_glasses() -> UsbGlasses | None:
    """Highest-level convenience: first XREAL pair found over USB, or None."""
    devs = scan_sysfs()
    return devs[0] if devs else None


def monitor(on_plug, on_unplug):
    """Blocking udev monitor. Calls on_plug(UsbGlasses)/on_unplug(dict) on hotplug.

    Requires pyudev (`pip install pyudev`). Used by `beamshell watch`.
    """
    import pyudev  # lazy: only needed for the live daemon

    context = pyudev.Context()
    # Fire for glasses already connected at startup.
    existing = find_glasses()
    if existing:
        on_plug(existing)

    mon = pyudev.Monitor.from_netlink(context)
    mon.filter_by(subsystem="usb")
    for device in iter(mon.poll, None):
        vid = device.get("ID_VENDOR_ID")
        pid = device.get("ID_MODEL_ID")
        if vid is None or pid is None:
            continue
        try:
            vi, pi = int(vid, 16), int(pid, 16)
        except ValueError:
            continue
        if not is_xreal(vi, pi):
            continue
        if device.action == "add":
            prof = profile_for(vi, pi)
            on_plug(UsbGlasses(device.sys_path, vi, pi, prof))
        elif device.action == "remove":
            on_unplug({"vid": vi, "pid": pi})
