"""Pure-logic tests for the movie library / stereoscope seam (no subprocess)."""
import json
import os

import pytest

from zoetrope import library


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
    monkeypatch.setenv("ZOETROPE_LIBRARY", str(env_dir))
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


# --- photo scan + stereo pairing --------------------------------------------

def test_pair_stereo_files_l_r_suffixes():
    pairs = library.pair_stereo_files(
        ["shot_l.jpg", "shot_r.jpg", "lone.jpg", "vac-left.png", "vac-right.png"])
    d = {left: right for left, right in pairs}
    assert d["shot_l.jpg"] == "shot_r.jpg"
    assert d["vac-left.png"] == "vac-right.png"
    assert d["lone.jpg"] is None
    assert len(pairs) == 3  # right-eye files fold into their left entry


def test_pair_stereo_files_case_insensitive():
    pairs = library.pair_stereo_files(["A_L.JPG", "a_r.jpg"])
    assert pairs == [("A_L.JPG", "a_r.jpg")]


def test_scan_photos_skips_poster_art(tmp_path):
    (tmp_path / "poster.jpg").touch()
    (tmp_path / "beach.mpo").touch()
    photos = library.scan_photos([str(tmp_path)])
    assert [p.title for p in photos] == ["beach"]


def test_scan_photos_pairs_and_titles(tmp_path):
    (tmp_path / "trip_l.jpg").touch()
    (tmp_path / "trip_r.jpg").touch()
    photos = library.scan_photos([str(tmp_path)])
    assert len(photos) == 1
    assert photos[0].right_path.endswith("trip_r.jpg")


# --- gallery navigation -----------------------------------------------------

def test_gallery_next_index_wraps():
    from zoetrope.apps.photo import next_index
    assert next_index(0, +1, 3) == 1
    assert next_index(2, +1, 3) == 0
    assert next_index(0, -1, 3) == 2
    assert next_index(5, 0, 0) == 0


# --- shared-provider hub (suite_providers bridge) ---------------------------

def test_jellyfin_config_requires_all_keys(tmp_path):
    from zoetrope import providers
    p = tmp_path / "config.json"
    p.write_text('{"jellyfin": {"server_url": "http://x"}}')
    assert providers.jellyfin_config(str(p)) is None
    p.write_text('{"jellyfin": {"server_url": "http://x", '
                 '"access_token": "t", "user_id": "u"}}')
    assert providers.jellyfin_config(str(p))["user_id"] == "u"
    assert providers.jellyfin_config(str(tmp_path / "missing.json")) is None


def test_synth_report_direct_vs_unsupported():
    pytest.importorskip("suite_providers")
    from suite_providers import ContentType, MediaItem
    from suite_providers.models import StereoConfidence, StereoFormat, StereoHint
    from zoetrope.providers import synth_report

    def item(fmt):
        return MediaItem(provider_id="j", provider_item_id="1", title="t",
                         content_type=ContentType.MOVIE,
                         stereo=StereoHint(fmt, StereoConfidence.SERVER))

    assert synth_report(item(StereoFormat.SBS_HALF))["playback"]["type"] == "direct"
    assert synth_report(item(StereoFormat.MONO))["playback"]["type"] == "direct"
    r = synth_report(item(StereoFormat.MVC))
    assert r["playback"]["type"] == "unsupported"
    assert r["playback"]["can_play_2d"] is True
    assert r["format"] == "mvc"


def test_hub_disabled_without_config():
    from zoetrope.providers import ProviderHub
    hub = ProviderHub(config=None)
    # jellyfin_config() may find the user's real config; force-disable:
    hub._jf_config = None
    assert hub.enabled is False
    hub.refresh_home(lambda d: (_ for _ in ()).throw(AssertionError))


def test_save_jellyfin_config_merges(tmp_path):
    from zoetrope.providers import jellyfin_config, save_jellyfin_config
    dest = str(tmp_path / "config.json")
    (tmp_path / "config.json").write_text('{"other": {"keep": true}}')
    save_jellyfin_config({"server_url": "http://x", "access_token": "t",
                          "user_id": "u"}, path=dest)
    import json
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["other"] == {"keep": True}
    assert jellyfin_config(dest)["access_token"] == "t"


def test_quick_connect_state_machine(tmp_path, monkeypatch):
    import asyncio

    from zoetrope import providers as pr

    class FakeProvider:
        async def quick_connect_enabled(self):
            return True

        async def quick_connect_initiate(self):
            return {"secret": "s", "code": "123456"}

        async def quick_connect_poll(self, secret):
            return True

        async def quick_connect_complete(self, secret):
            from suite_providers import AuthStatus
            return AuthStatus(ok=True, credentials={
                "access_token": "tok", "user_id": "u9"})

    monkeypatch.setattr(pr, "config_path",
                        lambda: str(tmp_path / "config.json"))
    monkeypatch.setattr(pr.asyncio, "sleep",
                        lambda s: asyncio.sleep(0))
    hub = pr.ProviderHub(config=None)
    hub._server = "http://jf"
    hub._provider = FakeProvider()
    events = []
    asyncio.run(hub._quick_connect(events.append))
    assert [e["state"] for e in events] == ["code", "done"]
    assert events[0]["code"] == "123456"
    assert hub.enabled and hub._jf_config["user_id"] == "u9"
    assert pr.jellyfin_config(str(tmp_path / "config.json"))["access_token"] == "tok"
