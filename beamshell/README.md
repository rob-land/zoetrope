# beamshell

A **Nebula-like spatial shell for XREAL glasses on Linux** — laptops and Wayland Linux phones
that support USB-C DisplayPort Alt Mode. When the glasses are plugged in it puts them into
3840×1080 side-by-side 3D, renders a floating arc of app tiles that you point at with your
head (3DoF), and can open a **3D movie player** and **3D photo viewer** from the launcher.

This is **v0.1**: the pure-logic core (detection, stereo math, scene/gaze layout) is complete
and unit-tested; the GL/tracking/app layers are working first-cut code that needs the real
glasses + GPU to exercise. See "Status" below for exactly what's verified.

> Design rationale, architecture, and roadmap: `../docs/10-linux-shell-design.md`.
> Where this is going: `../docs/11` (vision), `../docs/12` (interaction), `../docs/13` (apps + milestones).
> Hardware facts this builds on: `../docs/06-xreal-one-pro-and-eye.md`, `../docs/09-live-capture-one-pro-eye.md`.

## Quick start

```bash
cd beamshell
python -m pip install -e .            # core deps: moderngl, glfw, Pillow
# optional:  pip install -e '.[video,hotplug,heic,controller,term]'
#            movie player · hotplug · HEIC · Daydream BLE · terminal app

# Develop without glasses (windowed SBS preview, head auto-sways):
python -m beamshell run --mode preview --sway

# See what's detected:
python -m beamshell info

# With glasses plugged in (auto-detects the XREAL DP output + USB):
python -m beamshell run            # --mode auto picks 'glasses' when the DP output is found
```

Keys: **arrows** select · **Enter** open · **Backspace** back · **R** recenter · **Esc** quit.
(With real head tracking, the focused tile follows your gaze; arrows are for the preview.)

Inside an app (photo/movie), the window moves like Nebula's: **←/→** smaller/bigger,
**↑/↓** push farther / pull closer (Daydream: horizontal swipe or volume keys = size,
vertical swipe = push/pull). Size and distance persist until you quit.

## Terminal app

A floating dev console (`pip install -e '.[term]'`): a **Terminal** tile opens `$SHELL`
on a pty (pyte VT100 emulation, 100×30). While it's open the keyboard types into it —
printables, Enter, Backspace, Tab, and **Ctrl+A–Z** (so Ctrl+C works); **Esc** goes back
to the launcher instead of quitting, **Ctrl+R** recenters, and arrows still move/resize
the window.

## Phone as touchpad (web remote)

`beamshell run --remote` serves a one-page touchpad on port 8577 — open the printed URL
in your phone's browser: tap = open, swipes = navigate/size/distance, buttons for
back/recenter, and a text field that types into the terminal. This is the prototype of
the Linux-phone posture where the phone screen is the primary input (`../docs/12`).
**Opt-in and unauthenticated** — anyone on your LAN can send input while it's running.

## Put 3D media in place

**Movies.** The "3D Movies" tile browses your library: `--library DIR`,
`$BEAMSHELL_LIBRARY`, or — with zero setup — Ripsaw's `library_root`
(`~/.config/ripsaw/config.json`). Jellyfin-style `Title (Year)` folders give the
tiles their names and `poster.jpg`/`folder.jpg` art. Opening a title probes it
through the **ripplay engine** (`ripplay` on PATH or `$RIPPLAY_BIN`): packed SBS
files play directly in libmpv, while H.264 MVC (straight off a 3D Blu-ray rip),
MV-HEVC, and over-under stream through `ripplay stream` as composed Full-SBS.
Without ripplay installed, packed-SBS files still play via filename heuristics.

**Photos.** The "3D Gallery" tile flips through every still it finds in the
media dir + library (left/right arrows navigate): `.mpo`, `.jps`, wide SBS
images, explicit `*_l`/`*_r` (or `*-left`/`*-right`) stereo pairs, and flat
images; `.heic` spatial photos too with `pillow-heif` installed.

The demo media dir also still works: default `./media` (or `$BEAMSHELL_MEDIA`).
Thumbnails are cached under `~/.cache/beamshell/thumbs`. A clock floats above
the tile arc, and the focused tile zooms slightly. With a Daydream controller
connected, a glowing cursor dot shows where you're pointing.

## Run when the glasses are plugged in

Two options (see `packaging/`):
1. **User service + hotplug watcher** (`pip install -e '.[hotplug]'`):
   ```bash
   cp packaging/beamshell.service ~/.config/systemd/user/
   systemctl --user enable --now beamshell.service   # runs `beamshell watch`
   ```
2. **udev rule** (also grants hidraw access for direct IMU reads):
   ```bash
   sudo cp packaging/70-xreal-glasses.rules /etc/udev/rules.d/
   sudo udevadm control --reload
   ```

## Head tracking

`--tracker auto` tries, in order:
1. **xrdriver** — read orientation from [wheaney/XRLinuxDriver](https://github.com/wheaney/XRLinuxDriver)
   if it's running (it already supports the One/One Pro). **Recommended.**
2. **hidraw** — read the glasses IMU directly and fuse it here (gyro + accel). The exact One Pro
   HID report layout still needs confirming from a live capture (`../docs/08`); the parser has a
   documented Air-2 default and a `TODO`.
3. **stub** — identity/sway, so the shell runs with no hardware.

> Turn **off** the glasses' onboard stabilizer/anchor for host-driven tracking (see `../docs/06`).
> 6DoF via the XREAL Eye is out of scope for v0.1 (the X1 chip keeps that pose closed).

The tracker needs XRLinuxDriver configured with `disabled=false`, `output_mode=external_only`,
`external_mode=opentrack` in `~/.config/xr_driver/config.ini` (the driver's compiled-in default
is **disabled**). `packaging/console/install.sh` writes these lines for you.

## Daydream controller (optional laser pointer)

A Google Daydream controller works as a BLE pointer/remote (`pip install -e '.[controller]'`,
on by default via `--controller auto` when bleak is installed):

- **Point** to select a tile (a moving controller beats head gaze; leave it still and gaze resumes)
- **Click (touchpad press)** open · **App** back · **Home** recenter head + pointer
- **Swipe left/right** or **volume keys** prev/next (in an app: smaller/bigger)
- **Swipe up/down** (in an app) push the window farther / pull it closer

Pair it once at the system level: hold **Home** until the LED pulses, then
`bluetoothctl` → `scan on` → `pair <MAC>` (it advertises as "Daydream controller").
After that beamshell auto-connects whenever the controller wakes. The orientation
axis signs are a first-hardware-test guess; tune live with `BEAMSHELL_DD_SIGNS="1,1,1"`.

## Status — what's verified vs. needs hardware

| Layer | State |
|---|---|
| `config`, `mathutil`, `detect`, `stereo`, `scene`, `controller` parsing | ✅ **unit-tested** (`pytest`, 52 tests) |
| `tracking` (stub / hidraw / xrdriver) | ✅ xrdriver verified live (opentrack UDP); hidraw offsets still need a One Pro capture |
| `controller` (Daydream BLE) | Parser/gestures unit-tested; BLE scan loop runs; needs the physical controller to pair |
| `display` (find DP output, set SBS, restore) | Real `wlr-randr`/`xrandr` calls; needs the output present |
| `renderer` (moderngl stereo) + `window` (glfw) | Standard patterns; needs a GPU/GL context |
| `apps.photo` (SBS / MPO / pair) | Works with Pillow |
| `apps.movie` (libmpv) | Needs libmpv + python-mpv; least-exercised |
| `apps.term` (pty + pyte) | ✅ tested headlessly incl. live shell round-trip |
| `remote` (phone web-touchpad) | ✅ tested (HTTP round-trip, validation) |

Run the tests:
```bash
python -m pytest -q          # or: python -m unittest discover -s tests
```

## Linux phone notes

The same code targets a Wayland Linux phone (postmarketOS/Mobian) with DP Alt Mode: moderngl uses
GLES via EGL, glfw goes fullscreen on the glasses output, and `wlr-randr` sets the SBS mode under
phosh/sway. The heavy lifting is identical; only packaging differs.

## Layout

```
beamshell/
  config.py     XREAL VID/PIDs, per-model display+optics profiles
  mathutil.py   vec/quat/mat4 (pure python)
  detect.py     USB (sysfs/udev) + EDID glasses detection
  stereo.py     per-eye view/proj + SBS viewports
  scene.py      cylinder panel layout + gaze selection
  tracking.py   3DoF head tracking (xrdriver / hidraw / stub)
  controller.py Daydream BLE pointer (parser + gestures + bleak transport)
  remote.py     phone web-touchpad (HTTP, shared event vocabulary)
  display.py    find the XREAL output, set 3840x1080 SBS, restore
  renderer.py   moderngl stereo renderer (floor grid + panels)
  window.py     glfw window (preview / fullscreen-on-glasses) + input
  shell.py      launcher <-> app state machine
  apps/         base (tiles/textures), photo.py, movie.py, term.py
  main.py       CLI: run / watch / info
tests/          unit tests for the pure-logic core
packaging/      udev rule + systemd user service
```
