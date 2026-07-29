"""Jellyfin Quick Connect pairing panel (zero-typing in-glasses flow).

Shows the pairing code big; the user approves it from Jellyfin on
their phone/desktop (Settings → Quick Connect). On success the hub
saves credentials and the shell's rails refresh on their own.
"""
from __future__ import annotations

import queue

from ..scene import Panel
from .base import App, message_texture


class QuickConnectApp(App):
    id = "jellyfin-connect"
    title = "Connect Jellyfin"

    def __init__(self, ctx, hub):
        self.ctx = ctx
        self._events: queue.Queue = queue.Queue()
        self._panel = self._message(["Contacting the server…"])
        hub.quick_connect(self._events.put)

    def _message(self, lines: list[str]) -> Panel:
        return Panel(id=self.id, title=self.title, yaw_deg=0.0,
                     width_m=1.3, height_m=0.73,
                     texture=message_texture(self.ctx, lines),
                     stereo_mode="mono")

    def update(self, dt: float) -> None:
        try:
            while True:
                ev = self._events.get_nowait()
                state = ev.get("state")
                if state == "code":
                    self._panel = self._message([
                        "Quick Connect code:", "",
                        f"        {ev['code']}", "",
                        "Approve it in Jellyfin on your phone:",
                        "Settings → Quick Connect.",
                    ])
                elif state == "done":
                    self._panel = self._message([
                        "Connected!", "",
                        "Your server's rails will appear on the",
                        "launcher. Backspace to go back.",
                    ])
                else:
                    self._panel = self._message([
                        "Pairing failed:", ev.get("message", ""),
                        "", "Backspace = back to menu",
                    ])
        except queue.Empty:
            pass

    def panel(self) -> Panel:
        return self._panel
