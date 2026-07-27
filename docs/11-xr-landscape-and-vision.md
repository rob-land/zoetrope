# 11 — The XR landscape and where zoetrope is going

*Written 2026-07-19 from a research pass over the Linux XR ecosystem, vendor software,
and academic AR/HCI literature. Companion docs: [12](12-interaction-design.md) (how you
drive it) and [13](13-app-catalog-and-roadmap.md) (what runs on it).*

## The landscape, briefly

**Linux XR stacks.** The open-source XR world has converged on
[Monado](https://monado.freedesktop.org/) as the OpenXR runtime (Collabora, active
through [FOSDEM 2026](https://fosdem.org/2026/events/attachments/T38AKM-monado-and-beyond/slides/267345/monado_an_tfzl8ak.pdf)).
On top of it sit three desktop-in-XR projects, each with a lesson for us:

| Project | What it is | Lesson for zoetrope |
|---|---|---|
| [xrdesktop](https://www.collabora.com/news-and-blog/news-and-events/xrdesktop-014-with-openxr-support-released.html) | Existing desktop windows lifted into XR (GNOME/KDE integration) | Mirroring a 2D desktop is the *bridge* use case, not the destination |
| [Stardust XR](https://vronlinux.org/) | A true XR display server with spatial widgets; runs as overlay too | The long-term "native spatial shell" model; modular, Wayland-friendly |
| [wlx-overlay-s](https://wiki.archlinux.org/title/Virtual_reality) | Wayland/X11 desktop access from inside VR overlays | Small, pragmatic, ships today — zoetrope's spiritual sibling |
| [SimulaVR](https://simulavr.com/) | A whole Linux-VR laptop-replacement OS (Godot + NixOS) | **Text legibility is the whole game** for productivity; their low-pass filter work is why people can code in it |
| [Breezy Desktop](https://github.com/wheaney/breezy-desktop) | wheaney's GNOME/KDE virtual-monitor tool over XRLinuxDriver | Already solves "extra monitors on GNOME"; we interop with its driver — don't rebuild it, complement it |

**Vendor software** (what "finished" consumer UX looks like):
- XREAL's own [Nebula / One-series firmware](https://us.shop.xreal.com/blogs/buying-guide/user-guide_xreal-one-series)
  ships four display behaviors that users now expect as table stakes: **Anchor** (screen
  fixed in space), **Smooth Follow** (screen eases toward your gaze center), **Sideview**
  (small screen parked in a corner while you walk), and **Ultrawide** (one huge curved
  virtual monitor). The One Pro does anchor/follow *on-glasses* (the X1 chip), which is
  why our host-side tracking must ask the glasses to stop stabilizing, or cooperate with it.
- [Viture SpaceWalker](https://www.viture.com/store/productivity) does up to **three
  virtual monitors** on macOS/Windows with grid layouts and a "code mode";
  [Rokid AR Spatial](https://global.rokid.com/products/rokid-ar-spatial) sells a dedicated
  Android puck. Reviews consistently ding free-form window placement as *less* usable than
  simple grid/arc layouts — validation for zoetrope's cylinder-arc approach.
- The 2025–26 "AI glasses" wave (Meta Ray-Ban Display, Even Realities, Rokid Glasses)
  found its killer apps in **live captions/translation, teleprompter, navigation
  glances, and hands-free capture** — tiny, glanceable, mostly-text overlays; not
  immersive 3D. (See [hearing-accessibility roundup](https://www.hearingtracker.com/hearing-glasses/hear-with-your-eyes-five-ar-live-captioning-glasses),
  [Meta Ray-Ban Display](https://www.meta.com/ai-glasses/meta-ray-ban-display/).)

**Research picks** that shaped the interaction doc:
- Pointing on smart glasses: gaze/head pointing is fast but imprecise; a physical
  pointer (mouse/controller) wins for precision ([comparison study](https://arxiv.org/pdf/1905.05810)).
  Head-pointing + a *big-target UI* (our tile arc) is the sweet spot when no controller is present.
- Input taxonomy: handheld (phone, controller) / on-body touch (rings, frames) /
  touchless (voice, gaze, gesture) ([survey](https://ar5iv.labs.arxiv.org/html/1707.09728)).
  A shell should treat these as interchangeable *event sources* — which zoetrope
  already does (keyboard, Daydream, head gaze all emit the same event set).
- Driving: AR content placement is safety-critical; imagery far from the forward view
  degrades lane-keeping, and "conformal" world-locked AR arrows are **not**
  automatically safer than a simple fixed HUD ([review](https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2443252),
  [driving-nav study](https://arxiv.org/pdf/2404.18357)). Implication: a driving mode, if we
  ever ship one, is a minimal, fixed, peripheral glance display — not floating world arrows.
- Text-productivity threshold: ~45 pixels-per-degree is where coding/writing stops
  hurting. The One Pro (~49 PPD per XREAL) is *above* it — this hardware can genuinely
  host a workday, which is why the desktop-monitor use case is worth building well.

## Vision: what "1.0" is

**zoetrope 1.0 is a spatial session for Linux — one codebase, two postures:**

1. **Companion posture (supplementary).** Your laptop/phone works normally; plugging in
   the glasses adds a *spatial surround* — 1-3 virtual monitors, floating media panels, a
   glanceable ambient layer (clock, notifications, now-playing) arranged on the arc
   around your physical screen. You keep your mouse/keyboard; the glasses are extra
   real estate. (Interop: this posture can also simply *host Breezy Desktop* — our kiosk
   already runs the same driver.)
2. **Primary posture.** The glasses are the only display (phone in pocket / laptop lid
   closed / kiosk mode). zoetrope is the whole interface: launcher arc, spatial apps,
   real Wayland apps hosted as floating panels via a nested compositor, driven by
   whatever input is at hand (head gaze, phone-as-touchpad, Daydream, BT keyboard).

The same scene graph, renderer, tracking, and input-event model serve both; what differs
is *which panels exist* (mirrored outputs vs. native apps) and *how much chrome* we draw.

### Architecture evolution to get there

```
today                         next                          1.0
─────                         ────                          ───
GL shell w/ media apps   →    + nested Wayland compositor   →  Wayland apps as panels
                              (wlroots/Smithay headless,       everywhere, incl. phone
                              wl outputs → GL textures)
3DoF via XRLinuxDriver   →    + anchor/follow/sideview      →  display-behavior modes
                              as *host-side* modes             matching Nebula's four
media tiles              →    + terminal, screen-mirror,    →  app SDK: a panel + event
                              web remote                       contract any process can join
one output               →    + virtual outputs             →  1-3 spatial monitors
                              (kiosk sway headless outputs)    w/ grid/arc snapping
```

The **nested-compositor step is the keystone** (roadmap #4 in [10](10-linux-shell-design.md)):
once arbitrary Wayland clients render into our panels, "app development" for zoetrope
mostly stops being zoetrope's problem — any Linux app is a spatial app. Stardust XR
and wlx-overlay-s prove both the concept and the plumbing (wlr layer-shell/screencopy,
virtual outputs).

### Phone and desktop are the same product

postmarketOS/Mobian convergence is real but rough ([pmOS 26.06](https://linuxiac.com/postmarketos-26-06-brings-fresh-linux-phone-updates/)
ships GNOME 50 across 250+ devices; Phosh external-display support works but window
management is primitive). That's an *opportunity*: on a Linux phone, zoetrope IS the
convergence story — the phone in your pocket is the compute, the glasses are the
display, the phone screen is the touchpad. No Phosh-on-a-monitor awkwardness; the
spatial shell is the desktop mode. Same binary as the laptop kiosk, different input
defaults (see [12](12-interaction-design.md)).

## Honest constraints (so the vision stays real)

- **3DoF, not 6DoF.** No leaning around windows; comfort features (anchor modes,
  recenter, sway damping) matter more. 6DoF stays a stretch goal behind Monado+SLAM.
- **Birdbath optics ≈ 46° FoV.** "Rooms full of monitors" is marketing; 1-3 usable
  panels plus a peripheral ambient layer is the honest ceiling. Design for glances
  and focus-switching, not wall-of-glass.
- **The X1 chip owns the good stabilization.** Host-side anchor will always be a bit
  worse than on-glasses anchor; the pragmatic 1.0 uses the glasses' own anchor for the
  main screen where possible and host tracking for the *surround* layer.
- **Battery on phones.** GL at 60 fps + USB-C DP is a heater; the ambient layer needs a
  low-power path (damped refresh, dark pixels are free on OLED-ish birdbath displays).

Sources: [Monado](https://monado.freedesktop.org/) ·
[FOSDEM 2026 Monado talk](https://fosdem.org/2026/events/attachments/T38AKM-monado-and-beyond/slides/267345/monado_an_tfzl8ak.pdf) ·
[xrdesktop 0.14](https://www.collabora.com/news-and-blog/news-and-events/xrdesktop-014-with-openxr-support-released.html) ·
[VR on Linux](https://vronlinux.org/) · [ArchWiki VR](https://wiki.archlinux.org/title/Virtual_reality) ·
[SimulaVR](https://simulavr.com/) · [Breezy Desktop](https://github.com/wheaney/breezy-desktop) ·
[XREAL One guide](https://us.shop.xreal.com/blogs/buying-guide/user-guide_xreal-one-series) ·
[Viture productivity](https://www.viture.com/store/productivity) ·
[Rokid AR Spatial](https://global.rokid.com/products/rokid-ar-spatial) ·
[smart-glasses pointing study](https://arxiv.org/pdf/1905.05810) ·
[interaction survey](https://ar5iv.labs.arxiv.org/html/1707.09728) ·
[AR-HUD safety review](https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2443252) ·
[driving-nav workload study](https://arxiv.org/pdf/2404.18357) ·
[pmOS 26.06](https://linuxiac.com/postmarketos-26-06-brings-fresh-linux-phone-updates/) ·
[live-captions roundup](https://www.hearingtracker.com/hearing-glasses/hear-with-your-eyes-five-ar-live-captioning-glasses) ·
[Meta Ray-Ban Display](https://www.meta.com/ai-glasses/meta-ray-ban-display/)
