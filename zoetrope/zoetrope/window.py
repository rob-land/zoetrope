"""GLFW window + input. Two modes:

  * glasses  — borderless fullscreen on the XREAL monitor (matched by name/resolution),
               giving a real 3840x1080 SBS surface.
  * preview  — a normal desktop window (default 1920x540) that shows the same SBS output
               scaled down, so you can develop without the glasses.

Emits a tiny set of high-level input events the shell understands.
"""
from __future__ import annotations

from dataclasses import dataclass

# High-level events
EV_QUIT = "quit"
EV_RECENTER = "recenter"
EV_PREV = "prev"
EV_NEXT = "next"
EV_UP = "up"          # app mode: push the window farther away
EV_DOWN = "down"      # app mode: pull it closer
EV_ACTIVATE = "activate"
EV_BACK = "back"


@dataclass
class WindowConfig:
    mode: str = "preview"          # "preview" | "glasses"
    monitor_name: str | None = None
    width: int = 1920
    height: int = 540
    title: str = "zoetrope"


class Window:
    def __init__(self, cfg: WindowConfig):
        import glfw  # lazy
        self.glfw = glfw
        self.cfg = cfg
        self._events: list[str] = []
        self._chars: list[str] = []
        # While True (an app that accepts_text is open) most keys become text for
        # the app: printables + Enter/Backspace/Tab/Ctrl-chords are delivered via
        # poll_chars(), and Esc means "back" instead of "quit".
        self.text_mode = False
        if not glfw.init():
            raise RuntimeError("glfw.init() failed")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)

        monitor = None
        w, h = cfg.width, cfg.height
        if cfg.mode == "glasses":
            monitor = self._pick_monitor(cfg.monitor_name)
            if monitor:
                vm = glfw.get_video_mode(monitor)
                w, h = vm.size.width, vm.size.height
                glfw.window_hint(glfw.RED_BITS, vm.bits.red)
                glfw.window_hint(glfw.REFRESH_RATE, vm.refresh_rate)

        self.win = glfw.create_window(w, h, cfg.title, monitor, None)
        if not self.win:
            glfw.terminate()
            raise RuntimeError("glfw.create_window() failed")
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        glfw.set_key_callback(self.win, self._on_key)
        glfw.set_char_callback(self.win, self._on_char)

    def _pick_monitor(self, name: str | None):
        glfw = self.glfw
        monitors = glfw.get_monitors()
        if name:
            for mon in monitors:
                if glfw.get_monitor_name(mon).decode(errors="ignore") == name:
                    return mon
        # Fallback: a 3840x1080-ish monitor that isn't the primary.
        primary = glfw.get_primary_monitor()
        for mon in monitors:
            vm = glfw.get_video_mode(mon)
            if vm.size.width >= 3200 and vm.size.height <= 1200 and mon != primary:
                return mon
        return monitors[-1] if monitors else None

    def _on_char(self, win, codepoint):
        if self.text_mode:
            self._chars.append(chr(codepoint))

    def _on_key(self, win, key, scancode, action, mods):
        glfw = self.glfw
        if action != glfw.PRESS and action != glfw.REPEAT:
            return
        if self.text_mode:
            # Keys the char callback doesn't cover; arrows stay window-manipulation.
            if key == glfw.KEY_ESCAPE:
                self._events.append(EV_BACK)
            elif key == glfw.KEY_ENTER:
                self._chars.append("\r")
            elif key == glfw.KEY_BACKSPACE:
                self._chars.append("\x7f")
            elif key == glfw.KEY_TAB:
                self._chars.append("\t")
            elif (mods & glfw.MOD_CONTROL) and glfw.KEY_A <= key <= glfw.KEY_Z:
                self._chars.append(chr(key - glfw.KEY_A + 1))   # ^A..^Z incl. ^C/^D
            elif key in (glfw.KEY_LEFT, glfw.KEY_RIGHT, glfw.KEY_UP, glfw.KEY_DOWN):
                self._events.append({glfw.KEY_LEFT: EV_PREV, glfw.KEY_RIGHT: EV_NEXT,
                                     glfw.KEY_UP: EV_UP, glfw.KEY_DOWN: EV_DOWN}[key])
            elif key == glfw.KEY_R and (mods & glfw.MOD_CONTROL):
                self._events.append(EV_RECENTER)
            return
        mapping = {
            glfw.KEY_ESCAPE: EV_QUIT,
            glfw.KEY_R: EV_RECENTER,
            glfw.KEY_LEFT: EV_PREV,
            glfw.KEY_RIGHT: EV_NEXT,
            glfw.KEY_UP: EV_UP,
            glfw.KEY_DOWN: EV_DOWN,
            glfw.KEY_ENTER: EV_ACTIVATE,
            glfw.KEY_SPACE: EV_ACTIVATE,
            glfw.KEY_BACKSPACE: EV_BACK,
        }
        ev = mapping.get(key)
        if ev:
            self._events.append(ev)

    def make_gl_context(self):
        import moderngl
        return moderngl.create_context()

    def get_proc_address(self, name):
        """For libmpv's OpenGL render context (python-mpv get_proc_address callback)."""
        n = name.decode() if isinstance(name, bytes) else name
        return self.glfw.get_proc_address(n)

    def framebuffer_size(self) -> tuple[int, int]:
        return self.glfw.get_framebuffer_size(self.win)

    def poll(self) -> list[str]:
        self.glfw.poll_events()
        if self.glfw.window_should_close(self.win):
            self._events.append(EV_QUIT)
        evs, self._events = self._events, []
        return evs

    def poll_chars(self) -> str:
        """Text typed since the last call (only fills while text_mode is on)."""
        chars, self._chars = self._chars, []
        return "".join(chars)

    def swap(self) -> None:
        self.glfw.swap_buffers(self.win)

    def close(self) -> None:
        self.glfw.set_window_should_close(self.win, True)
        self.glfw.terminate()
