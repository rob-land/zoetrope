"""Unit tests for beamshell's dependency-free core (run: pytest, or python -m unittest)."""
import math
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from beamshell import config, detect, mathutil as m, scene, stereo


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def vapprox(a, b, tol=1e-6):
    return all(approx(x, y, tol) for x, y in zip(a, b))


class TestMath(unittest.TestCase):
    def test_identity_rotation(self):
        v = (0.3, -0.4, 0.5)
        self.assertTrue(vapprox(m.q_rotate(m.QUAT_IDENTITY, v), v))

    def test_yaw_90_maps_forward_to_left(self):
        # +90 deg about Y should rotate forward (0,0,-1) to (-1,0,0).
        q = m.q_from_axis_angle((0, 1, 0), math.radians(90))
        self.assertTrue(vapprox(m.q_rotate(q, (0, 0, -1)), (-1, 0, 0), 1e-6))

    def test_quat_mul_identity(self):
        q = m.q_norm((0.1, 0.2, 0.3, 0.4))
        self.assertTrue(vapprox(m.q_mul(m.QUAT_IDENTITY, q), q))

    def test_perspective_terms(self):
        p = m.mat4_perspective(math.radians(90), 2.0, 0.1, 100.0)
        f = 1.0 / math.tan(math.radians(90) / 2)
        self.assertTrue(approx(p[0], f / 2.0))     # f / aspect
        self.assertTrue(approx(p[5], f))
        self.assertTrue(approx(p[11], -1.0))
        self.assertTrue(approx(p[10], (100.0 + 0.1) / (0.1 - 100.0)))

    def test_rigid_inverse_translates_eye_to_origin(self):
        # A camera at (0,0,5) looking down -Z: the point (0,0,5) maps to view-space 0.
        view = m.mat4_rigid_inverse(m.QUAT_IDENTITY, (0, 0, 5))
        # transform (0,0,5,1) by column-major matrix
        p = _apply(view, (0, 0, 5, 1))
        self.assertTrue(vapprox(p[:3], (0, 0, 0), 1e-6))


class TestStereo(unittest.TestCase):
    def test_sbs_viewports(self):
        left, right = stereo.sbs_viewports(3840, 1080)
        self.assertEqual(left.as_tuple(), (0, 0, 1920, 1080))
        self.assertEqual(right.as_tuple(), (1920, 0, 1920, 1080))

    def test_eye_offset_sign(self):
        pose = stereo.HeadPose()
        lpos = stereo.eye_position(pose, 0.063, stereo.LEFT)
        rpos = stereo.eye_position(pose, 0.063, stereo.RIGHT)
        self.assertLess(lpos[0], 0.0)          # left eye to -x
        self.assertGreater(rpos[0], 0.0)       # right eye to +x
        self.assertTrue(approx(rpos[0] - lpos[0], 0.063))

    def test_eye_matrices_viewports(self):
        left, right = stereo.eye_matrices(stereo.HeadPose(), 3840, 1080, 48.0, 0.063)
        self.assertEqual(left.viewport.x, 0)
        self.assertEqual(right.viewport.x, 1920)

    def test_head_yaw_zero_when_forward(self):
        self.assertTrue(approx(stereo.head_yaw(stereo.HeadPose()), 0.0))

    def test_mono_matrices_single_fullframe(self):
        eyes = stereo.mono_matrices(stereo.HeadPose(), 1920, 1080, 48.0)
        self.assertEqual(len(eyes), 1)
        self.assertEqual(eyes[0].viewport.as_tuple(), (0, 0, 1920, 1080))


class TestDisplayModes(unittest.TestCase):
    def _fake_connector(self, root, connector, modes):
        d = os.path.join(root, connector)
        os.makedirs(d)
        with open(os.path.join(d, "modes"), "w") as f:
            f.write("\n".join(modes) + "\n")

    def test_output_modes_dedup(self):
        from beamshell import display
        with tempfile.TemporaryDirectory() as root:
            self._fake_connector(root, "card1-DP-1",
                                 ["1920x1080", "1920x1080", "1920x1080"])
            self.assertEqual(display.output_modes("card1-DP-1", root), ["1920x1080"])

    def test_sbs_available_false_when_only_2d(self):
        from beamshell import display
        from beamshell.config import PROFILES
        with tempfile.TemporaryDirectory() as root:
            self._fake_connector(root, "card1-DP-1", ["1920x1080"])
            tgt = display.DisplayTarget("card1-DP-1", "DP-1", PROFILES["one_pro"])
            self.assertFalse(display.sbs_available(tgt, PROFILES["one_pro"], root))

    def test_sbs_available_true_when_3840_present(self):
        from beamshell import display
        from beamshell.config import PROFILES
        with tempfile.TemporaryDirectory() as root:
            self._fake_connector(root, "card1-DP-1", ["3840x1080", "1920x1080"])
            tgt = display.DisplayTarget("card1-DP-1", "DP-1", PROFILES["one_pro"])
            self.assertTrue(display.sbs_available(tgt, PROFILES["one_pro"], root))


class TestDetect(unittest.TestCase):
    def _fake_usb(self, root, name, vid, pid):
        d = os.path.join(root, name)
        os.makedirs(d)
        with open(os.path.join(d, "idVendor"), "w") as f:
            f.write(f"{vid:04x}\n")
        with open(os.path.join(d, "idProduct"), "w") as f:
            f.write(f"{pid:04x}\n")

    def test_scan_finds_one_pro_not_beampro_gadget(self):
        with tempfile.TemporaryDirectory() as root:
            self._fake_usb(root, "1-1", 0x3318, 0x435)   # One Pro glasses
            self._fake_usb(root, "1-2", 0x1d6b, 0x0002)   # a hub, ignored
            self._fake_usb(root, "2-2", 0x3318, 0x0528)   # Beam Pro's OWN gadget (same VID!)
            found = detect.scan_sysfs(root)
            self.assertEqual(len(found), 1)              # gadget must NOT match
            self.assertEqual(found[0].profile.key, "one_pro")

    def test_unknown_in_range_pid_is_generic(self):
        # An XREAL VID with an unknown but in-range PID -> generic glasses.
        prof = detect.profile_for(0x3318, 0x429)
        self.assertIsNotNone(prof)
        self.assertEqual(prof.key, "generic")

    def test_host_gadget_pid_is_not_glasses(self):
        # Beam Pro / phone gadget: XREAL VID but out-of-range PID -> not glasses.
        self.assertFalse(detect.is_xreal(0x3318, 0x0528))
        self.assertIsNone(detect.profile_for(0x3318, 0x0528))

    def test_edid_pnp_and_product(self):
        edid = self._make_edid("MRG", 16640)
        self.assertEqual(detect.edid_pnp_id(edid), "MRG")
        self.assertEqual(detect.edid_product_id(edid), 16640)

    def test_find_output_from_edids(self):
        edids = {
            "card0-DSI-1": self._make_edid("QCM", 1),
            "card0-DP-1": self._make_edid("MRG", 16640),
        }
        out = detect.find_glasses_output_from_edids(edids)
        self.assertIsNotNone(out)
        self.assertEqual(out.connector, "card0-DP-1")
        self.assertEqual(out.pnp_id, "MRG")
        self.assertEqual(out.profile.key, "one_pro")

    @staticmethod
    def _make_edid(pnp: str, product: int) -> bytes:
        a, b, c = (ord(pnp[0]) - 64, ord(pnp[1]) - 64, ord(pnp[2]) - 64)
        man = (a << 10) | (b << 5) | c
        data = bytearray(128)
        data[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
        data[8] = (man >> 8) & 0xFF
        data[9] = man & 0xFF
        data[10] = product & 0xFF
        data[11] = (product >> 8) & 0xFF
        return bytes(data)


class TestScene(unittest.TestCase):
    def _scene(self, n=5):
        s = scene.LauncherScene()
        s.set_panels([scene.Panel(id=str(i), title=f"P{i}", yaw_deg=0) for i in range(n)])
        return s

    def test_layout_symmetric_centered_and_capped(self):
        s = self._scene(5)
        yaws = [p.yaw_deg for p in s.panels]
        self.assertTrue(approx(yaws[2], 0.0))            # middle centered
        self.assertTrue(approx(yaws[0], -yaws[-1]))      # symmetric
        self.assertTrue(all(yaws[i] < yaws[i + 1] for i in range(4)))  # increasing
        # default 22 deg spacing (capped by arc_span) -> tiles stay near center, in view
        self.assertTrue(approx(yaws[3] - yaws[2], 22.0))
        self.assertLessEqual(abs(yaws[0]), 45.0)

    def test_two_tiles_are_near_center(self):
        s = self._scene(2)
        yaws = sorted(p.yaw_deg for p in s.panels)
        self.assertTrue(approx(yaws[0], -11.0))          # +/- 11 deg, not +/- 40
        self.assertTrue(approx(yaws[1], 11.0))

    def test_gaze_selects_center_when_forward(self):
        s = self._scene(5)
        self.assertEqual(s.select_by_gaze(stereo.HeadPose()), 2)

    def test_gaze_selects_right_when_looking_right(self):
        s = self._scene(5)
        # Look ~40 deg to the right (about +Y): forward tilts to +x.
        q = m.q_from_axis_angle((0, 1, 0), math.radians(-40))  # -Y yaw = look right
        pose = stereo.HeadPose(orientation=q)
        idx = s.select_by_gaze(pose)
        self.assertGreater(idx, 2)

    def test_position_on_cylinder(self):
        s = self._scene(1)
        p = s.panels[0]
        pos = s.layout.position(p)
        # centered panel sits straight ahead at -radius on Z
        self.assertTrue(approx(pos[0], 0.0, 1e-6))
        self.assertTrue(approx(pos[2], -s.layout.radius_m, 1e-6))


class TestXRDriverParsing(unittest.TestCase):
    """Parsers for wheaney/XRLinuxDriver's two output channels."""

    def test_opentrack_packet_roundtrip(self):
        from beamshell.tracking import parse_opentrack_packet
        pkt = struct.pack("<6dI", 1.0, 2.0, 3.0, 45.0, -10.0, 5.0, 1234)
        self.assertEqual(parse_opentrack_packet(pkt),
                         (1.0, 2.0, 3.0, 45.0, -10.0, 5.0))
        self.assertIsNone(parse_opentrack_packet(b"short"))

    def test_opentrack_identity(self):
        from beamshell.tracking import opentrack_to_quat
        q = opentrack_to_quat(0.0, 0.0, 0.0)
        self.assertTrue(approx(abs(q[0]), 1.0, 1e-6))

    def test_opentrack_yaw_maps_to_beamshell_azimuth(self):
        from beamshell.tracking import opentrack_to_quat
        # Driver yaw +30 (positive-left in NWU) -> beamshell azimuth -30 (left).
        q = opentrack_to_quat(30.0, 0.0, 0.0)
        pose = stereo.HeadPose(orientation=q)
        self.assertTrue(approx(math.degrees(stereo.head_yaw(pose)), -30.0, 1e-4))

    def test_opentrack_pitch_default_sign_flipped(self):
        # Hardware-verified 2026-07-19: up/down was inverted with identity signs,
        # so the default must flip pitch (driver pitch axis is our -X).
        from beamshell.tracking import DEFAULT_OT_SIGNS, opentrack_to_quat
        self.assertEqual(DEFAULT_OT_SIGNS[1], -1.0)
        up_component_default = m.q_rotate(
            opentrack_to_quat(0.0, 20.0, 0.0), (0, 0, -1))[1]
        up_component_identity = m.q_rotate(
            opentrack_to_quat(0.0, 20.0, 0.0, (1, 1, 1)), (0, 0, -1))[1]
        self.assertTrue(approx(up_component_default, -up_component_identity, 1e-6))

    @staticmethod
    def _breezy_buf(x=0.0, y=0.0, z=0.0, w=1.0, date_ms=1000, version=5):
        buf = bytearray(186)
        buf[0] = version
        struct.pack_into("<Q", buf, 113, date_ms)
        struct.pack_into("<4f", buf, 121, x, y, z, w)
        parity = 0
        for b in buf[113:185]:
            parity ^= b
        buf[185] = parity
        return bytes(buf)

    def test_breezy_valid(self):
        from beamshell.tracking import parse_breezy_imu
        q = parse_breezy_imu(self._breezy_buf(w=1.0, date_ms=5000), now_ms=5100)
        self.assertIsNotNone(q)
        self.assertTrue(approx(q[0], 1.0, 1e-6))  # (w,x,y,z), w first

    def test_breezy_rejects_bad_version_parity_stale(self):
        from beamshell.tracking import parse_breezy_imu
        self.assertIsNone(parse_breezy_imu(self._breezy_buf(version=4)))
        good = bytearray(self._breezy_buf())
        good[130] ^= 0xFF   # corrupt orientation without fixing parity
        self.assertIsNone(parse_breezy_imu(bytes(good)))
        self.assertIsNone(parse_breezy_imu(self._breezy_buf(date_ms=1000), now_ms=99999))


class TestGazeKeyboardPriority(unittest.TestCase):
    """Keyboard nav must hold selection until the head actually turns (issue: arrow
    selection reverted after one frame under a static tracker)."""

    def test_no_lock_allows_gaze(self):
        from beamshell.shell import gaze_may_select
        self.assertTrue(gaze_may_select(None, 0.0))

    def test_locked_blocks_gaze_while_head_still(self):
        from beamshell.shell import gaze_may_select
        self.assertFalse(gaze_may_select(0.0, 0.0))
        self.assertFalse(gaze_may_select(0.0, 5.0))
        self.assertFalse(gaze_may_select(0.0, -5.0))

    def test_head_turn_past_threshold_resumes_gaze(self):
        from beamshell.shell import gaze_may_select
        self.assertTrue(gaze_may_select(0.0, 9.0))
        self.assertTrue(gaze_may_select(0.0, -9.0))

    def test_wraparound(self):
        from beamshell.shell import gaze_may_select
        self.assertFalse(gaze_may_select(179.0, -178.0))  # 3 deg apart across the seam
        self.assertTrue(gaze_may_select(179.0, -160.0))


def _apply(mat, vec4):
    """Apply a column-major mat4 to a 4-vector."""
    out = [0.0, 0.0, 0.0, 0.0]
    for row in range(4):
        out[row] = sum(mat[col * 4 + row] * vec4[col] for col in range(4))
    return out


def _dd_packet(time=0, seq=0, ori=(0, 0, 0), acc=(0, 0, 0), gyro=(0, 0, 0),
               touch=(0, 0), buttons=0):
    """Assemble a 20-byte Daydream notification from raw (LSB-unit) fields.

    Independent re-encoding of the documented bit layout: one MSB-first stream of
    time(9) seq(5) ori(3x13) acc(3x13) gyro(3x13) touch(2x8) buttons(5) = 152 bits.
    """
    fields = [(time, 9), (seq, 5)]
    fields += [(v, 13) for v in (*ori, *acc, *gyro)]
    fields += [(touch[0], 8), (touch[1], 8), (buttons, 5)]
    n = 0
    for v, w in fields:
        n = (n << w) | (v & ((1 << w) - 1))
    return n.to_bytes(19, "big") + b"\x00"


class TestDaydreamParsing(unittest.TestCase):
    def test_rejects_short_packet(self):
        from beamshell.controller import parse_daydream_packet
        self.assertIsNone(parse_daydream_packet(b"\x00" * 19))

    def test_zero_packet_is_neutral(self):
        from beamshell.controller import parse_daydream_packet
        s = parse_daydream_packet(_dd_packet())
        self.assertEqual(s.ori, (0.0, 0.0, 0.0))
        self.assertEqual(s.touch, (0.0, 0.0))
        self.assertFalse(s.touching)
        self.assertFalse(s.click or s.app or s.home or s.vol_up or s.vol_down)

    def test_ori_roundtrip_incl_negative(self):
        from beamshell.controller import parse_daydream_packet, _ORI_SCALE
        s = parse_daydream_packet(_dd_packet(ori=(100, -200, 8191)))
        self.assertTrue(approx(s.ori[0], 100 * _ORI_SCALE))
        self.assertTrue(approx(s.ori[1], -200 * _ORI_SCALE))
        self.assertTrue(approx(s.ori[2], -1 * _ORI_SCALE))  # 8191 = -1 in 13-bit

    def test_acc_gyro_roundtrip(self):
        from beamshell.controller import parse_daydream_packet, _ACC_SCALE, _GYRO_SCALE
        s = parse_daydream_packet(_dd_packet(acc=(8191, 512, -3), gyro=(-1000, 1, 0)))
        self.assertTrue(approx(s.accel[0], -1 * _ACC_SCALE))
        self.assertTrue(approx(s.accel[1], 512 * _ACC_SCALE))
        self.assertTrue(approx(s.accel[2], -3 * _ACC_SCALE))
        self.assertTrue(approx(s.gyro[0], -1000 * _GYRO_SCALE))
        self.assertTrue(approx(s.gyro[1], 1 * _GYRO_SCALE))

    def test_buttons_and_seq(self):
        from beamshell.controller import parse_daydream_packet
        s = parse_daydream_packet(_dd_packet(seq=13, buttons=0x1 | 0x2 | 0x10))
        self.assertEqual(s.seq, 13)
        self.assertTrue(s.click and s.home and s.vol_up)
        self.assertFalse(s.app or s.vol_down)

    def test_touch_roundtrip(self):
        from beamshell.controller import parse_daydream_packet
        s = parse_daydream_packet(_dd_packet(touch=(128, 255)))
        self.assertTrue(approx(s.touch[0], 128 / 255.0))
        self.assertTrue(approx(s.touch[1], 1.0))
        self.assertTrue(s.touching)

    def test_orientation_quat_and_pointer_yaw(self):
        from beamshell.controller import orientation_quat, pointer_yaw_pitch_deg
        self.assertEqual(orientation_quat((0, 0, 0), (1, 1, 1)), m.QUAT_IDENTITY)
        # +90 deg about +Y rotates forward to the LEFT -> pointer yaw -90.
        q = orientation_quat((0.0, math.pi / 2.0, 0.0), (1, 1, 1))
        yaw, pitch = pointer_yaw_pitch_deg(q)
        self.assertTrue(approx(yaw, -90.0, 1e-4))
        self.assertTrue(approx(pitch, 0.0, 1e-4))

    def test_pointer_yaw_matches_head_yaw_convention(self):
        from beamshell.controller import pointer_yaw_pitch_deg
        q = m.q_from_axis_angle((0, 1, 0), math.radians(-30))  # look right
        yaw, _ = pointer_yaw_pitch_deg(q)
        head = math.degrees(stereo.head_yaw(stereo.HeadPose(orientation=q)))
        self.assertTrue(approx(yaw, head, 1e-6))
        self.assertTrue(yaw > 0)


class TestDaydreamGestures(unittest.TestCase):
    @staticmethod
    def _state(**kw):
        from beamshell.controller import parse_daydream_packet
        return parse_daydream_packet(_dd_packet(**kw))

    def test_click_edge_fires_once(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        self.assertEqual(g.feed(self._state(buttons=0x1)), ["activate"])
        self.assertEqual(g.feed(self._state(buttons=0x1)), [])
        self.assertEqual(g.feed(self._state()), [])
        self.assertEqual(g.feed(self._state(buttons=0x1)), ["activate"])

    def test_app_home_vol_buttons(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        self.assertEqual(g.feed(self._state(buttons=0x4)), ["back"])
        self.assertEqual(g.feed(self._state(buttons=0x4 | 0x2)), ["recenter"])
        g2 = ControllerGestures()
        self.assertEqual(g2.feed(self._state(buttons=0x10)), ["next"])
        self.assertEqual(g2.feed(self._state(buttons=0x8)), ["prev"])

    def test_swipe_right_is_next(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        for x in (40, 90, 140, 200):
            self.assertEqual(g.feed(self._state(touch=(x, 128))), [])
        self.assertEqual(g.feed(self._state()), ["next"])  # finger lifts

    def test_swipe_left_is_prev(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        for x in (200, 120, 40):
            g.feed(self._state(touch=(x, 128)))
        self.assertEqual(g.feed(self._state()), ["prev"])

    def test_click_suppresses_swipe(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        g.feed(self._state(touch=(40, 128)))
        self.assertEqual(g.feed(self._state(touch=(120, 128), buttons=0x1)), ["activate"])
        g.feed(self._state(touch=(200, 128), buttons=0x1))
        self.assertEqual(g.feed(self._state()), [])   # release: no extra 'next'

    def test_vertical_swipes_are_up_down(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        for y in (200, 120, 40):                       # drag toward the top edge
            g.feed(self._state(touch=(128, y)))
        self.assertEqual(g.feed(self._state()), ["up"])
        g2 = ControllerGestures()
        for y in (40, 120, 200):
            g2.feed(self._state(touch=(128, y)))
        self.assertEqual(g2.feed(self._state()), ["down"])

    def test_short_or_diagonal_touch_no_swipe(self):
        from beamshell.controller import ControllerGestures
        g = ControllerGestures()
        g.feed(self._state(touch=(100, 100)))
        g.feed(self._state(touch=(120, 110)))          # short drag
        self.assertEqual(g.feed(self._state()), [])
        g.feed(self._state(touch=(40, 40)))
        g.feed(self._state(touch=(200, 220)))          # diagonal
        self.assertEqual(g.feed(self._state()), [])


class TestPointerGate(unittest.TestCase):
    def test_static_pointer_is_inactive(self):
        from beamshell.controller import PointerGate
        gate = PointerGate()
        self.assertFalse(gate.feed(10.0, 0.0, now=0.0))
        self.assertFalse(gate.feed(10.0, 0.0, now=0.1))

    def test_movement_activates_then_expires(self):
        from beamshell.controller import PointerGate
        gate = PointerGate(move_deg=1.0, window_s=0.6)
        gate.feed(10.0, 0.0, now=0.0)
        self.assertTrue(gate.feed(12.0, 0.0, now=0.1))    # moved 2 deg
        self.assertTrue(gate.feed(12.0, 0.0, now=0.5))    # still in window
        self.assertFalse(gate.feed(12.0, 0.0, now=0.8))   # idle past window


class TestWindowManipulation(unittest.TestCase):
    """Nebula-style focused-window resize + push/pull (app mode)."""

    @staticmethod
    def _app_shell(**attrs):
        """A Shell stand-in with just the state the manipulation handlers touch
        (constructing a real Shell needs a GL context)."""
        from types import SimpleNamespace

        from beamshell import shell as sh
        state = dict(mode=sh.APP, _app_scale=1.0, _app_dist=sh.APP_DIST_DEFAULT)
        state.update(attrs)
        return SimpleNamespace(**state)

    def test_focus_model_places_and_scales(self):
        from beamshell.shell import focus_model
        mat = focus_model(0.8, 0.5, distance=2.0, scale=1.5)
        v = _apply(mat, [1.0, 1.0, 0.0, 1.0])
        self.assertTrue(approx(v[0], 0.8 * 1.5))
        self.assertTrue(approx(v[1], 0.5 * 1.5))
        self.assertTrue(approx(v[2], -2.0))

    def test_resize_steps_and_clamps(self):
        from beamshell import shell as sh
        s = self._app_shell()
        sh.Shell.on_next(s)
        self.assertTrue(approx(s._app_scale, sh.APP_SCALE_STEP))
        sh.Shell.on_prev(s)
        self.assertTrue(approx(s._app_scale, 1.0))
        for _ in range(50):
            sh.Shell.on_next(s)
        self.assertTrue(approx(s._app_scale, sh.APP_SCALE_RANGE[1]))
        for _ in range(100):
            sh.Shell.on_prev(s)
        self.assertTrue(approx(s._app_scale, sh.APP_SCALE_RANGE[0]))

    def test_push_pull_steps_and_clamps(self):
        from beamshell import shell as sh
        s = self._app_shell()
        sh.Shell.on_farther(s)
        self.assertTrue(approx(s._app_dist, sh.APP_DIST_DEFAULT + sh.APP_DIST_STEP))
        for _ in range(50):
            sh.Shell.on_farther(s)
        self.assertTrue(approx(s._app_dist, sh.APP_DIST_RANGE[1]))
        for _ in range(100):
            sh.Shell.on_closer(s)
        self.assertTrue(approx(s._app_dist, sh.APP_DIST_RANGE[0]))

    def test_launcher_mode_ignores_push_pull(self):
        from beamshell import shell as sh
        s = self._app_shell(mode=sh.LAUNCHER)
        sh.Shell.on_farther(s)
        sh.Shell.on_closer(s)
        self.assertTrue(approx(s._app_dist, sh.APP_DIST_DEFAULT))


class TestPointerSelection(unittest.TestCase):
    def test_select_by_yaw_picks_nearest(self):
        sc = scene.LauncherScene(scene.CylinderLayout(step_deg=20.0))
        sc.set_panels([scene.Panel(id=str(i), title=str(i), yaw_deg=0.0)
                       for i in range(3)])          # laid out at -20, 0, +20
        self.assertEqual(sc.select_by_yaw(15.0), 2)
        self.assertEqual(sc.select_by_yaw(-8.0), 1)
        self.assertEqual(sc.select_by_yaw(-45.0), 0)


if __name__ == "__main__":
    unittest.main()
