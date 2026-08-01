"""Headless GL smoke test: build the StereoRenderer and draw one frame into an FBO.

Skips automatically when moderngl or a (standalone/EGL) GL context isn't available, so
it runs on a GPU/CI box and no-ops elsewhere. Verifies the VAOs, uniforms, textures and
per-eye draw path that pure-logic tests can't reach.
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zoetrope import mathutil as m, stereo
from zoetrope.scene import Panel


def _make_ctx():
    import moderngl
    return moderngl.create_standalone_context()


class TestHeadlessRender(unittest.TestCase):
    def setUp(self):
        try:
            self.moderngl = __import__("moderngl")
            self.ctx = _make_ctx()
        except Exception as e:  # noqa: BLE001
            raise unittest.SkipTest(f"no headless GL context: {e}")

    def tearDown(self):
        ctx = getattr(self, "ctx", None)
        if ctx is not None:
            ctx.release()

    def _solid_texture(self, rgba):
        return self.ctx.texture((2, 2), 4, bytes(rgba) * 4)

    def test_draw_one_frame(self):
        from zoetrope.renderer import StereoRenderer

        renderer = StereoRenderer(self.ctx)
        w, h = 640, 360
        color = self.ctx.renderbuffer((w, h))
        depth = self.ctx.depth_renderbuffer((w, h))
        fbo = self.ctx.framebuffer(color_attachments=[color], depth_attachment=depth)

        panel = Panel(id="a", title="A", yaw_deg=0.0, width_m=0.6, height_m=0.4,
                      texture=self._solid_texture([220, 40, 40, 255]), stereo_mode="mono")
        model = m.mat4_mul(m.mat4_translate((0.0, 0.0, -2.0)), _scale(0.6, 0.4))
        floor = m.mat4_mul(
            m.mat4_translate((0.0, -0.7, 0.0)),
            m.mat4_mul(m.mat4_from_quat(m.q_from_axis_angle((1, 0, 0), -1.5708)),
                       _scale(12.0, 12.0)))

        eyes = stereo.eye_matrices(stereo.HeadPose(), w, h, 48.0, 0.063)
        # Should not raise, and should draw something (not a uniform clear color).
        renderer.render((w, h), [(panel, model)], eyes, floor, "a", target=fbo)

        pixels = fbo.read(components=3)
        self.assertEqual(len(pixels), w * h * 3)
        self.assertGreater(len(set(pixels)), 1, "framebuffer is uniform; nothing drew")

    def test_shell_launcher_frame_with_cursor(self):
        """Full launcher path headlessly: dashboard slab + labeled rails
        + clock + pointer cursor."""
        import tempfile

        from zoetrope.renderer import StereoRenderer
        from zoetrope.shell import Shell

        renderer = StereoRenderer(self.ctx)
        w, h = 640, 360
        fbo = self.ctx.framebuffer(
            color_attachments=[self.ctx.renderbuffer((w, h))],
            depth_attachment=self.ctx.depth_renderbuffer((w, h)))
        with tempfile.TemporaryDirectory() as media:
            shell = Shell(self.ctx, media, None)
            shell.update(1 / 60, stereo.HeadPose())
            backdrop = shell.backdrop()
            self.assertIsNotNone(backdrop)
            eyes = stereo.eye_matrices(stereo.HeadPose(), w, h, 48.0, 0.063)
            renderer.render((w, h), shell.panels_models(), eyes,
                            shell.floor_model(), shell.selected_id(),
                            target=fbo, cursor=(12.0, -4.0),
                            backdrop=backdrop)
            # Same revision on the next frame: the cached VAO is reused.
            renderer.render((w, h), shell.panels_models(), eyes,
                            shell.floor_model(), shell.selected_id(),
                            target=fbo, backdrop=shell.backdrop())
            shell.close()
        self.assertGreater(len(set(fbo.read(components=3))), 1)

    def test_draw_mono_frame(self):
        """The 2D (mono) path — single full-frame viewport — must also render."""
        from zoetrope.renderer import StereoRenderer

        renderer = StereoRenderer(self.ctx)
        w, h = 640, 360
        color = self.ctx.renderbuffer((w, h))
        depth = self.ctx.depth_renderbuffer((w, h))
        fbo = self.ctx.framebuffer(color_attachments=[color], depth_attachment=depth)

        panel = Panel(id="a", title="A", yaw_deg=0.0, width_m=0.6, height_m=0.4,
                      texture=self._solid_texture([40, 220, 120, 255]), stereo_mode="mono")
        model = m.mat4_mul(m.mat4_translate((0.0, 0.0, -2.0)), _scale(0.6, 0.4))
        floor = m.mat4_translate((0.0, -0.7, 0.0))
        eyes = stereo.mono_matrices(stereo.HeadPose(), w, h, 48.0)
        self.assertEqual(len(eyes), 1)
        renderer.render((w, h), [(panel, model)], eyes, floor, "a", target=fbo)
        self.assertGreater(len(set(fbo.read(components=3))), 1)


def _scale(sx, sy):
    s = m.mat4_identity()
    s[0], s[5] = sx, sy
    return s


if __name__ == "__main__":
    unittest.main()
