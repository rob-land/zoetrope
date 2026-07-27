"""Pure-logic tests for the movie library / ripplay seam (no subprocess)."""
import json
import os

import pytest

from beamshell import library


# --- title derivation -------------------------------------------------------

def test_title_prefers_jellyfin_parent_dir(tmp_path):
    d = tmp_path / "Avatar (2009)"
    d.mkdir()
    p = d / "Avatar (2009) - 3D.fsbs.mkv"
    p.touch()
    assert library.title_from_path(str(p)) == "Avatar (2009)"


def test_title_falls_back_to_cleaned_stem(tmp_path):
    p = tmp_path / "Tron Legacy.fsbs.mkv"
    p.touch()
    assert library.title_from_path(str(p)) == "Tron Legacy"


def test_title_strips_stacked_3d_slugs(tmp_path):
    p = tmp_path / "Coraline.3D.hsbs.mkv"
    p.touch()
    assert library.title_from_path(str(p)) == "Coraline"


# --- poster + scan ----------------------------------------------------------

def test_scan_finds_movies_posters_and_sorts(tmp_path):
    a = tmp_path / "Up (2009)"
    b = tmp_path / "Brave (2012)"
    for d in (a, b):
        d.mkdir()
    (a / "Up (2009).fsbs.mkv").touch()
    (a / "poster.jpg").touch()
    (b / "Brave (2012).fsbs.mkv").touch()
    movies = library.scan_movies([str(tmp_path)])
    assert [m.title for m in movies] == ["Brave (2012)", "Up (2009)"]
    assert movies[1].poster and movies[1].poster.endswith("poster.jpg")
    assert movies[0].poster is None


def test_scan_skips_hidden_and_extras(tmp_path):
    (tmp_path / ".thumbs").mkdir()
    (tmp_path / ".thumbs" / "x.mkv").touch()
    (tmp_path / "Extras").mkdir()
    (tmp_path / "Extras" / "bonus.mkv").touch()
    (tmp_path / "Real.mkv").touch()
    movies = library.scan_movies([str(tmp_path)])
    assert [os.path.basename(m.path) for m in movies] == ["Real.mkv"]


def test_scan_dedupes_across_roots(tmp_path):
    (tmp_path / "One.mkv").touch()
    movies = library.scan_movies([str(tmp_path), str(tmp_path)])
    assert len(movies) == 1


# --- config discovery -------------------------------------------------------

def test_ripsaw_library_root_reads_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    lib = tmp_path / "movies"
    lib.mkdir()
    d = tmp_path / "ripsaw"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"library_root": str(lib)}))
    assert library.ripsaw_library_root() == str(lib)


def test_ripsaw_library_root_null_or_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert library.ripsaw_library_root() is None
    d = tmp_path / "ripsaw"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"library_root": None}))
    assert library.ripsaw_library_root() is None


def test_library_roots_env_override_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nope"))
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setenv("BEAMSHELL_LIBRARY", str(env_dir))
    roots = library.library_roots(str(media), explicit=str(env_dir))
    assert roots == [str(env_dir), str(media)]


# --- playback geometry ------------------------------------------------------

def _report(fmt, pb, w=1920, h=1080, tw=3840, th=1080):
    return {"format": fmt, "playback": {"type": pb},
            "width": w, "height": h,
            "target": {"width": tw, "height": th}}


def test_geometry_stream_is_target_fsbs():
    fbo, stereo, aspect = library.playback_geometry(_report("mvc", "stream"))
    assert fbo == (3840, 1080)
    assert stereo == "sbs"
    assert aspect == pytest.approx(1920 / 1080)


def test_geometry_direct_full_sbs():
    fbo, stereo, aspect = library.playback_geometry(
        _report("sbs-full", "direct", w=3840))
    assert fbo == (3840, 1080)
    assert stereo == "sbs"
    assert aspect == pytest.approx(1920 / 1080)


def test_geometry_direct_half_sbs_is_anamorphic():
    fbo, stereo, aspect = library.playback_geometry(
        _report("sbs-half", "direct", w=1920))
    assert fbo == (1920, 1080)
    assert stereo == "sbs"
    assert aspect == pytest.approx(1920 / 1080)  # squeezed halves expand back


def test_geometry_mono():
    fbo, stereo, aspect = library.playback_geometry(_report("mono", "direct"))
    assert stereo == "mono"
    assert aspect == pytest.approx(1920 / 1080)
