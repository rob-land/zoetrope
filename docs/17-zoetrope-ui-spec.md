# 17 — Zoetrope UI specification (glasses interface)

*Drafted 2026-07-28. The concrete design for the XREAL shell, applying
[14](14-ui-research-nebula-quest-visionos.md) /
[15](15-ui-research-round2.md) research under the
[16](16-suite-design-language.md) suite language. Numbers are normative
unless marked (tune). Ends with the Mirage Solo contingency addendum.*

## 0. Units and the world

- All UI is specified in **dmm** (1 mm at 1 m ≈ 0.057°). The renderer
  keeps `width_m = dmm × distance_m / 1000`.
- The stage is a **cylinder centered on the user**, default radius
  **1.7 m** (≈ the optics' focal plane; sustained content never nearer
  than 1.0 m, nothing ever nearer 0.5 m).
- **Comfort cone**: primary content within ±20° yaw of forward, panel
  centers ≈ **5° below eye level**; nothing interactive above +10°
  pitch. Ambient chrome lives at the *bottom* edge (Go dock pattern) —
  the clock moves down from its current above-arc position.
- **Neck model**: synthesize a small positional offset from head
  rotation (pivot ~120 mm behind, ~75 mm below eye center, standard
  Daydream constants) so panels parallax believably at 3DoF.

## 1. Scene architecture

Three layers (docs/12, unchanged) with one addition — a system overlay:

```
Layer 3  OVERLAY   control center + notifications; summoned, never reflows panels
Layer 2  AMBIENT   clock/battery/now-playing strip at bottom edge; head-locked-lite
Layer 1  PANELS    launcher rails, app panels, theater screen — on the cylinder
Layer 0  ANCHOR    floor grid / recenter reference / (VR: environment)
```

- Layer 2 is the only head-locked content and stays tiny + peripheral
  (≤3° tall, bottom 15° of view, auto-hides in theater).
- Layer 3 (new): summoned by `back`-long-press / look-down-then-activate
  / two-finger-swipe-down on the remote. Contents: now-playing +
  transport, volume/brightness, follow-mode toggle, layout presets,
  profile chip, recenter, quit. Dimming behind it, never an opaque
  backdrop.

## 2. Home: from tile arc to leanback rails

Replace the single arc of app tiles with **stacked rails on the
cylinder** (the arc becomes rows — same CylinderLayout math, a second
vertical slot):

```
        [ Resume rail ]      ← CONTINUE/NEXT/WATCHLIST/NEW (ripsaw library,
                               later couch's aggregator)
        [ Apps rail ]        ← 3D Movies · 3D Gallery · Terminal · (hosted
                               apps post-M2)
  ....... ambient strip ..............................................
```

- Rails scroll horizontally (`prev/next`); `up/down` moves between
  rails. Focus memory per rail. Back always retreats: page → home →
  (nothing; back on home summons overlay instead of quitting).
- **Gaze gravity**: head-gaze snaps focus to the nearest card in the
  gaze direction (never a free cursor over the launcher). Keyboard/
  remote and gaze co-exist via the existing gaze-lock rule.
- Cards: poster **2:3** for movies (≈ 300×450 dmm), **16:9** for apps/
  episodes (≈ 480×270 dmm), gap 20 dmm, next card peeking ~25%.
  Focused card: 1.06× scale + accent ring + parallax tilt (±2.5°,
  driven by sub-threshold head motion, tvOS-style) + title reveal.
- Movie rail shows 5 cards in the comfort cone; "view all" opens the
  full grid page (3 rows, denser).
- Selection-to-playback ≤ 2 activations: Resume rail plays directly;
  Movies rail opens the title's card → play.

## 3. Focus, reticle, and input

- **Targets ≥ 80×80 dmm** with 16 dmm padding (head-gaze floor; the
  research's 64 dmm is for laser pointers). In-panel sub-controls
  (transport buttons) follow the same floor.
- **Reticle**: only visible in pointer contexts (panel interaction,
  post-M2 hosted apps); rendered **at the depth of the hovered
  surface**; swells from 6 → 10 dmm over targets; hidden during
  playback and while a scroll fling is in flight; **act on release**.
- Verb grammar (extends docs/12): `activate` on release; long-`activate`
  = context menu (radial, Daydream-Elements style, ≤5 slots);
  long-`back` = overlay; hold-`recenter` = world recenter, tap =
  pointer recenter (two flavors, Nebula lesson).
- **Dwell** (no-hands fallback): 800 ms (tune) with radial progress fill
  around the focused element + a persistent 2-item **verb palette**
  (Select / Scroll) parked at the bottom edge, visionOS Dwell pattern.
- Phone remote: explicit **Trackpad ↔ Laser** mode toggle; 1-finger =
  cursor/focus nudge, 2-finger vertical = scroll, 2-finger tap = back,
  long-press = overlay, haptic tick on focus change (Vibration API).
  Add gyro streaming for Laser mode (phone IMU → yaw/pitch ray).

## 4. Visual design: Adwaita-through-glass

- **Palette** (additive display: black = transparent, so darkness is
  literal transparency):
  - Panel surface: white @ 12% + 1.5 dmm white @ 35% border (glassy
    stroke), radius 12 dmm. Focused: border → Adwaita blue accent.
  - Text: white; secondary white @ 70%; never below 55%.
  - Accent: `#3584e4` (focus ring, progress, selection) — bright enough
    to survive additive blending; avoid saturated reds/darks for chrome.
  - Scrims behind text-over-art: black gradient (i.e., transparency
    gradient) + slight art dim, not opaque boxes.
- **Type**: Cantarell/Inter, Medium+ weight in-lens. Body 24 dmm floor,
  captions 20 dmm (only for card subtitles), titles 36 dmm, page display
  48 dmm.
- Iconography: GNOME-symbolic-style strokes at ≥ 3 dmm stroke width.
- **No opaque dark panels anywhere** — dimming the world (theater) is
  done by *not drawing*, plus electrochromic dimming when the hardware
  control lands.

## 5. Theater mode (the movie experience)

Recipe (research-normative):
- Screen defaults to **~60° wide** (≈ 2.0 m wide at 1.85 m) — Carmack's
  number, deliberately not IMAX; user size presets: **Cinema 60° ·
  Large 75° · Max 85°** and distance presets near/mid/far (seat model).
  16:9 flat; curve toggle later (tune).
- Everything else fades out (panels hide, ambient strip auto-hides
  after 3 s). **Void toggle**: pure black surround (default) vs
  "room" (faint floor grid + panel ghosts at 5%).
- **Stereo content**: feathered frame — a 20 dmm soft alpha falloff on
  the screen edges (hides stereo-window violations; visionOS lesson).
- Transport = an **ornament** floating 40 dmm below the screen's bottom
  edge, slightly forward: play/pause, seek bar with thumbnail-free
  scrub, time, audio/subs, size/seat, exit. Auto-hides after 2.5 s;
  any input summons it. Never drawn over the picture.
- Subtitles render in the ornament plane (below frame) by default —
  cheaper than in-frame recomposition and avoids depth conflict with
  stereo content (subtitle-depth is a known 3D-BD pain; revisit with
  depth-aware placement later).
- Entry is always explicit (never auto-immersive); exit = back.

## 6. Layout presets & follow modes

- **Presets** (overlay-selectable, persisted per "space"): `Home`
  (rails), `Theater`, `Panel` (single app panel 1024×640 dmm-equiv),
  `Triptych` (3 hinged panels, post-M2), `Reading` (tall narrow panel,
  post-M2). No freeform placement; panels snap to arc slots.
- **Follow triad per-layout** (not per-panel): Anchor (default) ·
  Smooth Follow (deadzone ±8°, damped ~0.5 s glide; for transit) ·
  Sideview (54″-equivalent panel parked top-corner, head-locked-lite;
  for walking — glance only). Pitch handling: beyond ±50° pitch the
  layout blends to head-aligned over ~20° (avoids the look-straight-up
  flip; see the Snap patent prior-art note in 15§A — flag before
  productizing).
- On-chip glasses modes remain the *stability* path once the USB
  control protocol is cracked; host-side follow is for the surround
  layer only.

## 7. Sessions, persistence, Exposé

- **Session restore is day one**: open panels, layout preset, per-rail
  focus, playback position all persist across restarts (visionOS-1
  lesson). Stored per profile per "space" (a named layout: Desk, Sofa,
  Transit).
- **Exposé**: hold-`up` (or overlay button) gathers all panels into the
  comfort cone as a temporary rail; gaze-pick one; others return. This
  is our cheap win over visionOS's lost-windows problem.
- Notifications: toast at the bottom-edge strip only, 20 dmm tall,
  fade-in/out, with global DND in the overlay. Never at panel depth.

## 8. Apps in this design

- **Movies**: §2 rails + §5 theater; probe/stream via stereoscope
  (unchanged engine seam).
- **Gallery**: same card grammar; photo fills ~50° with feathered edges
  (stereo photos benefit like video); prev/next flips; slideshow =
  ambient-compatible (slow fade).
- **Terminal**: Panel preset; Reading mode later.
- **Post-M2 hosted apps**: appear as cards on the Apps rail; open into
  Panel/Triptych presets; shell draws focus ring + window pill (title,
  close, move-to-slot) 20 dmm above the panel — chrome outside content
  (visionOS/Android XR convention).

## 8a. The Movies app at library scale (designed 2026-07-29)

The current pages are walking-skeleton wiring (home rail of 8, an
"All Movies" page capped at 24 on one rail). The arithmetic that kills
linear browsing: ~14°/poster × ±40° comfort cone = 5–6 visible cards,
so a 300-title rail is ~50 window-steps. The scalable structure:

**Home never shows the library.** Home's media band is the **resume
rail** (Watch Next semantics — CONTINUE/NEXT/WATCHLIST/NEW, already
implemented in `suite_providers`' Jellyfin backend) plus optionally
"Recently added". Most sessions are "keep watching"; library size is
irrelevant on home.

**Opening Movies → a browse page of stacked rails** (the leanback
grammar the rails machinery already renders; shared with couch):

1. **Rail group per backend library** when several exist — Jellyfin
   "views" / Plex sections (Movies, Kids, Anime, …). Kid-mode profiles
   filter which libraries exist at all (provider obligation).
2. Within a library: **genre rails** (Jellyfin serves genres and
   filters server-side — one query per rail, fetched lazily as the
   gaze approaches), plus **Recently Added** and **Unwatched**.
   ~15 genre rails × ~20 titles turns 50 steps into "look down three
   rails, step twice."
3. **A-Z scrub rail**: a compact rail of letter tiles; activating a
   letter jumps the adjacent movie rail's window to that initial (the
   Kodi/Plex TV pattern; degrades perfectly to gaze+buttons since the
   alphabet is just another rail). Cheaper sibling shipped first:
   **long-press prev/next jumps by initial letter** (Android TV
   fast-scroll convention).
4. The dense **grid stays as "view all"** — wrong for primary browsing
   (research), fine for deliberate view-everything; row/col navigation
   already handles 2D.

**Search tiering** (glasses can't type): scoped browsing above beats
search below ~1k titles; the phone web-remote's keyboard covers rare
lookups today; voice is the eventual answer.

**Stereo at scale**: rails badge 3D titles from the provider's
`StereoHint`; a "3D" rail (server-filterable on Jellyfin via
`/Items?is3D=true`) sits with the genre rails. `NAME`-confidence hints
upgrade to `PROBED` lazily via the probe cache after first play.

**Paradigm note**: this structure is independent of the open
home-paradigm question (icon launcher vs media rails — see
[[feedback-zoetrope-ui-paradigm]]): if home becomes an icon launcher,
Movies is an icon and everything above is what the app opens into; the
media grammar lives inside the app, and non-media apps (terminal) stop
living in a media paradigm.

## 8b. What is spatial-native vs 2D grammar (the element split)

The stage is spatial; the content grammar is 2D everywhere. This is the
formal boundary that keeps zoetrope cohesive with couch/hearth:

**Spatial-native (exists only in XR; owned by the shell):** the
cylinder/layer stage; world-anchoring, layout presets, follow modes,
recenter; compositor-drawn focus ring and reticle-at-depth; gaze
gravity; the theater screen with feathered stereo edges; Exposé; the
head-locked-lite ambient strip; floating ornaments and window pills
(chrome outside content); environment/void; spatial audio cues; dwell +
verb palette.

**2D grammar (identical inside a zoetrope panel and on a couch/hearth
screen):** rails, card lockups, the resume row, overlay-control-center
anatomy, transport controls, settings/preferences pages, text,
keyboards, setup flows. A zoetrope panel should render *the same rails
couch renders* — same tokens, same focus behavior — placed on the stage
by the spatial layer. Never fake 3D inside panel content (no depth on
text, no extruded UI); depth expresses hierarchy *between* surfaces
only.

**Doesn't survive the trip to spatial:** hover-dependent UI, dense grids
as primary browsing, scrollbars (flings + focus memory instead), modal
chains, tiny toolbars. **Transfers both ways:** parallax tilt on the
focused card (thumb micro-motion on tvOS ≡ sub-threshold head motion
here).

## 9. Implementation order (maps to current code)

1. Palette/type/focus pass in `apps/base.py` + `shell.py` (tokens from
   doc 16). Move clock to bottom strip. *(small)*
2. Rails: extend CylinderLayout with vertical slots; gaze gravity;
   card lockups with poster art (movie picker becomes Resume+Movies
   rails). *(medium)*
3. Theater mode on MovieApp: size/seat presets, ornament transport,
   feathered stereo edges, void toggle. *(medium)*
4. Overlay control center + session restore + Exposé. *(medium)*
5. Neck model + reticle depth + dwell verb palette. *(small each)*
6. Follow triad host-side (deadzone/damping); pitch blend. *(medium)*
7. Phone remote: mode toggle, gyro laser, haptics. *(small)*

## Addendum: Lenovo Mirage Solo contingency

Status check (mirage/RESEARCH.md): the Solo has **never been rooted; no
custom ROM or mainline Linux exists; bootloader unlock unconfirmed** —
so this is a contingency spec, not a plan. If a pmOS port ever lands,
zoetrope's deltas are:

1. **Rendering**: the Solo is a lensed VR headset (single 2560×1440 LCD,
   1280×1440/eye) — zoetrope must add a **barrel-distortion pass**
   (per-eye distortion mesh + asymmetric projection) instead of the
   glasses' plain FSBS framebuffer. One extra render-to-texture +
   distortion-mesh draw in `renderer.py`; stereo math already per-eye.
2. **Opaque world**: VR, not AR — the Adwaita-through-glass palette
   inverts back toward standard dark Adwaita surfaces, and Layer 0
   grows a real environment (void + faint grid default; the theater
   Void toggle becomes the norm).
3. **Tracking**: WorldSense 6DoF if drivers ever exist; otherwise its
   IMU is plain 3DoF — either way the shell runs (6DoF just feeds the
   neck model with real translation). The **Daydream controller support
   we already ship** becomes the primary pointer (real laser, 64 dmm
   targets apply).
4. **Perf**: SD835 + Adreno 540 on freedreno — moderngl scene is light;
   video decode is the risk (no guaranteed V4L2 decoder early); target
   2D/FSBS H.264 first.
5. Everything else — rails, theater, overlay, tokens, input vocabulary —
   transfers unchanged. The spec was written distance-relative and
   input-agnostic for exactly this reason.
