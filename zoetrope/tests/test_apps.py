"""Tests for the terminal session (pty + pyte, no GL) and the phone web-remote."""
import json
import os
import sys
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pump_until(session, needle: str, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.pump()
        if any(needle in line for line in session.text_lines()):
            return True
        time.sleep(0.02)
    return False


class TestTermSession(unittest.TestCase):
    def setUp(self):
        try:
            import pyte  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pyte not installed")

    def test_command_output_reaches_screen(self):
        from zoetrope.apps.term import TermSession
        s = TermSession(cols=40, rows=8, argv=["sh", "-c", "echo B00T-OK; sleep 30"])
        try:
            self.assertTrue(_pump_until(s, "B00T-OK"), s.text_lines())
        finally:
            s.close()

    def test_write_input_round_trip(self):
        from zoetrope.apps.term import TermSession
        s = TermSession(cols=40, rows=8, argv=["sh"])
        try:
            # Quotes keep the echoed *command* from matching the marker.
            s.write('echo "W1R""ED"\n')
            self.assertTrue(_pump_until(s, "W1RED"), s.text_lines())
        finally:
            s.close()

    def test_render_screen_image(self):
        import pyte

        from zoetrope.apps.term import CELL_H, CELL_W, PAD, render_screen
        screen = pyte.Screen(20, 5)
        pyte.ByteStream(screen).feed(b"hello")
        img = render_screen(screen)
        self.assertEqual(img.size, (20 * CELL_W + 2 * PAD, 5 * CELL_H + 2 * PAD))
        self.assertEqual(screen.dirty, set())     # render clears dirty tracking
        self.assertGreater(len(img.getcolors(maxcolors=4096) or []), 1)

    def test_close_is_idempotent_and_kills_child(self):
        from zoetrope.apps.term import TermSession
        s = TermSession(cols=20, rows=4, argv=["sleep", "60"])
        pid = s.pid
        s.close()
        s.close()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                if os.waitpid(pid, os.WNOHANG) != (0, 0):
                    break
            except ChildProcessError:
                break
            time.sleep(0.05)
        else:
            self.fail("child survived close()")


class TestRemoteServer(unittest.TestCase):
    def setUp(self):
        from zoetrope.remote import RemoteServer
        self.srv = RemoteServer(port=0, bind="127.0.0.1")
        self.base = f"http://127.0.0.1:{self.srv.port}"

    def tearDown(self):
        self.srv.close()

    def _post(self, obj, path="/event"):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        return urllib.request.urlopen(req, timeout=5)

    def test_serves_touchpad_page(self):
        html = urllib.request.urlopen(self.base + "/", timeout=5).read().decode()
        self.assertIn("zoetrope remote", html)
        self.assertIn("touchstart", html)

    def test_event_round_trip_and_validation(self):
        self._post({"ev": "next"})
        self._post({"ev": "recenter"})
        self._post({"ev": "rm -rf"})              # not in the vocabulary
        time.sleep(0.05)
        self.assertEqual(self.srv.poll_events(), ["next", "recenter"])
        self.assertEqual(self.srv.poll_events(), [])   # drained

    def test_text_round_trip_and_limits(self):
        self._post({"text": "ls\r"})
        self._post({"text": "x" * 5000})          # over the 1024 cap: dropped
        self._post({"text": 42})                  # wrong type: dropped
        time.sleep(0.05)
        self.assertEqual(self.srv.poll_text(), "ls\r")

    def test_bad_requests(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError):
            self._post({"ev": "next"}, path="/nope")
        req = urllib.request.Request(self.base + "/event", data=b"not json",
                                     method="POST")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(req, timeout=5)


if __name__ == "__main__":
    unittest.main()
