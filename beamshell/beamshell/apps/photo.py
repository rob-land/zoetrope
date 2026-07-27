"""3D photo viewer.

Supported inputs:
  * .mpo                    — multi-picture JPEG (two frames) -> stereo "pair"
  * side-by-side image      — a single wide image (aspect >= ~1.8) -> "sbs"
  * two files L.ext,R.ext   — explicit stereo pair -> "pair"
  * anything else           — shown flat ("mono")

The Beam Pro's own spatial stills are HEIC; Pillow can read those if pillow-heif is
installed (optional). SBS/MPO/JPEG work with plain Pillow.
"""
from __future__ import annotations

import os

from ..scene import Panel
from .base import App, message_texture, pil_to_texture


def _split_mpo(path: str):
    """Split an MPO (concatenated JPEGs) into (left_img, right_img) PIL images."""
    from io import BytesIO
    from PIL import Image
    with open(path, "rb") as fh:
        data = fh.read()
    soi = b"\xff\xd8\xff"
    starts = [i for i in range(len(data) - 3) if data[i:i + 3] == soi]
    if len(starts) >= 2:
        left = Image.open(BytesIO(data[starts[0]:starts[1]]))
        right = Image.open(BytesIO(data[starts[1]:]))
        return left, right
    return Image.open(BytesIO(data)), None


class PhotoApp(App):
    id = "photo"
    title = "3D Photo"

    def __init__(self, ctx, path: str, right_path: str | None = None):
        self.ctx = ctx
        self.path = path
        self._panel = self._load(path, right_path)

    def _load(self, path: str, right_path: str | None) -> Panel:
        try:
            from PIL import Image
        except ImportError:
            return self._error(["Pillow not installed:", "pip install pillow pillow-heif"])
        try:
            if right_path:
                left = Image.open(path)
                right = Image.open(right_path)
                return self._pair_panel(left, right)
            ext = os.path.splitext(path)[1].lower()
            if ext == ".mpo":
                left, right = _split_mpo(path)
                if right is not None:
                    return self._pair_panel(left, right)
                return self._sbs_or_mono(left)
            return self._sbs_or_mono(Image.open(path))
        except Exception as e:  # noqa: BLE001 - surface load errors on the panel
            return self._error([f"Could not open photo:", os.path.basename(path), str(e)])

    def _sbs_or_mono(self, img) -> Panel:
        aspect = img.width / max(1, img.height)
        mode = "sbs" if aspect >= 1.8 else "mono"
        tex = pil_to_texture(self.ctx, img)
        w = 1.3  # inside the glasses' ~46 deg horizontal FOV at the 1.7 m focus distance
        h = w / (aspect / (2.0 if mode == "sbs" else 1.0))
        return Panel(id="photo", title="3D Photo", yaw_deg=0.0,
                     width_m=w, height_m=h, texture=tex, stereo_mode=mode)

    def _pair_panel(self, left, right) -> Panel:
        aspect = left.width / max(1, left.height)
        w, h = 1.3, 1.3 / aspect
        return Panel(id="photo", title="3D Photo", yaw_deg=0.0,
                     width_m=w, height_m=h,
                     texture=pil_to_texture(self.ctx, left),
                     texture_right=pil_to_texture(self.ctx, right),
                     stereo_mode="pair")

    def _error(self, lines) -> Panel:
        lines = list(lines) + ["", "Backspace = back to menu"]
        return Panel(id="photo", title="3D Photo", yaw_deg=0.0, width_m=1.3, height_m=0.73,
                     texture=message_texture(self.ctx, lines), stereo_mode="mono")

    def panel(self) -> Panel:
        return self._panel

    def close(self) -> None:
        for t in (self._panel.texture, self._panel.texture_right):
            try:
                if t is not None:
                    t.release()
            except Exception:
                pass
