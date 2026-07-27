# 10 — Design: `beamshell`, a Nebula-like Linux Shell

Design notes for the `beamshell` project (`../beamshell/`) — a spatial shell that launches
when XREAL glasses are plugged into a Linux laptop or a Wayland Linux phone with DP Alt Mode,
renders a Nebula-like floating launcher in 3DoF, and opens a 3D movie player and 3D photo
viewer. Stack (chosen with the user): **Python + moderngl + libmpv**.

## Why this stack

- **Transparent & hackable** — every layer is readable Python; the user is a tinkerer.
- **Verifiable now** — the pure-logic core (detection, stereo math, scene/gaze) is stdlib-only
  and unit-tested (18 tests) without a GPU or the glasses.
- **Portable** — moderngl runs GL on the laptop and GLES/EGL on a phone; glfw fullscreens on the
  glasses output; `wlr-randr` sets the SBS mode under sway/phosh/wayfire. Same code both places.
- **Codec-complete video** — libmpv plays anything (H.264/HEVC/MV-HEVC), rendered into a GL FBO.
- Alternatives considered: **Godot 4** (nicer UI, weaker built-in codecs, can't verify headless
  here) and **Monado/OpenXR** (most reusable, heaviest setup, no One Pro driver upstream yet). We
  can still expose beamshell's tracker/renderer through Monado later (see Roadmap).

## Architecture

```
                 ┌──────────────────────────────────────────────┐
  plug event ───▶│ detect  (USB VID 0x3318 + glasses PID;        │
  (udev/sysfs)   │          EDID PnP 'MRG'/'NRL' on a DP output) │
                 └───────────────┬──────────────────────────────┘
                                 │ GlassesProfile (One Pro: 3840x1080@60 SBS, fov, ipd)
        ┌────────────────────────┼───────────────────────────────┐
        ▼                        ▼                                ▼
   display                   tracking                         window (glfw)
   set 3840x1080 SBS      3DoF orientation quat            fullscreen on glasses
   (wlr-randr/xrandr)     (xrdriver│hidraw│stub)            │ or windowed preview
        │                        │                          ▼
        │                        │                    moderngl GL context
        └────────────┬───────────┘                          │
                     ▼                                       ▼
                  stereo  ── per-eye view/proj + SBS ──▶  renderer (StereoRenderer)
                     ▲                                       │ draws floor grid + panels
                     │                                       │ twice (L viewport | R viewport)
                  scene / shell  ◀── apps (launcher tiles, photo, movie) ──┘
                  cylinder layout + gaze selection + state machine
```

Data flow each frame: `tracker.get_orientation()` → `HeadPose` → `shell.update()` (gaze picks the
focused tile) → `stereo.eye_matrices()` (split the framebuffer L|R, offset cameras by ½ IPD) →
`renderer.render()` (floor grid + textured panels per eye) → `window.swap()`.

## Key design decisions

- **Detection needs VID *and* a glasses PID.** XREAL's VID `0x3318` is also used by XREAL *hosts*
  (the Beam Pro's own USB gadget enumerated as `0x3318:0x0528` here). We require the product-id to
  be a known/ in-range glasses id (`0x423`–`0x442`), and separately confirm via the DP EDID
  (`MRG`/`NRL` + product id 16640 = One Pro). This was a real bug caught during bring-up.
- **SBS 3D = split the framebuffer, not two windows.** The glasses take one 3840×1080 frame and
  send the left 1920 px to the left eye, right 1920 px to the right eye. We render the scene twice
  into the two halves with cameras offset by ½ IPD. Birdbath optics ⇒ no distortion mesh needed.
- **Panels carry a `stereo_mode`.** `mono` (same image both eyes), `sbs` (one wide texture, each
  eye samples its half — for 3D SBS movies), or `pair` (separate L/R textures — for MPO/stereo
  photos). The renderer picks the right texture + UV sub-rect per eye.
- **Gaze selection.** The focused launcher tile is the one whose azimuth on the cylinder is nearest
  the head's yaw. Arrow keys override for the no-hardware preview.
- **Lazy heavy imports.** moderngl/glfw/PIL/mpv are imported inside functions so the whole package
  (and its tests) import cleanly on a machine without them.
- **3DoF only (for now).** The launcher and both apps are head-orientation-locked. 6DoF via the
  XREAL Eye is deliberately out of scope — the X1 chip computes that pose and doesn't expose it to
  the host (see [06](06-xreal-one-pro-and-eye.md)/[09](09-live-capture-one-pro-eye.md)).

## Head tracking sources (`tracking.py`)

1. `XRDriverTracker` — reads orientation from **XRLinuxDriver** if running (it already supports the
   One/One Pro). Preferred; least code; best fusion.
2. `HidRawTracker` — opens the glasses' `/dev/hidraw`, integrates gyro + corrects tilt with accel.
   The exact **One Pro HID report layout is the one open TODO** — the parser defaults to the
   documented Air-2 format; confirm offsets with a live capture (`08`, and the live IMU stream seen
   in `09`).
3. `StubTracker` — identity or gentle sway, so the shell runs with no hardware.

## What's verified vs. pending

| Verified here (no hardware) | Needs the glasses / GPU |
|---|---|
| stereo math, SBS split, eye offsets | GL rendering (moderngl/glfw context) |
| USB + EDID detection incl. host-gadget exclusion | `wlr-randr`/`xrandr` mode switch on the real output |
| cylinder layout + gaze selection | libmpv movie playback into an FBO |
| CLI wiring (`run`/`watch`/`info`), clean imports | HID IMU report offsets for the One Pro |

52 unit tests (`pytest`) cover the first column (incl. Daydream packet/gesture parsing
and a headless-GL launcher frame).

## Roadmap

1. **Bring-up on the laptop** with the One Pro: `beamshell run` (glasses mode), confirm SBS output +
   XRLinuxDriver tracking; tune IPD/FoV per `config.PROFILES["one_pro"]`.
   *2026-07-19: tracking wiring verified live. The driver's compiled-in default is
   `disabled=true`, so `~/.config/xr_driver/config.ini` needs `disabled=false` (the console
   installer now writes it); with that, opentrack packets flow and `XRDriverTracker` tracks
   with ~0.02° jitter at rest. Worn test: yaw correct, pitch was inverted —
   `DEFAULT_OT_SIGNS = (1, -1, -1)` now flips pitch AND roll (both follow from the NWU→
   beamshell axis mapping: driver pitch axis = our -X, roll axis = our -Z). Roll flip is
   derived, not yet confirmed by tilting the head.*
2. **Confirm the HID IMU layout** for a `hidraw` fallback (capture per `08`).
3. **Nicer launcher** — icons, more tiles, a clock/now-playing panel; curved multi-row layout.
   *2026-07-19: first pass done — media thumbnails (ffmpeg frame-grab for movies, left-eye
   crop for SBS), clock panel, icon glyphs, rounded selection glow, focus zoom, controller
   cursor dot. Multi-row layout still open.*
3a. **Daydream controller** *(added 2026-07-19)* — `controller.py` BLE laser pointer:
   point/click/swipe/buttons; packet parser + gestures unit-tested; axis signs
   (`BEAMSHELL_DD_SIGNS`) still need a live pairing to confirm.
3b. **Window manipulation** *(added 2026-07-19)* — Nebula-style resize + push/pull of the
   focused app panel: ←/→ size, ↑/↓ distance (Daydream: h-swipe/volume = size, v-swipe =
   distance), clamped 0.45–2.5× and 0.9–4 m, verified via headless screenshots.
4. **Real windowed apps as panels** — host arbitrary Wayland apps on `VirtualDisplay`-equivalents
   (like Nebula's floating 2D panels) via a nested compositor (wlroots/Smithay) — the big step
   toward a true desktop-in-glasses.
5. **Monado path** — expose the tracker as a Monado 3DoF driver so OpenXR apps (and xrdesktop /
   Stardust XR) work too; keep beamshell as the lightweight native shell.
6. **Phone packaging** — postmarketOS/Mobian APK-equivalent + the systemd user service.
7. **(Stretch) 6DoF** — only if the X1 pose is reverse-engineered or via Monado+Basalt SLAM on the
   Eye's UVC feed.

## Files

See `../beamshell/README.md` for the module-by-module layout and run instructions.
