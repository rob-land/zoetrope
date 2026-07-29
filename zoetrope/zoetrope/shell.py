"""The shell: a launcher of tiles on a cylinder; activating a tile opens an app panel.

State machine: LAUNCHER <-> APP. In LAUNCHER the focused tile follows your head (gaze),
or the arrow keys in preview. Enter opens it; Backspace returns.
"""
from __future__ import annotations

import glob
import math
import os
import queue
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

from . import mathutil as m
from .scene import CylinderLayout, LauncherScene, Panel, _wrap180
from .stereo import HeadPose, head_yaw
from .apps.base import App, clock_image, make_tile, pil_to_texture
from .apps.photo import GalleryApp, PhotoApp
from . import library
from .apps.movie import MovieApp

LAUNCHER, APP = "launcher", "app"

# After keyboard navigation, gaze re-takes selection only once the head has turned
# this far from where it was at the keypress. A static tracker (stub / no driver)
# therefore never overrides the keyboard.
GAZE_RESUME_DEG = 8.0

# Nebula-style focused-window manipulation: multiplicative size steps and additive
# depth steps, clamped so the panel can't fill the view or vanish into the horizon.
APP_SCALE_STEP = 1.12
APP_SCALE_RANGE = (0.45, 2.5)
APP_DIST_STEP = 0.25
APP_DIST_RANGE = (0.9, 4.0)
APP_DIST_DEFAULT = 1.7


def _panel_scale(width_m: float, height_m: float):
    mat = m.mat4_identity()
    mat[0] = width_m
    mat[5] = height_m
    return mat


def _clamp(v: float, lo_hi: tuple[float, float]) -> float:
    return max(lo_hi[0], min(lo_hi[1], v))


def focus_model(width_m: float, height_m: float,
                distance: float = APP_DIST_DEFAULT, scale: float = 1.0):
    """Model matrix for the focused app panel: straight ahead at `distance`,
    sized by the panel dimensions times a user zoom `scale`."""
    s = m.mat4_identity()
    s[0] = width_m * scale
    s[5] = height_m * scale
    return m.mat4_mul(m.mat4_translate((0.0, 0.0, -distance)), s)


def gaze_may_select(lock_yaw_deg: float | None, yaw_deg: float,
                    threshold_deg: float = GAZE_RESUME_DEG) -> bool:
    """True when gaze selection is allowed: no keyboard lock, or head moved past it."""
    return lock_yaw_deg is None or abs(_wrap180(yaw_deg - lock_yaw_deg)) > threshold_deg

_PHOTO_EXTS = (".mpo", ".jpg", ".jpeg", ".png", ".heic", ".heif")
_MOVIE_EXTS = (".mp4", ".mkv", ".mov", ".webm", ".m4v")


def _find_media(media_dir: str, exts) -> str | None:
    """Prefer files hinting at 3D ('sbs'/'3d'/'stereo') so the demo shows stereo content."""
    files = [p for p in sorted(glob.glob(os.path.join(media_dir, "*")))
             if os.path.splitext(p)[1].lower() in exts]
    if not files:
        return None
    for p in files:
        low = os.path.basename(p).lower()
        if any(h in low for h in ("sbs", "3d", "stereo", "_ou", "half")):
            return p
    return files[0]


def _photo_thumb(path: str):
    """Load a small PIL preview; SBS-looking images (aspect > 2) keep the left eye."""
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()
        if img.width > 2.0 * img.height:
            img = img.crop((0, 0, img.width // 2, img.height))
        img.thumbnail((512, 512))
        return img
    except Exception:
        return None


def _thumbs_cache_dir() -> str:
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "zoetrope", "thumbs")


def _movie_thumb(path: str):
    """Grab a frame with ffmpeg (cached under the XDG cache);
    None when unavailable."""
    out = os.path.join(_thumbs_cache_dir(), os.path.basename(path) + ".jpg")
    try:
        if not os.path.exists(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            for ss in ("30", "5", "0"):   # long samples first, then short clips
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", path,
                     "-frames:v", "1", "-vf", "scale=800:-2", out],
                    timeout=30, check=False)
                if os.path.exists(out) and os.path.getsize(out) > 0:
                    break
        return _photo_thumb(out)          # reuses the SBS left-eye crop
    except Exception:
        return None


def _entry_thumb(entry):
    """Tile art for a shared-provider RailEntry (cached poster file)."""
    if entry.poster:
        return _photo_thumb(entry.poster)
    return None


def _poster_thumb(mv):
    """Tile art for a library movie: Jellyfin poster art when present,
    else a grabbed frame."""
    if mv.poster:
        thumb = _photo_thumb(mv.poster)
        if thumb is not None:
            return thumb
    return _movie_thumb(mv.path)


def _uniform_scale(s: float):
    mat = m.mat4_identity()
    mat[0] = mat[5] = mat[10] = s
    return mat


@dataclass
class Tile:
    id: str
    title: str
    subtitle: str
    open: Callable[[], App | None]
    icon: str | None = None
    thumb: object | None = None      # PIL image for the card background
    poster: bool = False             # 2:3 poster card instead of 16:10 tile


class Shell:
    # How many movie tiles the arc holds comfortably; the library scan
    # itself is unbounded, this only caps the page.
    MOVIE_PAGE_LIMIT = 24

    def __init__(self, ctx, media_dir: str, get_proc_address,
                 library_dir: str | None = None, hub=None):
        self.ctx = ctx
        self.media_dir = media_dir
        self.get_proc_address = get_proc_address
        self.library_roots = library.library_roots(media_dir, library_dir)
        self.mode = LAUNCHER
        self.current: App | None = None
        self.scene = LauncherScene(CylinderLayout(radius_m=1.9, arc_span_deg=80.0))
        self._nav_this_frame = False
        self._gaze_lock_yaw: float | None = None
        self._app_scale = 1.0                    # focused-window user zoom
        self._app_dist = APP_DIST_DEFAULT        # focused-window distance (m)
        self._page = "home"
        # Shared-provider rails (suite_providers.aio via ProviderHub):
        # fetched in the background, delivered through a queue the frame
        # loop drains — network never blocks a frame.
        self.hub = hub
        self._net: dict = {"resume": [], "movies": []}
        self._pending_rails: queue.Queue = queue.Queue()
        if hub is not None and hub.enabled:
            hub.refresh_home(self._pending_rails.put)
        self._rows = self._build_home_rows()
        self._tiles = [t for r in self._rows for t in r]
        self._install_tiles()
        self._clock = self._install_clock()

    # --- tiles -------------------------------------------------------------
    # Home rail geometry (doc 17 §2): movie posters above, apps below,
    # ambient strip at the bottom edge.
    HOME_RAIL_MOVIES = 8

    def _build_home_rows(self) -> list[list[Tile]]:
        photos = library.scan_photos(self.library_roots)
        movies = library.scan_movies(self.library_roots,
                                     limit=self.HOME_RAIL_MOVIES)
        movie_sub = (f"{len(movies)} title{'s' if len(movies) != 1 else ''}"
                     if movies else "no library found")
        photo_sub = (f"{len(photos)} photo{'s' if len(photos) != 1 else ''}"
                     if photos else "no photos")
        resume = self._net.get("resume") or []
        if resume:
            # Doc 17 §8a: home's media band is the resume rail once a
            # backend provides one; the local rail is the fallback.
            movie_rail = [
                Tile(f"resume:{i}", e.title, "",
                     lambda en=e: self._open_entry(en),
                     icon="movie", thumb=_entry_thumb(e), poster=True)
                for i, e in enumerate(resume)
            ]
        else:
            movie_rail = [
                Tile(f"home-movie:{i}", mv.title, "",
                     lambda m=mv: self._open_movie(m),
                     icon="movie", thumb=_poster_thumb(mv), poster=True)
                for i, mv in enumerate(movies)
            ]
        app_rail = [
            Tile("gallery", "3D Gallery", photo_sub,
                 lambda ps=photos: GalleryApp(self.ctx, ps),
                 icon="photo",
                 thumb=_photo_thumb(photos[0].path) if photos else None),
            Tile("movies", "All Movies", movie_sub,
                 self._open_movies_page, icon="movie",
                 thumb=_poster_thumb(movies[0]) if movies else None),
            Tile("term", "Terminal", os.path.basename(os.environ.get("SHELL", "sh")),
                 self._open_term, icon="term"),
        ]
        return [r for r in (movie_rail, app_rail) if r]

    def _build_movie_tiles(self) -> list[Tile]:
        movies = library.scan_movies(self.library_roots, limit=self.MOVIE_PAGE_LIMIT)
        tiles = [Tile("_back", "‹ Back", "launcher",
                      self._open_home_page, icon=None)]
        for i, mv in enumerate(movies):
            tiles.append(Tile(
                f"movie:{i}", mv.title, os.path.basename(mv.path),
                lambda m=mv: self._open_movie(m),
                icon="movie", thumb=_poster_thumb(mv)))
        seen = {t.title for t in tiles}
        for i, e in enumerate(self._net.get("movies") or []):
            if e.title in seen or len(tiles) > self.MOVIE_PAGE_LIMIT:
                continue
            tiles.append(Tile(
                f"net-movie:{i}", e.title, str(e.year or ""),
                lambda en=e: self._open_entry(en),
                icon="movie", thumb=_entry_thumb(e)))
        return tiles

    def _open_entry(self, entry) -> App | None:
        """Open a shared-provider RailEntry: network streams carry a
        server-synthesized report instead of a local probe."""
        return MovieApp(self.ctx, entry.url or entry.path,
                        self.get_proc_address, probe=entry.report)

    def _open_movie(self, mv: library.Movie) -> App | None:
        """Probe through stereoscope (3D format + how to play), then hand the
        result to MovieApp so streamed formats (MVC, MV-HEVC, TAB) go
        through `stereoscope stream` and packed files play directly."""
        report = library.probe(mv.path)
        return MovieApp(self.ctx, mv.path, self.get_proc_address, probe=report)

    def _open_movies_page(self) -> None:
        self._set_page("movies")
        return None

    def _open_home_page(self) -> None:
        self._set_page("home")
        return None

    def _set_page(self, page: str) -> None:
        self._page = page
        self._rows = (self._build_home_rows() if page == "home"
                      else [self._build_movie_tiles()])
        self._tiles = [t for r in self._rows for t in r]
        self._install_tiles()

    def _open_term(self):
        try:
            from .apps.term import TermApp
            return TermApp(self.ctx)
        except ImportError:
            print("[shell] terminal needs pyte:  pip install -e '.[term]'")
            return None

    # Vertical rail centers (meters at the arc). Sized so the rails and
    # the clock strip never overlap: posters [0.05..0.59], apps
    # [-0.44..-0.04], clock [-0.67..-0.53].
    ROW_Y = (0.32, -0.24)

    def _install_tiles(self) -> None:
        rows = []
        for i, tiles in enumerate(self._rows):
            y = self.ROW_Y[i] if i < len(self.ROW_Y) else -0.24 - 0.46 * (i - 1)
            panels = []
            for t in tiles:
                if t.poster:
                    w_m, h_m, tw, th = 0.36, 0.54, 340, 510
                else:
                    w_m, h_m, tw, th = 0.62, 0.40, 512, 320
                panels.append(Panel(
                    id=t.id, title=t.title, yaw_deg=0.0,
                    width_m=w_m, height_m=h_m, y_m=y,
                    # Each row sits a hair nearer than the one above so
                    # any residual overlap depth-tests instead of
                    # z-fighting (co-planar quads flicker).
                    radius_bias=-0.02 * i,
                    texture=make_tile(self.ctx, t.title, t.subtitle,
                                      w=tw, h=th, icon=t.icon, thumb=t.thumb),
                    stereo_mode="mono",
                ))
            rows.append(panels)
        self.scene.set_rows(rows)

    def _install_clock(self):
        try:
            img = clock_image()
        except Exception:                 # Pillow missing: shell still works, no clock
            return None
        self._clock_tex = pil_to_texture(self.ctx, img)
        self._clock_minute = time.localtime().tm_min
        # Bottom ambient strip: up-gaze is fatiguing (doc 17 §0), so
        # ambient chrome lives below the rails, glanceable on look-down.
        return Panel(id="_clock", title="clock", yaw_deg=0.0,
                     width_m=0.48, height_m=0.14, y_m=-0.60,
                     radius_bias=-0.05,
                     texture=self._clock_tex, stereo_mode="mono")

    def _update_clock(self) -> None:
        if self._clock is None:
            return
        now = time.localtime()
        if now.tm_min != self._clock_minute:
            self._clock_minute = now.tm_min
            img = clock_image(when=now).convert("RGBA")
            self._clock_tex.write(img.tobytes())
            self._clock_tex.build_mipmaps()

    # --- events ------------------------------------------------------------
    def on_prev(self):
        """Launcher: previous tile. App: previous item (gallery-style
        apps) or shrink the window (Nebula-style)."""
        if self.mode == LAUNCHER:
            self.scene.move_selection(-1)
            self._nav_this_frame = True
        elif self.current is not None and self.current.handles_nav:
            self.current.nav(-1)
        else:
            self._app_scale = _clamp(self._app_scale / APP_SCALE_STEP, APP_SCALE_RANGE)

    def on_next(self):
        """Launcher: next tile. App: next item or grow the window."""
        if self.mode == LAUNCHER:
            self.scene.move_selection(+1)
            self._nav_this_frame = True
        elif self.current is not None and self.current.handles_nav:
            self.current.nav(+1)
        else:
            self._app_scale = _clamp(self._app_scale * APP_SCALE_STEP, APP_SCALE_RANGE)

    def on_farther(self):
        """Launcher: rail above. App: push the window away."""
        if self.mode == LAUNCHER:
            self.scene.move_row(-1)
            self._nav_this_frame = True
        elif self.mode == APP:
            self._app_dist = _clamp(self._app_dist + APP_DIST_STEP, APP_DIST_RANGE)

    def on_closer(self):
        """Launcher: rail below. App: pull the window in."""
        if self.mode == LAUNCHER:
            self.scene.move_row(+1)
            self._nav_this_frame = True
        elif self.mode == APP:
            self._app_dist = _clamp(self._app_dist - APP_DIST_STEP, APP_DIST_RANGE)

    def on_activate(self):
        if self.mode == APP and self.current is not None:
            self.current.on_activate()
            return
        if self.mode != LAUNCHER:
            return
        panel = self.scene.selected_panel
        if not panel:
            return
        tile = next((t for t in self._tiles if t.id == panel.id), None)
        if not tile:
            return
        app = tile.open()
        if app is not None:
            self.current = app
            self.mode = APP
            # Fresh window geometry per app; apps may prefer a distance
            # (movies open well back).
            self._app_scale = 1.0
            self._app_dist = _clamp(
                getattr(app, "preferred_dist", None) or APP_DIST_DEFAULT,
                APP_DIST_RANGE)

    def on_back(self):
        if self.mode == APP and self.current is not None:
            self.current.close()
            self.current = None
            self.mode = LAUNCHER
        elif self.mode == LAUNCHER and self._page != "home":
            self._set_page("home")

    def on_pointer(self, yaw_deg: float):
        """Controller ray: select like gaze, but hold the pick against head gaze
        (same lock the keyboard uses) so the two inputs don't fight."""
        if self.mode != LAUNCHER:
            return
        if self.scene.select_by_yaw(yaw_deg) >= 0:
            self._nav_this_frame = True

    # --- per-frame ---------------------------------------------------------
    def update(self, dt: float, pose: HeadPose) -> None:
        try:
            while True:
                self._net.update(self._pending_rails.get_nowait())
                if self.mode == LAUNCHER:
                    self._set_page(self._page)
        except queue.Empty:
            pass
        if self.mode == LAUNCHER:
            self._update_clock()
            yaw = math.degrees(head_yaw(pose))
            if self._nav_this_frame:
                self._gaze_lock_yaw = yaw
            elif gaze_may_select(self._gaze_lock_yaw, yaw):
                self._gaze_lock_yaw = None
                self.scene.select_by_gaze(pose)
            self._nav_this_frame = False
        elif self.current is not None:
            self.current.update(dt)

    def floor_model(self):
        rot = m.mat4_from_quat(m.q_from_axis_angle((1, 0, 0), math.radians(-90)))
        scale = m.mat4_identity()
        scale[0] = 12.0
        scale[5] = 12.0
        return m.mat4_mul(m.mat4_translate((0.0, -0.7, 0.0)), m.mat4_mul(rot, scale))

    def panels_models(self):
        if self.mode == APP and self.current is not None:
            p = self.current.panel()
            out = [(p, focus_model(p.width_m, p.height_m,
                                   self._app_dist, self._app_scale))]
            orn = self.current.ornament()
            if orn is not None:
                # Float the ornament just under the app panel's bottom
                # edge, slightly nearer the viewer (chrome outside the
                # content, never over the picture).
                dy = p.height_m * self._app_scale / 2 + orn.height_m / 2 + 0.05
                model = m.mat4_mul(
                    m.mat4_translate((0.0, -dy, -(self._app_dist - 0.05))),
                    _panel_scale(orn.width_m, orn.height_m))
                out.append((orn, model))
            return out
        out = []
        selected = self.scene.selected_panel
        for panel in self.scene.panels:
            model = self.scene.layout.model_matrix(panel)
            if panel is selected:            # gentle zoom on the focused tile
                model = m.mat4_mul(model, _uniform_scale(1.06))
            out.append((panel, model))
        if self._clock is not None:
            out.append((self._clock, self.scene.layout.model_matrix(self._clock)))
        return out

    def wants_void(self) -> bool:
        """True while the open app asked for theater purity (movie
        playback): the renderer blanks the stage layers."""
        return (self.mode == APP and self.current is not None
                and getattr(self.current, "wants_void", False))

    def wants_text(self) -> bool:
        """True while the open app consumes keyboard text (window.py switches its
        key mapping accordingly)."""
        return (self.mode == APP and self.current is not None
                and self.current.accepts_text)

    def on_text(self, text: str) -> None:
        if self.wants_text():
            self.current.write_input(text)

    def selected_id(self) -> str | None:
        if self.mode == LAUNCHER:
            p = self.scene.selected_panel
            return p.id if p else None
        return None

    def close(self):
        if self.current is not None:
            self.current.close()
