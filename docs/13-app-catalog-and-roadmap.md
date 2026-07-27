# 13 — App catalog, AR use cases, and the prioritized roadmap

*Companion to [11](11-xr-landscape-and-vision.md) and [12](12-interaction-design.md).
What is actually worth building for a face-worn display, sorted by honesty.*

## Why "on your face" changes which apps win

A head-mounted display buys four things a monitor can't give: **privacy** (nobody
behind you can read it), **place-independence** (couch, plane, tent, tiny apartment),
**size-independence** (a 200" screen from a 75 g device), and **glanceability**
(information in your periphery while your hands and eyes do something else). Apps
that don't exploit at least one of these are better on a monitor — that's the filter
below.

## Tier 1 — the daily drivers (stationary, build these)

| App | Exploits | Status / plan |
|---|---|---|
| **Virtual monitors** (1-3 panels mirroring/extending the host) | size, place, privacy | The keystone; via nested compositor / wlr virtual outputs. Interop: Breezy Desktop already does GNOME — we complement with the kiosk + phone story |
| **Media theater** (SBS movies, 3D photos) | size, place | ✅ shipped v0.1 |
| **Terminal** | privacy, place | scaffolded in `apps/term.py` — a floating dev console is the single highest-value *native* app for our audience (SimulaVR's whole pitch) |
| **Ambient layer** (clock, battery, notifications, now-playing) | glance | clock ✅; notifications via DBus next |
| **Reader** (PDF/EPUB/long-form, huge type, anchor mode) | size, comfort | natural PhotoApp descendant; pairs with recline — screens can't point at a ceiling, glasses can |
| **Focus cockpit** (one task panel + timer, everything else hidden) | place, glance | trivially a layout preset, weirdly compelling |

## Tier 2 — strong, needs one more ingredient

- **Video calls** — panel + webcam passthrough; needs the nested compositor (browser)
  or a native client; glasses speakers/mic routing (backlog below).
- **Big-picture creative review** (photos at scale, video color pass) — needs color
  accuracy validation on the birdbath optics first.
- **Flight/space/racing sim glass cockpit** — the Linux simpit community already uses
  XR glasses this way; mostly works via Breezy Vulkan today; our value-add is head-yaw
  → view binding for titles that support TrackIR/opentrack (the driver *already*
  speaks opentrack — a config preset, not code).
- **Presentation teleprompter** — notes on your face, slides on the projector; the
  Ray-Ban Display teleprompter is the proof (CES 2026); needs text panel + pager
  events, both of which exist today.

## Walking around town (glanceable AR)

The industry's actual daily-use killer apps are **live captions/translation,
navigation glances, and teleprompter-style text** ([captions roundup](https://www.hearingtracker.com/hearing-glasses/hear-with-your-eyes-five-ar-live-captioning-glasses),
[RayNeo nav guide](https://www.rayneo.com/blogs/news/best-smart-glasses-for-navigation-2026-guide)) —
all mostly-text, all sideview-posture. For zoetrope on a Linux phone:

| Use case | Design (per [12](12-interaction-design.md) sideview rules) | Feasibility |
|---|---|---|
| **Walking navigation** | small head-locked corner card: next turn + distance, voice-first; NOT world-locked arrows | phone GPS + OSM routing (e.g. Valhalla/GraphHopper); very buildable |
| **Live captions / translation** | one-line caption strip, bottom-center | on-device Whisper-class STT on phone SoCs is now plausible; the accessibility payoff is huge |
| **Notification glance** | icon + one line, 3 s, then gone | DBus, easy |
| **Transit / at-a-glance cards** | departure board card while looking up | GTFS APIs, easy |
| **Safety posture** | brightness low, content ≤ 1 line, auto-blank while moving fast, physical dimming available | policy layer, must ship *with* the features |

Caveat: the One Pro is a tethered birdbath — bulkier and darker than the caption-first
glasses. These features are worth having when you're *already* wearing them, but
all-day-wear AR is a different hardware class; we don't need to pretend otherwise.

## Driving — mostly "don't"

The literature is consistent: HUD content far from the forward view degrades
lane-keeping; world-locked AR arrows are **not** automatically safer than a simple
fixed display; cognitive load, not pixels, is the budget
([review](https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2443252),
[study](https://arxiv.org/pdf/2404.18357)). A tethered 46° birdbath that dims the
world is the wrong instrument for driving. Position: **no driving mode** beyond an
explicit parked/passenger mode; if ever revisited, it's ≤ 1 fixed glanceable element
near the forward view, voice-primary, and built on the safety literature — not vibes.

## The backlog (parked features from live testing)

1. **Drift** — observed 2026-07-19. Two-part fix: (a) the driver was
   `calibration_state=NOT_CALIBRATED` — let the glasses sit still for ~15 s after
   plug-in, and expose "recalibrate" (the driver honors a `recalibrate` control flag;
   `xr_driver_cli` can set it) as a zoetrope action next to recenter; (b) long-term,
   on-glasses anchor for the main panel (below).
2. **Anchor / smooth-follow / sideview modes** — host-side per-panel modes are small
   code (damped yaw, head-locked offsets — see [12](12-interaction-design.md));
   on-chip anchor needs the USB control protocol for mode switching (docs/03, 06).
3. **3D auto-switch** — the One-series takes a proprietary USB command to enter SBS;
   Nebula/Beam do it automatically. Capture the command (docs/08 method) while
   toggling 3D in the on-glasses menu, then `display.py` can enter/exit 3D without
   touching the menu. The kiosk already handles the re-EDID dance once the mode flips.
4. **Audio to the glasses speakers** — the One Pro already enumerates as a USB audio
   sink (`sound-card2` in sysfs). This is a WirePlumber/PipeWire default-route rule
   scoped to the kiosk session (route to XREAL card when present, restore on unplug) —
   packaging work, no reverse engineering. High value for movies.
5. **Notifications panel** — DBus `org.freedesktop.Notifications` mirror into the
   ambient layer.

## Sequenced roadmap (supersedes the list in [10](10-linux-shell-design.md) §Roadmap)

```
M1  Comfort & parity      recalibrate action · audio routing · smooth-follow/sideview
    (all small)           per-panel modes · notification glances
M2  The keystone          nested Wayland compositor → real apps as panels;
                          virtual-monitor layout presets (1-3 panels + grid snap)
M3  Phone convergence     pmOS/Mobian packaging · phone-as-touchpad polished
                          (remote.py → native) · battery/thermal budget pass
M4  Out-of-house          sideview walking mode + nav glance card + captions spike
M5  Ecosystem             Monado 3DoF driver · panel/event contract for third-party
                          apps · opentrack head-look preset for sims
```

Scaffolds landing with this doc: `apps/term.py` (terminal panel), `remote.py`
(phone web-touchpad), text-input routing through window/shell — see README.
