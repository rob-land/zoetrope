"""Bridge to the shared suite provider layer (suite_providers.aio).

The shell's rails are fed from two places: the local ripsaw-style
library scan (:mod:`zoetrope.library`, synchronous and instant) and —
when configured — the same async provider stack couch drives
(Jellyfin today). The hub owns a daemon asyncio loop so the glfw frame
loop never blocks on the network; results arrive via a thread-safe
callback and the shell rebuilds its rails when they land.

Configuration (``~/.config/zoetrope/config.json``)::

    {"jellyfin": {"server_url": "http://server:8096",
                  "access_token": "...", "user_id": "..."}}

Obtaining a token is manual for now (couch's Quick Connect flow will
be shared later). No config → local-only, exactly as before.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass

STREAM_DIRECT = {"mono", "sbs-full", "sbs-half"}


def config_path() -> str:
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(cfg, "zoetrope", "config.json")


def jellyfin_config(path: str | None = None) -> dict | None:
    """The jellyfin block, or None when absent/incomplete."""
    try:
        with open(path or config_path(), "rb") as f:
            jf = json.load(f).get("jellyfin") or {}
    except Exception:
        return None
    if all(jf.get(k) for k in ("server_url", "access_token", "user_id")):
        return jf
    return None


def jellyfin_server_url(path: str | None = None) -> str | None:
    """server_url from a partial jellyfin block (pre-pairing)."""
    try:
        with open(path or config_path(), "rb") as f:
            return (json.load(f).get("jellyfin") or {}).get("server_url")
    except Exception:
        return None


def save_jellyfin_config(creds: dict, path: str | None = None) -> None:
    """Merge paired credentials into the config file, preserving any
    other top-level keys."""
    dest = path or config_path()
    try:
        with open(dest, "rb") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["jellyfin"] = {
        "server_url": creds.get("server_url"),
        "access_token": creds.get("access_token"),
        "user_id": creds.get("user_id"),
    }
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, dest)


def synth_report(item) -> dict:
    """A stereoscope-probe-shaped report for a network MediaItem.

    The server's stereo hint replaces byte-level probing (we can't
    cheaply probe over HTTP). Packed SBS and 2D play directly; formats
    that need local composition (TAB/MV-HEVC) or decode (MVC) are
    honest about it rather than guessing.
    """
    fmt = item.stereo.format.value
    if fmt in STREAM_DIRECT:
        playback = {"type": "direct"}
    else:
        playback = {
            "type": "unsupported",
            "reason": (f"This title is {fmt} on the server — play it from "
                       "a local copy, or re-archive as Full-SBS for "
                       "streaming playback."),
            "can_play_2d": True,
        }
    return {"kind": "video", "format": fmt, "playback": playback,
            "width": None, "height": None,
            "target": {"width": 3840, "height": 1080}}


@dataclass(frozen=True)
class RailEntry:
    """One card on a shell rail, local or network."""
    title: str
    year: int | None = None
    path: str | None = None        # local file (plays via stereoscope probe)
    url: str | None = None         # network stream (plays via synth report)
    poster: str | None = None      # local file path (posters are cached)
    report: dict | None = None     # pre-made probe report for network items
    progress: float | None = None  # 0..1 resume fraction


def _poster_cache_dir() -> str:
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "zoetrope", "posters")


class ProviderHub:
    """Owns the asyncio loop thread and the configured providers."""

    _UNSET = object()

    def __init__(self, config=_UNSET):
        self._jf_config = (jellyfin_config() if config is ProviderHub._UNSET
                           else config)
        # A server_url alone (no token yet) still starts the loop so
        # Quick Connect pairing can run.
        self._server = (self._jf_config or {}).get("server_url")             or jellyfin_server_url()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._provider = None
        if self.enabled or self._server:
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._loop.run_forever,
                             name="zoetrope-providers", daemon=True).start()

    @property
    def enabled(self) -> bool:
        return self._jf_config is not None

    @property
    def has_server(self) -> bool:
        return bool(self._server)

    @property
    def server_name(self) -> str | None:
        return getattr(self, "_server_name", None)

    def start_discovery(self, deliver) -> None:
        """No config at all? Find the server ourselves (Jellyfin UDP
        broadcast via the shared suite implementation). On a find the
        hub gains a server (Connect tile appears); ``deliver({})``
        nudges the shell to rebuild its rails."""
        if self.enabled or self._server:
            return
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._loop.run_forever,
                             name="zoetrope-providers", daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._discover(deliver), self._loop)

    async def _discover(self, deliver) -> None:
        try:
            from suite_providers.aio.jellyfin import discover
            servers = await discover(timeout=2.5)
        except Exception:
            return
        if servers and not self._server:
            self._server = servers[0].url
            self._server_name = servers[0].name
            deliver({})

    def quick_connect(self, deliver) -> None:
        """Pair with Jellyfin via Quick Connect (no typing in-glasses).

        ``deliver(dict)`` receives ``{"state": "code", "code": ...}``,
        then ``{"state": "done"}`` (credentials saved to the config and
        the hub becomes enabled) or ``{"state": "error", ...}``.
        """
        if self._loop is None or not self._server:
            deliver({"state": "error",
                     "message": "No jellyfin.server_url configured."})
            return
        asyncio.run_coroutine_threadsafe(self._quick_connect(deliver),
                                         self._loop)

    async def _quick_connect(self, deliver) -> None:
        try:
            from suite_providers import SourceConfig
            from suite_providers.aio import JellyfinProvider

            if self._provider is None:
                self._provider = JellyfinProvider()
                self._provider.configure(SourceConfig(
                    id="jellyfin-zoetrope", provider="jellyfin",
                    display_name="Jellyfin",
                    config={"server_url": self._server}))
            p = self._provider
            if not await p.quick_connect_enabled():
                deliver({"state": "error", "message":
                         "Quick Connect is disabled on the server "
                         "(enable it in the Jellyfin dashboard)."})
                return
            init = await p.quick_connect_initiate()
            if not init:
                deliver({"state": "error",
                         "message": "Could not start Quick Connect."})
                return
            deliver({"state": "code", "code": init["code"]})
            for _ in range(90):
                await asyncio.sleep(2.0)
                if await p.quick_connect_poll(init["secret"]):
                    status = await p.quick_connect_complete(init["secret"])
                    if status.ok and status.credentials:
                        creds = dict(status.credentials)
                        creds["server_url"] = self._server
                        save_jellyfin_config(creds)
                        self._jf_config = {
                            "server_url": self._server,
                            "access_token": creds.get("access_token"),
                            "user_id": creds.get("user_id"),
                        }
                        deliver({"state": "done"})
                    else:
                        deliver({"state": "error",
                                 "message": status.message or "Sign-in failed."})
                    return
            deliver({"state": "error", "message": "Pairing timed out."})
        except Exception as e:
            deliver({"state": "error", "message": str(e)})

    def refresh_home(self, deliver) -> None:
        """Fetch resume + movie rails; ``deliver(dict)`` is called from
        the hub thread (pass a Queue.put)."""
        if not self.enabled or self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._fetch(deliver), self._loop)

    async def _fetch(self, deliver) -> None:
        try:
            from suite_providers import ContentType, SourceConfig
            from suite_providers.aio import JellyfinProvider

            if self._provider is None:
                self._provider = JellyfinProvider()
                self._provider.configure(SourceConfig(
                    id="jellyfin-zoetrope", provider="jellyfin",
                    display_name="Jellyfin",
                    config={"server_url": self._jf_config["server_url"]}))
            creds = {"access_token": self._jf_config["access_token"],
                     "user_id": self._jf_config["user_id"]}
            p = self._provider
            resume = await p.get_continue_watching(creds, limit=8)
            movies = await p.list_library(ContentType.MOVIE, creds, limit=24)
            deliver({
                "resume": [await self._entry(i) for i in resume],
                "movies": [await self._entry(i) for i in movies],
            })
        except Exception as e:  # network errors surface as an empty update
            deliver({"resume": [], "movies": [], "error": str(e)})

    async def _entry(self, item) -> RailEntry:
        stream_url = (f"{self._jf_config['server_url'].rstrip('/')}"
                      f"/Videos/{item.provider_item_id}/stream?static=true"
                      f"&api_key={self._jf_config['access_token']}")
        progress = item.progress_fraction
        return RailEntry(
            title=item.title, year=item.year,
            url=stream_url, poster=await self._poster(item),
            report=synth_report(item), progress=progress)

    async def _poster(self, item) -> str | None:
        if not item.poster_url:
            return None
        os.makedirs(_poster_cache_dir(), exist_ok=True)
        dest = os.path.join(_poster_cache_dir(),
                            f"{item.provider_item_id}.jpg")
        if os.path.exists(dest):
            return dest
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    item.poster_url,
                    params={"api_key": self._jf_config["access_token"]})
                r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            return dest
        except Exception:
            return None
