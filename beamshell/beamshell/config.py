"""Static configuration: XREAL glasses identities and per-model display/optics profiles.

Values are taken from the reverse-engineering docs in ../docs (esp. 03 and 09):
XREAL USB vendor id is 0x3318; the One Pro reports EDID product id 16640 / PnP "MRG"
and drives a 3840x1080@60 side-by-side (SBS) 3D mode (1920x1080 per eye).
"""
from __future__ import annotations

from dataclasses import dataclass, field

XREAL_VID = 0x3318  # 13080 — XREAL/Nreal USB vendor id (also used by XREAL *hosts*
                    # like the Beam Pro's own USB gadget, so VID alone is NOT enough).
XREAL_EDID_PNP = ("MRG", "NRL")  # new / old glasses EDID manufacturer ids

# Known glasses product-ids live in this range (0x423..0x442 across all models — see
# docs/03). We require the PID to be in-range/known so a connected Beam Pro or Linux
# phone gadget (same VID, different PID e.g. 0x0528) is not mistaken for glasses.
GLASSES_PID_MIN = 0x423
GLASSES_PID_MAX = 0x442


@dataclass(frozen=True)
class GlassesProfile:
    """Everything the shell needs to know about one glasses model."""
    key: str
    name: str
    model_type: int                 # Nebula's internal "type" (see docs/03)
    usb_pids: tuple[int, ...]        # USB product ids under vendor 0x3318
    edid_product_id: int             # EDID product id reported over DisplayPort
    sbs_width: int = 3840            # full DP width in side-by-side 3D mode
    sbs_height: int = 1080
    refresh_hz: int = 60
    # Optics (approximate; birdbath combiners -> negligible lens distortion).
    fov_h_deg: float = 46.0          # per-eye horizontal field of view
    ipd_m: float = 0.063             # default interpupillary distance (meters)
    # Some models also expose a flat high-refresh mode (e.g. One Pro 1920x1080@90).
    flat_mode: tuple[int, int, int] | None = None

    @property
    def eye_width(self) -> int:
        return self.sbs_width // 2

    @property
    def aspect(self) -> float:
        return self.eye_width / self.sbs_height


# Per-model profiles. One Pro is the confirmed/target unit; others are best-effort
# from the model map so the shell can adapt if a different pair is plugged in.
PROFILES: dict[str, GlassesProfile] = {
    "one_pro": GlassesProfile(
        key="one_pro", name="XREAL One Pro", model_type=6,
        usb_pids=(0x435, 0x436), edid_product_id=16640,
        sbs_width=3840, sbs_height=1080, refresh_hz=60,
        fov_h_deg=48.0, flat_mode=(1920, 1080, 90),
    ),
    "one": GlassesProfile(
        key="one", name="XREAL One", model_type=7,
        usb_pids=(0x437, 0x438), edid_product_id=16641,
        fov_h_deg=45.0, flat_mode=(1920, 1080, 90),
    ),
    "air2_ultra": GlassesProfile(
        key="air2_ultra", name="XREAL Air 2 Ultra", model_type=5,
        usb_pids=(0x425, 0x426), edid_product_id=12598, fov_h_deg=46.0,
    ),
    "air2_pro": GlassesProfile(
        key="air2_pro", name="XREAL Air 2 Pro", model_type=3,
        usb_pids=(0x431, 0x432), edid_product_id=12597, fov_h_deg=46.0,
    ),
    "air2": GlassesProfile(
        key="air2", name="XREAL Air 2", model_type=4,
        usb_pids=(0x427, 0x428), edid_product_id=12596, fov_h_deg=46.0,
    ),
    "air": GlassesProfile(
        key="air", name="XREAL Air", model_type=2,
        usb_pids=(0x423, 0x424), edid_product_id=12594, fov_h_deg=46.0,
    ),
}

# Fallback used when a pair matches the XREAL vendor id but not a known PID.
GENERIC = GlassesProfile(
    key="generic", name="XREAL (generic)", model_type=8,
    usb_pids=(), edid_product_id=0,
)

# Reverse lookups.
PID_TO_PROFILE: dict[int, GlassesProfile] = {
    pid: prof for prof in PROFILES.values() for pid in prof.usb_pids
}
EDID_TO_PROFILE: dict[int, GlassesProfile] = {
    prof.edid_product_id: prof for prof in PROFILES.values()
}


def is_glasses_pid(pid: int) -> bool:
    """True if this USB product-id (under VID 0x3318) is a glasses model."""
    return pid in PID_TO_PROFILE or GLASSES_PID_MIN <= pid <= GLASSES_PID_MAX


def profile_for_pid(pid: int) -> GlassesProfile | None:
    return PID_TO_PROFILE.get(pid)


def profile_for_edid_product(product_id: int) -> GlassesProfile | None:
    return EDID_TO_PROFILE.get(product_id)
