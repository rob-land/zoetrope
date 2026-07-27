"""A floating terminal panel: $SHELL on a pty, VT100-emulated by pyte, rendered
to a texture. The single highest-value native app for a face-worn display —
private, any-size, works lying on the couch. (`pip install -e '.[term]'`.)

Split for testability: `TermSession` owns the pty + pyte screen (no GL, unit-
testable); `TermApp` wraps it in the shell's App interface and draws it with
Pillow. Text reaches us via Shell.on_text() -> write_input() (see window.py's
text_mode routing: printable chars, Enter, Backspace, Tab, Ctrl+A..Z).
"""
from __future__ import annotations

import fcntl
import os
import pty
import signal
import struct
import termios

from ..scene import Panel
from .base import App, _load_font, pil_to_texture

COLS, ROWS = 100, 30
CELL_W, CELL_H = 10, 20        # pixels per character cell at font size 16
PAD = 12

FG = (220, 230, 238, 255)
BG = (10, 14, 20, 242)
CURSOR = (120, 200, 220, 255)


def _load_mono(size: int):
    from PIL import ImageFont
    for path in (
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return _load_font(size)


class TermSession:
    """$SHELL on a pty feeding a pyte screen. Pure logic + OS, no GL."""

    def __init__(self, cols: int = COLS, rows: int = ROWS, argv=None):
        import pyte
        self.cols, self.rows = cols, rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        argv = argv or [os.environ.get("SHELL", "/bin/sh")]
        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # child
            os.environ["TERM"] = "linux"
            os.execvp(argv[0], argv)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0))
        fl = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        self.alive = True

    def pump(self) -> bool:
        """Drain pty output into the emulator. True if the screen changed."""
        changed = False
        while True:
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            except OSError:          # child exited, pty closed
                self.alive = False
                break
            if not data:
                self.alive = False
                break
            self.stream.feed(data)
            changed = True
        return changed or bool(self.screen.dirty)

    def write(self, text: str) -> None:
        if self.alive:
            try:
                os.write(self.fd, text.encode())
            except OSError:
                self.alive = False

    def text_lines(self) -> list[str]:
        return [self.screen.display[i] for i in range(self.rows)]

    def close(self) -> None:
        self.alive = False
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.kill(self.pid, signal.SIGHUP)
            os.waitpid(self.pid, os.WNOHANG)
        except (OSError, ChildProcessError):
            pass


def render_screen(screen, font=None):
    """pyte screen -> PIL image (plain single-color text + block cursor)."""
    from PIL import Image, ImageDraw
    font = font or _load_mono(16)
    w = screen.columns * CELL_W + 2 * PAD
    h = screen.lines * CELL_H + 2 * PAD
    img = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(img)
    for row in range(screen.lines):
        d.text((PAD, PAD + row * CELL_H), screen.display[row], font=font, fill=FG)
    cx = PAD + screen.cursor.x * CELL_W
    cy = PAD + screen.cursor.y * CELL_H
    d.rectangle([cx, cy, cx + CELL_W - 1, cy + CELL_H - 1], outline=CURSOR, width=2)
    screen.dirty.clear()
    return img


class TermApp(App):
    id = "term"
    title = "Terminal"
    accepts_text = True

    def __init__(self, ctx):
        self.ctx = ctx
        self.session = TermSession()
        self._font = _load_mono(16)
        img = render_screen(self.session.screen, self._font)
        self._size = img.size
        self._tex = pil_to_texture(ctx, img)
        self._panel = Panel(
            id="term", title="Terminal",
            yaw_deg=0.0, width_m=1.15,
            height_m=1.15 * img.size[1] / img.size[0],
            texture=self._tex, stereo_mode="mono")

    def panel(self) -> Panel:
        return self._panel

    def update(self, dt: float) -> None:
        if self.session.pump():
            img = render_screen(self.session.screen, self._font)
            self._tex.write(img.tobytes())
            self._tex.build_mipmaps()

    def write_input(self, text: str) -> None:
        self.session.write(text)

    def close(self) -> None:
        self.session.close()
