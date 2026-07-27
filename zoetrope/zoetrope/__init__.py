"""zoetrope — a Nebula-like spatial shell for XREAL glasses on Linux.

Pure-logic modules (config, mathutil, detect, stereo, scene) have no third-party
dependencies. The GL/IO/app modules (renderer, window, tracking, display, apps.*)
import moderngl / glfw / mpv / PIL lazily, so importing this package never fails
just because a rendering dependency is missing.
"""
__version__ = "0.1.0"
