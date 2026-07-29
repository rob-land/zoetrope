"""Movie library discovery + the stereoscope engine seam.

zoetrope does not know how to detect or convert 3D formats itself —
that's stereoscope's job (shared with the Ripsaw ripper). This module:

- finds the user's library (``$ZOETROPE_LIBRARY``, else Ripsaw's
  ``library_root`` from ``~/.config/ripsaw/config.json``);
- scans it for movies, deriving titles and poster art from the
  Jellyfin-style naming Ripsaw writes (``Title (Year)/…``,
  ``poster.jpg``/``folder.jpg``);
- wraps the ``stereoscope probe`` (JSON: what is this file, how to play it)
  and ``stereoscope stream`` (composed Full-SBS NUT on stdout) CLI.

Everything except the subprocess calls is pure and unit-testable.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

MOVIE_EXTS = (".mkv", ".mp4", ".m4v", ".mov", ".webm", ".m2ts", ".ts")
POSTER_NAMES = ("poster.jpg", "poster.png", "folder.jpg", "folder.png", "cover.jpg")

# Ripsaw/scene-style suffix slugs that don't belong in a display title.
_TITLE_NOISE = re.compile(
    r"(\.(fsbs|hsbs|ftab|htab|fou|hou|sbs|tab|ou|halfsbs|3d))+$", re.IGNORECASE)


def ripsaw_config_path() -> str:
    cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(cfg, "ripsaw", "config.json")


def ripsaw_library_root() -> str | None:
    """Ripsaw's library_root, so both apps share one library with zero setup."""
    try:
        with open(ripsaw_config_path(), "rb") as f:
            root = json.load(f).get("library_root")
        return root if root and os.path.isdir(root) else None
    except Exception:
        return None


def library_roots(media_dir: str | None = None,
                  explicit: str | None = None) -> list[str]:
    """Candidate roots, most specific first, existing dirs only, deduped."""
    candidates = [explicit, os.environ.get("ZOETROPE_LIBRARY"),
                  ripsaw_library_root(), media_dir]
    out: list[str] = []
    for c in candidates:
        if c and os.path.isdir(c) and c not in out:
            out.append(c)
    return out


def title_from_path(path: str) -> str:
    """Display title: prefer a Jellyfin-style ``Title (Year)`` parent dir,
    else the cleaned-up file stem."""
    parent = os.path.basename(os.path.dirname(path))
    if re.search(r"\(\d{4}\)$", parent):
        return parent
    stem = os.path.splitext(os.path.basename(path))[0]
    return _TITLE_NOISE.sub("", stem)


def poster_for(path: str) -> str | None:
    """Jellyfin-style artwork next to the movie file, when present."""
    d = os.path.dirname(path)
    for name in POSTER_NAMES:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


@dataclass
class Movie:
    path: str
    title: str
    poster: str | None


def scan_movies(roots: list[str], limit: int = 200) -> list[Movie]:
    """Walk the library for movie files, sorted by title. Hidden dirs and
    extras-style subfolders are skipped; one entry per file."""
    seen: set[str] = set()
    out: list[Movie] = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")
                           and d.lower() not in ("extras", "trailers", "featurettes")]
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1].lower() not in MOVIE_EXTS:
                    continue
                p = os.path.join(dirpath, fn)
                real = os.path.realpath(p)
                if real in seen:
                    continue
                seen.add(real)
                out.append(Movie(path=p, title=title_from_path(p),
                                 poster=poster_for(p)))
                if len(out) >= limit:
                    break
    out.sort(key=lambda mv: mv.title.lower())
    return out


# --- photos -----------------------------------------------------------------

PHOTO_EXTS = (".mpo", ".jps", ".jpg", ".jpeg", ".png", ".heic", ".heif")

# name-suffix conventions for explicit left/right stereo pair files
_PAIR_SUFFIXES = (("_l", "_r"), ("-l", "-r"), ("_left", "_right"), ("-left", "-right"))


@dataclass
class Photo:
    path: str
    right_path: str | None
    title: str


def pair_stereo_files(names: list[str]) -> list[tuple[str, str | None]]:
    """Group a directory's photo filenames into (left, right-or-None)
    entries by the usual L/R suffix conventions; case-insensitive."""
    by_lower = {n.lower(): n for n in names}
    used: set[str] = set()
    out: list[tuple[str, str | None]] = []
    for n in sorted(names):
        low = n.lower()
        if low in used:
            continue
        stem, ext = os.path.splitext(low)
        matched = False
        for ls, rs in _PAIR_SUFFIXES:
            if stem.endswith(ls):
                partner = by_lower.get(stem[: -len(ls)] + rs + ext)
                if partner:
                    out.append((n, partner))
                    used.add(low)
                    used.add(partner.lower())
                    matched = True
                break
            if stem.endswith(rs) and by_lower.get(stem[: -len(rs)] + ls + ext):
                used.add(low)   # right eye — folded into its left's entry
                matched = True
                break
        if not matched:
            out.append((n, None))
            used.add(low)
    return out


def scan_photos(roots: list[str], limit: int = 500) -> list[Photo]:
    """Walk for still photos, pairing explicit L/R files. MPO/JPS/wide-SBS
    detection happens at view time (the viewer splits them itself)."""
    seen: set[str] = set()
    out: list[Photo] = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            photos = [f for f in filenames
                      if os.path.splitext(f)[1].lower() in PHOTO_EXTS
                      and not f.lower().startswith(("poster.", "folder.", "cover."))]
            for left, right in pair_stereo_files(photos):
                p = os.path.join(dirpath, left)
                real = os.path.realpath(p)
                if real in seen:
                    continue
                seen.add(real)
                title = os.path.splitext(left)[0]
                out.append(Photo(
                    path=p,
                    right_path=os.path.join(dirpath, right) if right else None,
                    title=title))
                if len(out) >= limit:
                    break
    out.sort(key=lambda ph: ph.title.lower())
    return out


# --- stereoscope engine seam ----------------------------------------------------

def stereoscope_bin() -> str | None:
    return os.environ.get("STEREOSCOPE_BIN") or shutil.which("stereoscope")


def probe(path: str, target: tuple[int, int] = (3840, 1080)) -> dict | None:
    """``stereoscope probe`` JSON for a file, or None when stereoscope is missing
    or fails (callers fall back to filename heuristics)."""
    exe = stereoscope_bin()
    if not exe:
        return None
    try:
        res = subprocess.run(
            [exe, "probe", "--target", f"{target[0]}x{target[1]}", path],
            capture_output=True, timeout=30, check=True)
        return json.loads(res.stdout)
    except Exception:
        return None


def stream_command(path: str,
                   target: tuple[int, int] = (3840, 1080)) -> list[str] | None:
    """argv for ``stereoscope stream`` (composed Full-SBS NUT on stdout)."""
    exe = stereoscope_bin()
    if not exe:
        return None
    return [exe, "stream", "--target", f"{target[0]}x{target[1]}", path]


def playback_geometry(report: dict) -> tuple[tuple[int, int], str, float]:
    """``(fbo_size, stereo_mode, per_eye_aspect)`` for a probe report.

    The FBO must match what mpv actually renders (else it letterboxes
    inside the texture and the eye split breaks): streamed playback is
    composed Full-SBS at the probe target; direct playback is the file's
    own geometry. Per-eye aspect is the shape of the floating panel:
    full SBS halves its width, half-SBS is anamorphic (each squeezed
    half expands back to the full-frame aspect), mono is as-is.
    """
    fmt = report.get("format", "unknown")
    pb = (report.get("playback") or {}).get("type")
    w = report.get("width") or 1920
    h = report.get("height") or 1080
    t = report.get("target") or {}
    tw, th = t.get("width") or 3840, t.get("height") or 1080
    if pb == "stream":
        return (tw, th), "sbs", (tw / 2) / th
    if fmt == "sbs-full":
        return (w, h), "sbs", (w / 2) / h
    if fmt == "sbs-half":
        return (w, h), "sbs", w / h
    return (w, h), "mono", w / h
