"""3D movie player, backed by libmpv (any codec: HEVC, MV-HEVC, H.264, etc.).

mpv renders each frame into an offscreen FBO whose colour texture is placed on the panel.
For a side-by-side 3D movie, set stereo_mode="sbs" and each eye samples its half; for a
2D movie use "mono". Requires libmpv + the `python-mpv` package; if missing, the panel
shows an instructional message instead of crashing.

This is the most hardware/driver-dependent module — it needs a live GL context and libmpv,
so it can't be exercised headless. The FBO/mpv-render wiring follows the standard
`MpvRenderContext(api_type="opengl")` pattern.
"""
from __future__ import annotations

import os
import subprocess

from .. import library
from ..scene import Panel
from .base import App, message_texture


ORNAMENT_LINGER_S = 2.5      # transport auto-hides after this idle time


def fmt_time(seconds: float | None) -> str:
    """mm:ss / h:mm:ss for the transport bar (pure; unit-tested)."""
    if seconds is None:
        return "--:--"
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    mn, sec = divmod(rem, 60)
    return f"{h}:{mn:02d}:{sec:02d}" if h else f"{mn}:{sec:02d}"


def ornament_visible(shown_at: float | None, now: float,
                     linger: float = ORNAMENT_LINGER_S) -> bool:
    """Pure visibility rule: shown for `linger` seconds after the last
    transport input, then auto-hidden (doc 17 §5)."""
    return shown_at is not None and (now - shown_at) < linger


class MovieApp(App):
    id = "movie"
    title = "3D Movie"
    handles_nav = True           # prev/next seek instead of resizing
    # Open the screen well back from the launcher plane — at 1.7 m the
    # cinema canvas reads as in-your-face on the fixed-focus optics
    # (hardware feedback: "way too close, several steps back").
    preferred_dist = 2.7

    def __init__(self, ctx, path: str, get_proc_address, stereo_mode: str = "sbs",
                 fbo_size=(1920, 1080), probe: dict | None = None):
        self.ctx = ctx
        self.path = path
        self.stereo_mode = stereo_mode
        self._mpv = None
        self._render = None
        self._fbo = None
        self._tex = None
        self._stream_proc: subprocess.Popen | None = None
        self._aspect: float | None = None
        self._orn_shown_at: float | None = None
        self._orn_panel = None
        self._orn_tex = None
        self._panel = self._open(path, get_proc_address, fbo_size, probe)

    def _open(self, path, get_proc_address, fbo_size, report) -> Panel:
        """Decide how to play: stereoscope-probed files stream composed
        Full-SBS through `stereoscope stream` when needed and play packed
        files directly; unprobed files keep the caller's stereo/fbo."""
        media = path
        if report is None:
            report = library.probe(path)
        if report is not None:
            pb = report.get("playback") or {}
            if pb.get("type") == "unsupported":
                lines = ["This file can't play in 3D:", pb.get("reason", "")]
                return self._error([ln for chunk in lines for ln in _wrap(chunk)])
            fbo_size, self.stereo_mode, self._aspect = library.playback_geometry(report)
            if pb.get("type") == "stream":
                cmd = library.stream_command(path)
                if cmd is None:
                    return self._error([
                        "This format needs the stereoscope engine,",
                        "which isn't installed:",
                        "cargo install --path ~/projects/stereoscope",
                        "(or set STEREOSCOPE_BIN)"])
                self._stream_proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                media = f"fd://{self._stream_proc.stdout.fileno()}"
        return self._init_mpv(media, get_proc_address, fbo_size)

    def _init_mpv(self, path, get_proc_address, fbo_size) -> Panel:
        if "://" not in path and not os.path.exists(path):
            return self._error([f"File not found:", os.path.basename(path)])
        try:
            import mpv  # python-mpv (needs libmpv.so)
        except (ImportError, OSError, AttributeError):
            # python-mpv raises OSError when libmpv.so itself is missing.
            return self._error(["libmpv / python-mpv not installed:",
                                 "sudo dnf install mpv-libs",
                                 "pip install python-mpv"])
        try:
            w, h = fbo_size
            self._tex = self.ctx.texture((w, h), 4)
            self._fbo = self.ctx.framebuffer(color_attachments=[self._tex])

            self._mpv = mpv.MPV(vo="libmpv", hwdec="auto")
            # python-mpv needs a ctypes CFUNCTYPE, signature (ctx, name) -> address.
            # Keep a reference on self: ctypes callbacks must outlive the render ctx.
            self._gpa = mpv.MpvGlGetProcAddressFn(
                lambda _ctx, name: get_proc_address(name) or 0)
            self._render = mpv.MpvRenderContext(
                self._mpv, "opengl",
                opengl_init_params={"get_proc_address": self._gpa},
            )
            self._mpv.play(path)
            aspect = self._aspect or ((w / 2) / h if self.stereo_mode == "sbs" else w / h)
            # Cinema default: the screen subtends ~60 deg — Carmack's
            # Netflix-on-Go number; bigger magnifies compression and
            # forces head-scanning (doc 17 §5). At the 1.7 m focus
            # distance: 2 * 1.7 * tan(30 deg) ~= 1.96 m. The user's
            # existing zoom keys scale toward Large/Max from here.
            import math as _math
            pw = 2.0 * 1.7 * _math.tan(_math.radians(30.0))
            self.wants_void = True
            panel = Panel(id="movie", title="3D Movie", yaw_deg=0.0,
                          width_m=pw, height_m=pw / aspect,
                          texture=self._tex, stereo_mode=self.stereo_mode)
            if self.stereo_mode == "sbs":
                # Feathered frame hides stereo-window violations at the
                # screen edges (~20 dmm at this size).
                panel.data["feather"] = 0.012
            return panel
        except Exception as e:  # noqa: BLE001
            return self._error(["mpv init failed:", str(e)])

    def update(self, dt: float) -> None:
        import time
        if (self._orn_shown_at is not None
                and ornament_visible(self._orn_shown_at, time.monotonic())):
            self._orn_accum = getattr(self, "_orn_accum", 0.0) + dt
            if self._orn_accum >= 1.0:
                self._orn_accum = 0.0
                self._refresh_ornament()
        # Pull a fresh frame into our FBO if mpv has one ready.
        if self._render is None or self._fbo is None:
            return
        if self._render.update():
            w, h = self._tex.size
            # flip_y=False: the renderer's quad UVs are top-left origin (PIL
            # convention), and mpv's unflipped FBO output matches it (verified
            # against mpv screenshot_raw orientation).
            self._render.render(flip_y=False, opengl_fbo={
                "w": w, "h": h, "fbo": self._fbo.glo,
            })

    # -- transport (doc 17 §5) ----------------------------------------------

    def on_activate(self) -> None:
        """Play/pause; summons the transport ornament."""
        if self._mpv is not None:
            try:
                self._mpv.pause = not self._mpv.pause
            except Exception:
                pass
        self._show_ornament()

    def nav(self, delta: int) -> None:
        """Seek +-10 s. (Distance via up/down is the seat control; the
        screen size stays at its cinema preset.)"""
        if self._mpv is not None:
            try:
                self._mpv.seek(10 * delta, "relative")
            except Exception:
                pass
        self._show_ornament()

    def _show_ornament(self) -> None:
        import time
        self._orn_shown_at = time.monotonic()
        self._refresh_ornament()

    def ornament(self) -> Panel | None:
        import time
        if not ornament_visible(self._orn_shown_at, time.monotonic()):
            return None
        return self._orn_panel

    def _refresh_ornament(self) -> None:
        """(Re)draw the transport bar texture: play state, progress in
        the accent color, timecodes. Chrome outside the picture."""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return
        w, h = 1024, 96
        img = Image.new("RGBA", (w, h), (255, 255, 255, 31))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([2, 2, w - 2, h - 2], radius=20,
                            outline=(255, 255, 255, 89), width=2)
        pos = dur = None
        paused = False
        if self._mpv is not None:
            try:
                pos = self._mpv.time_pos
                dur = self._mpv.duration
                paused = bool(self._mpv.pause)
            except Exception:
                pass
        # play/pause glyph
        gx, gy, gs = 30, 24, 48
        if paused:
            d.polygon([(gx, gy), (gx, gy + gs), (gx + gs * 0.8, gy + gs / 2)],
                      fill=(255, 255, 255, 255))
        else:
            bw = int(gs * 0.28)
            d.rectangle([gx, gy, gx + bw, gy + gs], fill=(255, 255, 255, 255))
            d.rectangle([gx + gs * 0.5, gy, gx + gs * 0.5 + bw, gy + gs],
                        fill=(255, 255, 255, 255))
        # progress track + accent fill
        tx0, tx1, ty = 110, w - 190, h // 2
        d.rounded_rectangle([tx0, ty - 4, tx1, ty + 4], radius=4,
                            fill=(255, 255, 255, 60))
        if pos is not None and dur:
            fx = tx0 + (tx1 - tx0) * min(1.0, pos / dur)
            d.rounded_rectangle([tx0, ty - 4, fx, ty + 4], radius=4,
                                fill=(53, 132, 228, 255))
        font = _load_ornament_font()
        d.text((tx1 + 16, ty - 16), f"{fmt_time(pos)} / {fmt_time(dur)}",
               font=font, fill=(255, 255, 255, 220))
        if self._orn_tex is None:
            from .base import pil_to_texture
            self._orn_tex = pil_to_texture(self.ctx, img)
            self._orn_panel = Panel(
                id="movie-transport", title="transport", yaw_deg=0.0,
                width_m=1.35, height_m=0.13,
                texture=self._orn_tex, stereo_mode="mono")
        else:
            self._orn_tex.write(img.convert("RGBA").tobytes())

    def _error(self, lines) -> Panel:
        lines = list(lines) + ["", "Backspace = back to menu"]
        return Panel(id="movie", title="3D Movie", yaw_deg=0.0, width_m=1.3, height_m=0.73,
                     texture=message_texture(self.ctx, lines), stereo_mode="mono")

    def panel(self) -> Panel:
        return self._panel

    def close(self) -> None:
        try:
            if self._render is not None:
                self._render.free()
            if self._mpv is not None:
                self._mpv.terminate()
        except Exception:
            pass
        if self._stream_proc is not None:
            try:
                self._stream_proc.terminate()
                self._stream_proc.wait(timeout=5)
            except Exception:
                try:
                    self._stream_proc.kill()
                except Exception:
                    pass
            self._stream_proc = None


def _load_ornament_font():
    from .base import _load_font
    return _load_font(30)


def _wrap(text: str, width: int = 40) -> list[str]:
    """Naive word wrap for error-panel lines."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]
