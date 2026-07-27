"""Find the XREAL DisplayPort output and switch it into 3840x1080 side-by-side 3D mode.

On a laptop or Linux phone the glasses appear as a normal Wayland/X output. We locate it
by its EDID (PnP 'MRG'/'NRL'), then set the SBS mode via wlr-randr (wlroots compositors:
sway, phosh, wayfire) or xrandr (X11), restoring the previous mode on exit.

The glasses' own onboard anchoring/stabilizer should be turned OFF for host-driven
tracking (see docs/06); this module only handles the display mode.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from . import detect
from .config import GlassesProfile


@dataclass
class DisplayTarget:
    connector: str                 # DRM connector, e.g. "card0-DP-1"
    output_name: str | None        # compositor output name, e.g. "DP-1"
    profile: GlassesProfile | None
    previous_mode: str | None = None


def _drm_to_output_name(connector: str) -> str:
    """'card0-DP-1' -> 'DP-1' (the name wlr-randr/xrandr/glfw use)."""
    return re.sub(r"^card\d+-", "", connector)


def output_modes(connector: str, drm_root: str = "/sys/class/drm") -> list[str]:
    """Available 'WxH' modes for a DRM connector (from sysfs; dedup, order preserved)."""
    path = os.path.join(drm_root, connector, "modes")
    seen, out = set(), []
    try:
        with open(path) as fh:
            for line in fh:
                mode = line.strip()
                if mode and mode not in seen:
                    seen.add(mode)
                    out.append(mode)
    except OSError:
        pass
    return out


def sbs_available(target: "DisplayTarget", profile, drm_root: str = "/sys/class/drm") -> bool:
    """True if the glasses currently expose the profile's side-by-side 3D mode.

    XREAL glasses only advertise the 3840x1080 SBS EDID after being switched into 3D
    mode (a proprietary USB command on the Beam Pro, or the glasses' on-board display
    toggle). Until then only 2D 1920x1080 modes are present.
    """
    want = f"{profile.sbs_width}x{profile.sbs_height}"
    return want in output_modes(target.connector, drm_root)


def find_display() -> DisplayTarget | None:
    edids = detect.read_drm_edids()
    found = detect.find_glasses_output_from_edids(edids)
    if not found:
        return None
    return DisplayTarget(
        connector=found.connector,
        output_name=_drm_to_output_name(found.connector),
        profile=found.profile,
    )


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return p.returncode, (p.stdout + p.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _session_is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE") == "wayland"


def set_sbs_mode(target: DisplayTarget, profile: GlassesProfile) -> bool:
    """Switch the glasses output to WxH@Hz SBS. Returns True on success."""
    name = target.output_name or ""
    mode = f"{profile.sbs_width}x{profile.sbs_height}"
    hz = profile.refresh_hz
    if _session_is_wayland() and shutil.which("wlr-randr"):
        rc, out = _run(["wlr-randr", "--output", name,
                        "--mode", f"{mode}@{hz}Hz", "--on"])
        return rc == 0
    if shutil.which("xrandr"):
        # ensure the modeline exists then apply
        _run(["xrandr", "--output", name, "--mode", mode, "--rate", str(hz)])
        rc, out = _run(["xrandr", "--output", name, "--mode", mode])
        return rc == 0
    return False


def restore(target: DisplayTarget) -> None:
    name = target.output_name or ""
    if not name:
        return
    if _session_is_wayland() and shutil.which("wlr-randr"):
        _run(["wlr-randr", "--output", name, "--preferred"])
    elif shutil.which("xrandr"):
        _run(["xrandr", "--output", name, "--auto"])
