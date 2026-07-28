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


class MovieApp(App):
    id = "movie"
    title = "3D Movie"

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
            # Keep the panel inside the glasses' ~46 deg horizontal FOV
            # (1.3 m at the 1.7 m focus distance is ~42 deg).
            pw = 1.3
            return Panel(id="movie", title="3D Movie", yaw_deg=0.0,
                         width_m=pw, height_m=pw / aspect,
                         texture=self._tex, stereo_mode=self.stereo_mode)
        except Exception as e:  # noqa: BLE001
            return self._error(["mpv init failed:", str(e)])

    def update(self, dt: float) -> None:
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
