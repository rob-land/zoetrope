# 15 — UI research round 2: competitors, Android XR, the 3DoF canon, Linux prior art, 10-foot grammar

*Survey landed 2026-07-28. Extends [14](14-ui-research-nebula-quest-visionos.md)
(Nebula / Horizon OS / visionOS). Also written for **couch**
(`~/projects/mobile-linux/developed/couch`) — the GTK4 10-foot streaming
shell — which shares the leanback/focus grammar and the ambient-display
ambition; couch-relevant findings are tagged **[couch]**. Sources inline;
per-section deep reports available in session history.*

## The one-paragraph synthesis

Round 2 confirms round 1's architecture and adds an empirical mandate:
**Oculus Go telemetry showed ~70% of use was media** — a movie-first 3DoF
shell is the historically-proven product, and Oculus TV literally ran the
Android TV leanback stack in VR, meaning the row/focus 10-foot grammar *is*
correct spatial UI, not an analogy. The industry's shared vocabulary is now
clear: **named layout presets** (never freeform), the **0DoF / Anchor /
Smooth-Follow triad**, **dual-mode handheld input** (ray + trackpad from the
same device), and **angular units** (Daydream dmm → Android XR dp-to-dmm).
Google has published the numbers Android XR glasses will train users on —
match them and zoetrope feels "normal." And every surviving Linux spatial
project converged on exactly our M2 plan (standalone nested compositor,
apps composited as textures), with **pywlroots** the strongest
implementation candidate. Strategic clock: XREAL + Google ship Project
Aura (Android XR, ≤$1,500) in fall 2026, including a laptop-DP-tether
spatial-desktop demo — our exact use case gets a proprietary competitor,
and our differentiators are Linux-native openness, follow-modes
(reviewers' loudest unmet Android XR want), and the 3DoF-no-runtime
niche nobody else occupies.

## A. Same-class competitors (Viture SpaceWalker · Rokid YodaOS · RayNeo)

**Viture SpaceWalker** — the software leader in our hardware class:
- **Named multi-screen layouts**, not freeform: Single, Dual, Triple,
  Stacked Triple, curved Ultrawide Panoramic, and "Code Mode"
  (portrait–landscape–portrait). Keyboard chords swap layouts; e.g.
  Ctrl+Shift+Alt+X toggles yaw-lock. Screens are real OS displays you drag
  windows across.
- **Smooth Follow = deadzone + damped glide-back**, on by default, applies
  to the *whole layout* (not one screen). The "gimbal feel." Note the
  balance shift: XREAL One's on-chip anchor now beats Viture's host-side
  follow (Beast drifted in comparisons) — consistent with doc 14's
  "stabilization belongs in-glasses" conclusion.
- **Phone-as-controller with two switchable modes**: Laser Pointer (3DoF
  ray, tap=click) and Trackpad (1-finger cursor, 2-finger scroll).
  Documented gaps users hit: no right-click, no drag-select.
- **Immersive 3D**: real-time AI 2D→3D (per-frame monocular depth, three
  depth presets, movie-vs-game latency modes) — the halo feature, but
  needs RTX-4060-class GPU. Their "1-Click 3D" SBS detection is the
  cheaper sibling (we already beat this with real MVC/MV-HEVC decode).
- Their pitfalls: DRM black-screens inside the spatial environment, laggy
  embedded browser, cursor-lost-in-space, news-feed/ads on the launcher
  home (universally disliked — doc 14's "launcher = launcher" again).

**Rokid Station/YodaOS-Master** — the pocket-host posture (≈ our FP5):
- Station 1 was a **Google-certified Android TV device driving glasses** —
  "Chromecast strapped to my face," and it worked (validates leanback).
- Station 2/YodaOS: bottom dock + up to 3 world-fixed side-by-side
  windows, with **named modes**: Theater (single "300-inch" screen),
  Multi-Screen, **Reading Mode** (window reflowed book-like, page-turn by
  tap — a genuinely novel mode worth considering), Motion mode (vehicle
  stabilization).
- Puck input mirrors Viture: trackpad face (multi-touch, usable flat on a
  table) OR held as a 3DoF laser pointer. BT keyboard/mouse/gamepad.
- Complaints: buggy companion app, fan noise under multitasking, "more a
  media device than productivity" — media-first again.

**RayNeo** — one distinctive idea: Mirror Studio's **zone-drag model**
(pick a 2/3/5-screen layout, drag windows into zone placeholders;
Ctrl+1 resets positions; blacks out the laptop panel for privacy). Their
X-series temple-touchpad and Ring were panned — don't rely on tiny
touch surfaces.

**Adopt into zoetrope:** a **layout-preset picker** (arc presets: single /
triptych / theater / reading, per-preset persistence) replacing any
freeform ambitions; yaw-lock and reset chords; phone remote gains an
explicit Laser↔Trackpad mode toggle; right-click and drag as first-class
remote verbs; a Reading mode for the terminal/text panels later.

## B. Android XR (+ Project Aura) — the incoming default

Google's published conventions (developer.android.com/design/ui/xr):
- Panels: default **1024×720 dp**, min 385×595, max 2560×1800; spawn at
  **1.75 m**, depth range 0.75–5 m, constant angular size 0.75–1.75 m;
  conversion **0.868 dp→dmm**; panel center **5° below eye level**;
  primary content within a **41° cone**; 32 dp corner radius.
- Targets **56 dp preferred / 48 dp minimum**, 8 dp spacing; type ≥14 dp,
  normal+ weight, user-scalable.
- **Material XR components**: Orbiters (nav controls floating beside a
  panel, 20 dp offset — same idea as visionOS ornaments), elevation
  ladder (orbiter 16 dp → popup 32 dp → dialog 56 dp), SpaceToggleButton.
- **Additive-display guidance that's directly ours**: on see-through
  optics **black = transparent**; use bright/light colors, add white for
  solidity. The "Glimmer" AI-glasses design language doubles down:
  light-on-shadow, thicker rounder type, depth via shadow weight,
  fade-in/out notifications. This settles zoetrope's palette direction:
  light strokes and vibrant-bright fills on transparency, never dark
  panels.
- Shell model: desktop-like launcher panel (clock/status, system row,
  10-app grid), window "pills" above each app, Home Space (unlimited flat
  panels) vs Full Space (one spatialized app). April 2026 update added
  wall-pinning, 3-window session restore, auto-spatialization (ML 2D→3D
  of the focused window at 1080p30).
- Review verdicts: shell fluidity praised over Quest; complaints = no
  floating windows over immersive apps, weak layout persistence, and —
  notably — **no follow-me/head-locked mode**, an explicit reviewer wish.
  Follow modes are our chance to out-feature the incumbent-to-be.
- **Project Aura** (fall 2026, ≤$1,500): optical see-through, ~70° FOV,
  1920×1200/eye @120 Hz, electrochromic dimming, 91 g, **6DoF + hand
  tracking, no eye tracking**, wired Snapdragon puck that doubles as a
  trackpad, Gemini as headline input. I/O 2026 demoed a **laptop DP
  tether extending the desktop into AR** — our use case, productized.

**Adopt into zoetrope:** match the numbers (1.75 m spawn ≈ our 1.7 m —
already right; 5°-below-eye centers; 41° content cone; 48–56 dp-scale
targets); bright-on-transparent styling; orbiter-style panel controls;
a "reorganize/auto-tidy" action; session restore as table stakes.

## C. The 3DoF canon (Daydream · Oculus Go) — free, complete, proven

**Daydream's design system** (the best-documented 3DoF spec ever
published; still live at developers.google.com/vr):
- **dmm units** (1 mm at 1 m ≈ 0.057°): body text **24 dmm** (hard floor:
  text ≥1.5° subtense); ray/gaze targets **64×64 dmm + 16 dmm padding**
  (head-gaze is coarser than their laser — use ~80 dmm); design panels as
  ordinary 2D at 1 dmm = 1 px (their sticker sheet did exactly this).
- Hard rules that transfer verbatim: nothing nearer 0.5 m; world-locked
  panels on a **cylinder centered on the user** (flat wide panels get
  keystoned/blurry edges — our CylinderLayout is correct); **neck model
  required** for 3DoF solidity (synthesize small positional offset from
  rotation — zoetrope should add this, it's ~10 lines of math); recenter
  must leave the cursor dead-ahead; **reticle renders at the depth of the
  target it's over** (mismatched depths make pointing feel broken — the
  single most important reticle rule).
- Input grammar: touchpad swipe=scroll (required for long lists),
  click=select, app-button=back, hold-home=recenter. Daydream Elements
  (open source) has tuned arm models and Swipe/Click radial menus.
- Text entry is unsalvageable at 3DoF — design zero-typing paths (we
  already do: library browse, no search-by-typing on glasses; voice
  later).

**Oculus Go / Carmack** — the closest historical product to zoetrope:
- **~70% of Go usage was media.** The movie-first bet is empirically
  correct.
- **Oculus TV ran Android TV leanback in VR** — the leanback focus model
  (rows + big focus states + D-pad) is *the* natural 3DoF-buttons UI,
  arguably better than free-cursor pointing for our picker. **[couch]**:
  this is the same grammar couch ships; the two projects should share
  conventions (rails, focus ring behavior, continue-watching rows).
- Carmack's Netflix numbers: virtual screen sized to **~60° FOV**
  deliberately (bigger magnifies artifacts and forces head-scanning —
  "IMAX mode" is a trap); dim the room because ambient light ruins
  perceived black level; **Void Theater** (blank everything) for purity +
  power. His cursor heuristics: act on touch-*release*, suppress cursor
  during scroll flings, auto-hide during playback.
- Perf pattern: UI can render at 30 fps while head-pose reprojection runs
  at panel refresh (their TimeWarp layers ≈ presenting video as a
  compositor quad layer — highest-quality sampling path). Subtitles cost
  power (force per-frame recomposition) — plan for it.
- Go chrome lived **below the horizon** (glance down for dock/status) —
  matches doc 14's "move ambient chrome out of the up-zone."

## D. Linux spatial prior art — the M2 answer

- **Every survivor converged on our M2 shape**: standalone nested
  compositor, apps composited as textures. Collabora tried the other way
  (xrdesktop patching GNOME/KWin), declared it unsustainable, and pivoted
  to exactly this model (wxrd) before stalling. Never mirror/patch a host
  DE.
- **pywlroots is the first-choice implementation** (qtile proves Python
  Wayland compositing is real; wlroots does the protocol grind; wlr
  imports client buffers as textures). The risky seam to spike first:
  sharing an EGL context between wlroots' renderer and moderngl.
  Fallback: a Rust sidecar built like **WayVR's `wayvr` crate**
  (Smithay 0.7; launches Wayland apps, renders to textures, real seats —
  the closest existing implementation of M2, GPL-3, mine it heavily).
- Cheaper pre-M2 milestone: **mirror existing windows** via
  wlr-screencopy/PipeWire (WayVR's `wlx-capture` crate is the reference)
  with uinput injection — gets "your sway windows as panels" before we
  own a compositor.
- **StardustXR**: active, architecturally beautiful (scenegraph server,
  SUIS input routing, panel items); its flatscreen mode runs without
  OpenXR but has no head-tracked-stereo mode — watch, mine ideas,
  possible long-term convergence target (a Python client speaking its
  flatbuffers protocol is feasible).
- **Monado** has 3DoF drivers for the Xreal *Air* family but not One
  Pro (One-series fuses on-chip; different HID). Not needed for the
  shell; relevant only if we later host third-party OpenXR content.
- **Simula** (alive-but-slow): durable lessons = aggressive low-pass/
  supersampling for text legibility on limited panels, gaze-directed
  keyboard focus, spatial workspaces.
- **Immersed** (proprietary): what stuck for users is the
  **virtual-monitor metaphor with per-monitor placement persistence**,
  not free-floating windows — same conclusion as §A's layout presets.
- Zoetrope's niche — 3DoF glasses, no XR runtime, Python — is
  **genuinely unoccupied**.

## E. 10-foot & smart-display grammar — for the movie picker and couch

Head-gaze + buttons is formally the same input class as a D-pad: coarse
pointing + select/back. The whole 10-foot canon therefore transfers to
zoetrope's picker, and it's couch's native grammar. **[couch]** throughout.

**The numbers** (tvOS HIG · developer.android.com/design/ui/tv):
- Safe zones: tvOS 90 pt L/R + 60 pt T/B on 1920×1080; Android TV 48 dp
  horizontal + 27 dp vertical (~5%) on a 960×540 dp canvas.
- Body text ≥ ~29 pt @1080p, titles ≥ 48 pt; sans-serif, no thin weights;
  muted high-contrast palette (TVs oversaturate; AR optics bloom — same
  rule, two reasons).
- Cards: 16:9 default video, **2:3 posters**, 1:1 people/logos; 20 dp
  gaps with the next card *peeking* to signal scrollability; focus scale
  1.025–1.1× (smaller elements scale more) + glow/shadow, animated
  <150 ms.
- Input feel: acknowledge within ~50 ms even if artwork is still loading
  (skeleton cards); slow focus is what makes the official Jellyfin TV
  client the ecosystem's cautionary tale.

**Focus is the interface.** tvOS's focus engine doctrine: no cursor; one
unmistakably focused element at all times; the "lockup" (art + label
scale/move/focus as one unit); focus memory per rail; every direction
purposeful; Back always retreats — no traps. For gaze this means **gaze
gravity** (snap to the element grid), not free pointing. tvOS's
signature parallax tilt on the focused item (2–5 art layers reacting to
sub-threshold thumb motion) maps beautifully to zoetrope: tilt the
focused poster with sub-threshold *head* motion.

**Structure**: single-axis rails of large cards beat dense 2-D grids for
primary browsing (grids fine for "view all"); full-bleed artwork *is*
the UI, chrome collapses when idle; the first rail is the **semantic
resume row** — Android TV's Watch Next model (CONTINUE / NEXT /
WATCHLIST / NEW, each with progress + recency) is the canonical schema,
and for couch it's the natural cross-backend aggregation model across
Jellyfin/Plex/IPTV. Nintendo Switch is the existence proof that the
core loop is "pick from ~12 things in <2 s" — count clicks-to-playback
as a regression metric (Steam's Big Picture redesign added 2–5 clicks
and users noticed). PS5's Control Center gives the overlay rule:
transport/quick-settings/profile **overlay live video, never navigate
away**. Steam Deck's Gamescope+SteamUI (fullscreen game-pad shell over a
desktop Linux stack) is architecturally couch's closest cousin.

**Streaming-UX failure modes to design against:** autoplaying previews
with sound on dwell (punishes the pause-to-read behavior D-pad/gaze
browsing requires); density loss (Netflix's 2025 big-card redesign cut
rows to 3–4 visible titles — "you can see more titles on a phone than
on an 84-inch TV"); chrome creep; file-structure-first layouts
(Jellyfin's official client) instead of experience-first.

**Ambient smart-display grammar for couch** (Echo Show APL + Nest Hub):
1. Three-state machine: Active → **Ambient** after ~10 min idle
   (backdrop + glanceable card deck) → dimmed/off; any input returns to
   Active exactly where the user left off.
2. Rotating home-card deck, each card a plugin with per-profile toggles:
   clock/weather, up-next episode, recently added (*arr), server health,
   IPTV "on now."
3. Persistent overlays outlive the rotation (now-playing, timers pinned
   to a corner strip) — Nest Hub pattern.
4. **Proximity density switching** (Nest Hub's ~4 ft ultrasound rule):
   far = huge type, one fact per card, no controls; near = denser +
   touch targets. Design every ambient card in two density tiers; a
   cheap proxy for proximity is touch/remote pickup.
5. Voice/remote parity: visuals supplement, never gate (APL doctrine —
   every action reachable by voice or one button).
6. Burn-in discipline: no static chrome in ambient, slow drift on art.
7. Profile-aware ambient: kid profile filters the artwork rotation too.

## Consolidated adoption list (rounds 1+2)

Near-term, high-value, all landable in today's Python/moderngl zoetrope:
1. Layout presets + per-preset persistence (A, D-Immersed).
2. Follow-mode triad with pitch-zone handling; whole-layout follow (A;
   the Snap patent US11899204 documents deadzone/damping/pitch-blend
   design — treat as prior-art reference and IP flag).
3. Neck model + reticle-at-target-depth + Carmack cursor heuristics (C).
4. dmm-based sizing pass over tiles/text (C, B numbers; ~80 dmm gaze
   targets, 24 dmm body text).
5. Theater defaults: ~60° screen, dim/void toggle, chrome below horizon,
   act-on-release (C).
6. Bright-on-transparent palette per Android XR/Glimmer (B).
7. Leanback-style movie picker: gaze-gravity focus model, lockups, poster
   rails with peeking, semantic resume row, parallax tilt on focus,
   <2-selections-to-playback — conventions shared with couch (C, E).
8. Phone remote: Laser↔Trackpad modes, 2-finger scroll, right-click verb
   (A); vibration feedback (doc 14).
9. M2: spike pywlroots+moderngl EGL sharing; pre-M2 wlr-screencopy
   mirroring milestone (D).
10. Session restore of open panels/layouts (B; visionOS lesson in 14).
