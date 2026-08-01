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
from .scene import CylinderLayout, LauncherScene, Panel, _wrap180, backdrop_mesh
from .stereo import HeadPose, head_yaw
from .apps.base import App, clock_image, make_label, make_tile, pil_to_texture
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

# Whole-slab push/pull (PgUp/PgDn or -/=): launcher cylinder radius.
SLAB_DIST_DEFAULT = 1.9


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


# --- dashboard-slab vertical rhythm (doc 17 §2b) ---------------------------
# Each rail gets a heading band above it; the bottom bar (clock) closes
# the slab. All values are meters at the cylinder.
LABEL_BAND_M = 0.06     # rail heading strip (text ~0.045 tall inside it)
ROW_GAP_M = 0.06
SLAB_Y_TOP = 0.55       # top edge of the first heading band
BAR_H_M = 0.12          # bottom (clock) bar height


def rail_rhythm(row_heights: list[float],
                y_top: float = SLAB_Y_TOP) -> tuple[list[tuple[float, float]], float]:
    """Walk the rails top-down: returns ``([(label_y, row_y), ...], bar_y)``
    — vertical centers for each rail's heading and cards, and for the
    bottom bar. Pure so the layout is testable without GL."""
    out = []
    y = y_top
    for h in row_heights:
        out.append((y - LABEL_BAND_M / 2.0, y - LABEL_BAND_M - h / 2.0))
        y -= LABEL_BAND_M + h + ROW_GAP_M
    return out, y - BAR_H_M / 2.0

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
                 library_dir: str | None = None, hub=None,
                 radius_m: float | None = None):
        self.ctx = ctx
        self.media_dir = media_dir
        self.get_proc_address = get_proc_address
        self.library_roots = library.library_roots(media_dir, library_dir)
        self.mode = LAUNCHER
        self.current: App | None = None
        self.scene = LauncherScene(CylinderLayout(
            radius_m=_clamp(radius_m or SLAB_DIST_DEFAULT,
                            self.SLAB_DIST_RANGE),
            arc_span_deg=80.0))
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
        self._net_kicked = hub is not None and hub.enabled
        if self._net_kicked:
            hub.refresh_home(self._pending_rails.put)
        elif hub is not None and not hub.has_server:
            # Nothing configured: try Jellyfin UDP discovery; a find
            # surfaces the Connect tile via a rails rebuild.
            hub.start_discovery(self._pending_rails.put)
        self._chrome: list[Panel] = []       # rail headings (non-selectable)
        self._backdrop_rev = 0               # bumped on relayout
        self._backdrop = None                # cached (rev, verts, size_m)
        self._slab = (self.SLAB_HALF_ARC_RANGE[0], -0.8, 0.6)
        self._rows = self._build_home_rows()
        self._tiles = [t for _, r in self._rows for t in r]
        self._clock = self._install_clock()
        self._install_tiles()

    # --- tiles -------------------------------------------------------------
    # Dashboard slab (doc 17 §2b, SteamVR-dashboard form): the app/source
    # rail on top, continue-watching rails below, clock in the bottom
    # bar — all on one curved glass slab.
    HOME_RAIL_MOVIES = 8
    #: slab horizontal half-arc bounds: it hugs the widest rail (short
    #: rows get a snug slab) but never exceeds what the ±40° scroll
    #: window plus the widest card can reach.
    SLAB_HALF_ARC_RANGE = (26.0, 52.0)
    #: whole-slab distance (cylinder radius) push/pull step and clamp
    SLAB_DIST_STEP = 0.15
    SLAB_DIST_RANGE = (1.3, 3.2)

    def _build_home_rows(self) -> list[tuple[str, list[Tile]]]:
        photos = library.scan_photos(self.library_roots)
        movies = library.scan_movies(self.library_roots,
                                     limit=self.HOME_RAIL_MOVIES)
        movie_sub = (f"{len(movies)} title{'s' if len(movies) != 1 else ''}"
                     if movies else "no library found")
        photo_sub = (f"{len(photos)} photo{'s' if len(photos) != 1 else ''}"
                     if photos else "no photos")
        resume = self._net.get("resume") or []
        # Top rail: apps & sources (Jellyfin now; Plex/Grayjay slot in
        # here as the shared provider layer grows).
        app_rail = []
        if self.hub is not None and self.hub.enabled:
            app_rail.append(Tile(
                "jellyfin", "Jellyfin",
                self.hub.server_name or "movies & shows",
                self._open_jellyfin_page, icon="movie",
                thumb=_entry_thumb(resume[0]) if resume else None))
        elif self.hub is not None and self.hub.has_server:
            from .apps.connect import QuickConnectApp
            app_rail.append(Tile(
                "jellyfin-connect", "Connect Jellyfin",
                self.hub.server_name or "Quick Connect",
                lambda: QuickConnectApp(self.ctx, self.hub), icon="movie"))
        app_rail += [
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
        rows: list[tuple[str, list[Tile]]] = [("Apps", app_rail)]
        # Below: one continue-watching rail per source that provides one
        # (Jellyfin resume today); the local library is the fallback so
        # the slab always has a media band.
        if resume:
            src = (self.hub.server_name if self.hub else None) or "Jellyfin"
            rows.append((f"Continue watching · {src}", [
                Tile(f"resume:{i}", e.title, "",
                     lambda en=e: self._open_entry(en),
                     icon="movie", thumb=_entry_thumb(e), poster=True)
                for i, e in enumerate(resume)
            ]))
        elif movies:
            rows.append(("Library", [
                Tile(f"home-movie:{i}", mv.title, "",
                     lambda m=mv: self._open_movie(m),
                     icon="movie", thumb=_poster_thumb(mv), poster=True)
                for i, mv in enumerate(movies)
            ]))
        return rows

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

    def _open_jellyfin_page(self) -> None:
        self._set_page("jellyfin")
        return None

    def _build_jellyfin_rows(self) -> list[tuple[str, list[Tile]]]:
        """The Jellyfin source page: that server's rails only (the
        All Movies page stays the local/merged view)."""
        name = self.hub.server_name if self.hub else None
        name = name or "Jellyfin"
        resume = self._net.get("resume") or []
        movies = self._net.get("movies") or []
        back = Tile("_back", "‹ Back", "launcher", self._open_home_page,
                    icon=None)
        rows: list[tuple[str, list[Tile]]] = []
        if resume:
            rows.append((f"Continue watching · {name}", [
                Tile(f"jf-resume:{i}", e.title, "",
                     lambda en=e: self._open_entry(en),
                     icon="movie", thumb=_entry_thumb(e), poster=True)
                for i, e in enumerate(resume)
            ]))
        rows.append((f"Movies · {name}", [back] + [
            Tile(f"jf-movie:{i}", e.title, str(e.year or ""),
                 lambda en=e: self._open_entry(en),
                 icon="movie", thumb=_entry_thumb(e), poster=True)
            for i, e in enumerate(movies)
        ]))
        return rows

    def _open_home_page(self) -> None:
        self._set_page("home")
        return None

    def _set_page(self, page: str) -> None:
        self._page = page
        if page == "home":
            self._rows = self._build_home_rows()
        elif page == "jellyfin":
            self._rows = self._build_jellyfin_rows()
        else:
            self._rows = [("All Movies", self._build_movie_tiles())]
        self._tiles = [t for _, r in self._rows for t in r]
        self._install_tiles()

    def _open_term(self):
        try:
            from .apps.term import TermApp
            return TermApp(self.ctx)
        except ImportError:
            print("[shell] terminal needs pyte:  pip install -e '.[term]'")
            return None

    def _install_tiles(self) -> None:
        """Lay the labeled rails out on the slab (doc 17 §2b): headings
        above each rail, cards below, clock parked in the bottom bar."""
        heights = [0.54 if any(t.poster for t in tiles) else 0.40
                   for _, tiles in self._rows]
        rhythm, _ = rail_rhythm(heights)
        rows = []
        for i, (label, tiles) in enumerate(self._rows):
            _, y = rhythm[i]
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
        # Rail headings (textures made once here; positioned below).
        self._chrome = []
        for i, (label, _tiles) in enumerate(self._rows):
            lab = make_label(self.ctx, label) if label else None
            if lab is None:
                continue
            tex, aspect = lab
            h_m = 0.045
            self._chrome.append(Panel(
                id=f"_label:{i}", title=label, yaw_deg=0.0,
                width_m=h_m * aspect, height_m=h_m, y_m=rhythm[i][0],
                radius_bias=0.02, texture=tex, stereo_mode="mono",
                # Chrome draws depth-test-off: a wide flat label chords
                # the curved slab and its corners dip behind the surface
                # (end-pull bows the slab in faster than the chord).
                data={"overlay": True}))
        self._layout_chrome()

    def _layout_chrome(self) -> None:
        """Geometry-only pass: slab arc, heading/clock placement, slab
        extent. Cheap (no texture work), so radius changes reuse it."""
        heights = [0.54 if any(t.poster for t in tiles) else 0.40
                   for _, tiles in self._rows]
        rhythm, bar_y = rail_rhythm(heights)
        lay = self.scene.layout
        deg_per_m = math.degrees(1.0 / lay.radius_m)
        # Slab arc: hug the widest rail. A row's reach is its full
        # centered spread or the scroll window, whichever is smaller,
        # plus half the widest card (and the focus zoom).
        half_arc = self.SLAB_HALF_ARC_RANGE[0]
        for panels in self.scene.rows:
            step = self.scene._row_step(panels)
            n = len(panels)
            card_w = max(p.width_m for p in panels) * deg_per_m
            if step * (n - 1) <= lay.arc_span_deg:
                spread = step * (n - 1) / 2.0
                margin = 3.0
            else:
                # Windowed row: hug the *visible* window (mirrors
                # _relayout_row), not the arc cap — otherwise a long
                # rail blows the slab out to maximum width while only
                # a few cards actually show. Extra margin gives the
                # peeking next card ~25-35% of visible width before the
                # rim fade cuts it.
                spread = max(1, int(lay.arc_span_deg / 2.0 / step)) * step
                margin = 0.35 * card_w + 2.0
            half_arc = max(half_arc, spread + (card_w / 2.0) * 1.06 + margin)
        half_arc = min(half_arc, self.SLAB_HALF_ARC_RANGE[1])
        # Headings left-aligned inside the slab (SteamVR-style), clear
        # of the rim fade band (arc_fade 2.5° + 0.5° inset in the
        # renderer) that was eating the heading's first characters.
        for panel in self._chrome:
            panel.yaw_deg = (-half_arc + 4.0
                             + (panel.width_m / 2.0) * deg_per_m)
        # Clock into the bottom bar, right-aligned but clear of the
        # rounded corner (the flat quad chords the curve).
        if self._clock is not None:
            half_w_deg = (self._clock.width_m / 2.0) * deg_per_m
            self._clock.yaw_deg = half_arc - 5.0 - half_w_deg
            # Above the bar center: the flat quad chords the curved
            # slab, whose projected edge climbs toward the corners
            # (measured headless, not derived).
            self._clock.y_m = bar_y + 0.04
        # Slab extent: wrap the headings/rails/bar with a small margin.
        self._slab = (half_arc, bar_y - BAR_H_M / 2.0 - 0.10,
                      SLAB_Y_TOP + 0.05)
        self._backdrop_rev += 1

    def set_radius(self, radius_m: float) -> None:
        """Move the whole slab nearer/farther (PgDn/PgUp): re-derive the
        rail layout and chrome at the new radius; textures are reused."""
        self.scene.layout.radius_m = _clamp(radius_m, self.SLAB_DIST_RANGE)
        self.scene._relayout()
        self._layout_chrome()

    def backdrop(self) -> tuple | None:
        """The dashboard slab for the renderer: ``(rev, vertices,
        (w_m, h_m), half_arc_deg)`` — the arc doubles as the card
        clip/fade limit; None while an app is focused (launcher hidden)."""
        if self.mode != LAUNCHER:
            return None
        if self._backdrop is None or self._backdrop[0] != self._backdrop_rev:
            half_arc, y0, y1 = self._slab
            verts, size = backdrop_mesh(self.scene.layout, half_arc, y0, y1)
            self._backdrop = (self._backdrop_rev, verts, size, half_arc)
        return self._backdrop

    def _install_clock(self):
        try:
            img = clock_image()
        except Exception:                 # Pillow missing: shell still works, no clock
            return None
        self._clock_tex = pil_to_texture(self.ctx, img)
        self._clock_minute = time.localtime().tm_min
        # Lives in the slab's bottom bar (doc 17 §2b); _install_tiles
        # sets its yaw/height to the current layout.
        return Panel(id="_clock", title="clock", yaw_deg=0.0,
                     width_m=0.40, height_m=0.11, y_m=-0.70,
                     radius_bias=0.02,
                     texture=self._clock_tex, stereo_mode="mono",
                     data={"overlay": True})

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

    def on_push(self):
        """PgUp / '-': launcher — push the whole slab farther away;
        app — same as up (push the window)."""
        if self.mode == LAUNCHER:
            self.set_radius(self.scene.layout.radius_m + self.SLAB_DIST_STEP)
        elif self.mode == APP:
            self._app_dist = _clamp(self._app_dist + APP_DIST_STEP, APP_DIST_RANGE)

    def on_pull(self):
        """PgDn / '=': launcher — pull the slab closer; app — pull the window."""
        if self.mode == LAUNCHER:
            self.set_radius(self.scene.layout.radius_m - self.SLAB_DIST_STEP)
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
        if (self.hub is not None and self.hub.enabled
                and not self._net_kicked):
            self._net_kicked = True
            self.hub.refresh_home(self._pending_rails.put)
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
            if panel.data.get("offstage"):     # beyond the scroll window
                continue
            model = self.scene.layout.model_matrix(panel)
            if panel is selected:            # gentle zoom on the focused tile
                model = m.mat4_mul(model, _uniform_scale(1.06))
            out.append((panel, model))
        for panel in self._chrome:           # rail headings (non-selectable)
            out.append((panel, self.scene.layout.model_matrix(panel)))
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
