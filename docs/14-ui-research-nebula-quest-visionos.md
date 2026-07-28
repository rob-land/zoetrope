# 14 — UI research: Nebula, Horizon OS, visionOS → what zoetrope should steal

*Survey landed 2026-07-27. Companion to [12](12-interaction-design.md) (interaction
design — this doc refines it) and [13](13-app-catalog-and-roadmap.md) (roadmap —
this doc feeds its milestones). Full source list at the bottom; inline links
throughout.*

Three shipping spatial UIs were surveyed: XREAL's own Nebula/nebulaOS (our
hardware, so its choices are ground truth for what works on birdbath 3DoF
glasses), Meta's Horizon OS (a decade of iteration + published design metrics),
and Apple's visionOS (the best-documented design language, plus — crucially —
Apple's *accessibility* input paths, which are exactly our input model).

## TL;DR — ranked adoption list

1. **Angular units everywhere ("pt-as-angle").** visionOS defines a point as an
   angle so windows keep constant angular size at any distance. On 3DoF
   *everything already lives on a sphere* — adopt degrees (or a shell-pt) as the
   one sizing unit for tiles, panels, text, and hit targets, replacing our ad-hoc
   `width_m` at fixed distance.
2. **Target sizes are known numbers — use them.** visionOS: 60 pt minimum hit
   area (~1.5° at its scale), centers ≥60 pt apart; Meta: 32 dp visual / 48 dp
   hit; Daydream (the only pure-ray-pointer numbers ever published): 64 dmm hit,
   16 dmm padding, ~24 dmm body text. Head-gaze is *coarser* than eye-gaze, so
   treat these as floors. Our ~20°-apart tiles are safely above; per-tile
   sub-controls (task 13's media buttons) must obey them.
3. **Spawn-then-anchor, never head-lock; recenter is sacred.** All three
   platforms converge on this. Panels spawn head-relative, then world-anchor;
   rigid head-lock is reserved for tiny ambient chrome (visionOS bans it
   outright, Meta "avoid"). Every platform gives recenter one dedicated
   physical action (Digital Crown press / Meta-button long-press / Beam mode
   button long-press). We have `R`/hold — keep it one action away from every
   state, and add Nebula's second flavor: **pointer/reticle recenter** distinct
   from world recenter.
4. **System UI is an overlay layer, not a peer window.** Meta paid ~18 months of
   UI churn (Universal Menu → Navigator → revert → Navigator again) learning
   that Settings/launcher opening *as a window* that reflows your panels reads
   as broken. Our launcher/app split already respects this; keep quick-settings,
   notifications, and the coming glasses-control UI in a summoned overlay that
   never rearranges panels. And **dim, don't paint**: on an additive display an
   occluding backdrop is doubly wrong (Meta had to strip Navigator's grey oval).
5. **Theater mode is a recipe, not a feature flag:** enlarge toward an oversized
   virtual screen + dim everything else + optional curve + seat/distance
   presets. visionOS adds the killer detail for stereo content: **feathered
   window edges** hide stereo-window violations at the frame — directly
   applicable to our MVC/MV-HEVC playback panels. Never auto-enter immersive
   playback; transport controls live on an ornament *below* the frame,
   auto-hiding, never burned into the content.
6. **Discrete beats freeform without hands.** Meta shipped discrete
   small/medium/large/jumbo panel sizes *before* pinch-resize; Nebula sizes
   screens in stepped inches; our prev/next resize steps are already right.
   Same for placement: **snap-to-arc slots** beat free placement — reviewers
   count visionOS's no-snap free placement as a net negative. Our
   CylinderLayout slots are the right architecture; formalize them
   (3-slot "hinged triptych at ~1 m/slightly below eye line" is Meta's
   default working set and maps 1:1 to 3DoF).
7. **Ship the Exposé visionOS lacks.** "Windows get lost" is the #1 visionOS
   complaint and Meta's window-anchoring arrived only in v81. On a 3DoF sphere
   an overview is trivial: gather all panels into the comfort cone, gaze-pick
   one. Pair it with **layout persistence** (per-"space" profiles) — visionOS 1
   forgot layouts on reboot and it defined the product's first-year reputation.
8. **Dwell needs a verb palette.** Apple's Dwell Control (their no-hands path)
   pairs dwell with a tiny palette choosing what the dwell *does* (tap / scroll
   / long-press / drag). Our planned dwell-as-last-resort should copy this
   instead of inventing a one-verb dwell.
9. **Comfort numbers to encode as defaults:** sustained content ≥1 m (we park at
   1.7 m — good, matches the glasses' focal plane; don't fake nearer depth);
   important UI inside a ~60° cone, centered slightly *below* line of sight
   (up/diagonal gaze travel is fatiguing — our clock floating *above* the arc
   violates this; move ambient chrome down or to the sides); no motion in the
   periphery; relocate objects by fade-out/fade-in, not by animating them across
   space; keep the horizon level (Nebula ships "screen leveling" for a reason).
10. **Adaptive translucency, not dark mode.** visionOS has no dark mode — glass
    material + 3 vibrancy levels adapt to whatever's behind. For additive
    optics (background = the real world, always) this is the correct model:
    translucent panels, white text, weight bolder than desktop defaults
    (both Apple and Meta note in-lens rendering eats thin strokes).

## Per-platform notes worth keeping

### Nebula / nebulaOS (XREAL) — ground truth for our hardware

- **The mode set is the product**: Body/Spatial Anchor, Smooth Follow (damped
  lazy-follow, pitched for vehicles), Sideview (small corner panel, 54–85" on
  One-series, keeps central vision clear), Fixed quadrant placement. Our
  docs/12 mode table already mirrors this — this survey confirms it's the
  right parity set and adds the *use-case framing*: Anchor when stationary,
  Smooth Follow in transit, Sideview while walking/doing chores.
- **Comfort default is a big far screen**: 147"/171" at 4 m (adjustable 1–10 m).
  Rationale: far placement minimizes vergence strain on a fixed-focus display.
  Our movie "theater" should default far-and-huge, not near-and-monitor-like.
- **FOV correction for our configs**: One Pro is marketed **57°** (One: 50°;
  the ~46° figure floating in our comments is the Air 2). Caveat before
  touching `config.py` (currently `fov_h_deg=48`): vendor FOV numbers are
  usually *diagonal*; 57° diagonal on 16:9 ≈ **49.7° horizontal**, so 48 may
  already be about right. Verify optically (render a calibrated grid, measure
  where it clips) before changing layout math.
- **Strategic validation**: XREAL deprecated Nebula-for-Android entirely —
  phone-side 3DoF reprojection over USB-C never got stable (drifting anchors,
  smeared Smooth Follow, stuck pointer). One-series does anchor/follow/sideview
  **on the X1 chip in-glasses**. Consequence for us: let the glasses do
  stabilization; the host shell treats the display as dumb pixels (exactly our
  current kiosk model), and host-side follow modes are *additions* for the
  surround layer, not the core stability path. The USB control protocol for
  switching on-chip modes is the same backlog item as the 3D-mode switch
  (docs/13 backlog 3).
- **Phone-as-controller works**: IMU laser-pointer + screen-as-touchpad + a
  dedicated *pointer recenter* button (praised as "lost cursor" recovery), and
  haptic feedback on virtual-keyboard taps was singled out as delightful —
  our web-remote can vibrate via the Vibration API for the same effect.
  Anti-pattern observed: keyboard sometimes in-glasses, sometimes on-phone —
  pick one place per posture and never surprise.

### Horizon OS (Meta Quest) — the iteration record

- **One input contract**: the entire panel/system layer compiles every input
  (controller ray, hand pinch, eye+pinch) down to **ray + select + scroll**.
  Hands are deliberately "like a Touch controller" via a stabilized wrist
  PointerPose — pointing comes from a *stable* pose, not the noisiest joint.
  Our `prev/next/up/down/activate/back/recenter` vocabulary is the same idea;
  the refinement to adopt: model head-gaze as a *ray* so panels and in-panel
  content share one hit-testing path, and low-pass the ray like Meta stabilizes
  PointerPose.
- **Layout numbers**: default panel 1024×640 dp (min 384×500, max 1440×1000);
  ray-driven UI at ~1 m, "slightly below the line of sight"; direct-touch at
  45 cm is a tier we simply don't have — everything in zoetrope belongs in the
  ≥1 m indirect tier.
- **The triptych won**: 3 hinged panels moved as a unit beat freeform for
  mainstream users for years; 6-window freeform stayed opt-in. v83's
  double-press-to-hide-all-windows is a great chord for our keyboard/remote
  (peek at the real world instantly — on AR glasses even more valuable).
- **Media plumbing**: 3D convention is plain SBS/TB frame-packing (our FSBS
  output is already the industry's least-common-denominator); transport
  controls below the viewport on their own dimmed auto-hiding layer; theater =
  enlarge + dim + user-set curve. Horizon TV shows cinema as a *destination*
  (environment + hub), distinct from the panel system.
- **Churn warnings**: freeze the muscle-memory surface (summon action, dock
  position) even while internals evolve; never ship a half-migrated shell
  (Navigator still opening legacy windows read as broken); notifications need
  a dedicated depth + edge slot + a global DND, or users disable them; a feed
  on the launcher was so disliked Meta deleted it — launcher = launcher.

### visionOS (Apple Vision Pro) — the design language + our input model, shipped

- **Apple already ships our input model as accessibility**: Pointer Control
  with a **Head** cursor source (a visible cursor at the head-ray intersection
  — first-party head-gaze-plus-click), Dwell Control with its verb palette,
  full BT keyboard/trackpad/gamepad support. We're not building a degraded
  visionOS; we're building its (well-designed) indirect path as the primary.
- **Compositor-owned focus**: apps never see gaze; the *system* renders hover
  highlight and delivers only activations. Keep focus rendering in the shell
  (as today) — apps/panels receive events, never the gaze stream.
- **Window grammar**: new windows 1280×720 pt at ~2 m dead ahead; window bar +
  close orb *below* the window (chrome outside the content rect — content
  never pays pixels for controls); ornaments float slightly in front, overlap
  the bottom edge by 20 pt; dragged windows stay perpendicular to the viewer
  (free on our sphere). Depth = hierarchy, sparingly: modals forward, source
  dims back.
- **Hover-delay taxonomy** (none / short / long for affordances / tab-expansion
  / tooltips) is directly reusable as our dwell-timing taxonomy.
- **Home View details**: offset 4-5-4 honeycomb, icons with 2.5D parallax pop
  on focus, Environments that scale-up-then-open on sustained gaze
  (intent-confirming hover — a dwell-native pattern). v1's alphabetical-only
  grid was hated: user-arrangeable order matters even on a tile arc.
- **Cinema**: seat presets (row/position), screens "beyond the dimensions of
  the room," auto-dim as content approaches, spatial video as a
  feathered-edge "window into a memory." The feathered stereo window is the
  single best trick here for us.

## What this means for the two hosts

**Laptop (today's kiosk + supplementary mode).** The layer model in docs/12
survives contact with all three platforms intact; what's new is mostly policy:
triptych slots at ~1 m equivalent / slightly below eye line, overlay-only system
UI, Exposé + per-space layout persistence, theater recipe for stereoscope
content, hide-all-panels chord, ambient chrome moved out of the "up" zone.

**Fairphone 5 (mobile Linux) — newly credible.** Unlike the Beam Pro (docs/05:
SM6450 not upstreamed, camera stack welded to Android), the FP5 is a
first-class mainline citizen: QCM6490 is well-upstreamed, postmarketOS supports
the device, and **DP-alt-mode-out has been demoed on mainline with Fairphone's
own kernel dev upstreaming the patch series** (v2, March 2025 — track
`pmic_glink` DP support). The FP5 + One Pro is therefore the reference mobile
target: same Wayland/GL stack as the laptop, Adreno 643 via freedreno, phone
screen as the touchpad/OSK exactly as Nebula's Beam did (our web-remote
already speaks this; a native surface later). Nebula's deprecation story is
the cautionary tale for this posture: keep the phone-side shell *thin* (dumb
FSBS framebuffer out, on-chip stabilization in-glasses), or we inherit the
drift/smear/latency complaints that killed Nebula-on-phones. Power budget on
a phone SoC reinforces the same rule — no host-side per-frame reprojection.

Input matrix addition for FP5 posture (extends docs/12): phone flat in hand =
touchpad (tap/drag/two-finger-back); phone raised = IMU laser pointer (the
"phone-as-6DoF-wand" open question in docs/12 is answered — Nebula shipped it
and it worked; add gyro streaming to the web-remote); pocket = head-gaze +
dwell with the verb palette.

## Pitfalls registry (what not to build)

- Head-locked panels (everything except tiny ambient chrome).
- System surfaces as peer windows that reflow the working set.
- Opaque occluding overlays on an additive display — dim instead.
- Free window placement without snap slots; freeform resize before we have a
  precise pointer.
- One-verb dwell (dwell without a verb palette).
- Host-side reprojection/stabilization as the *primary* stability path.
- Auto-entering immersive/theater playback.
- Notification toasts at arbitrary depth/position without DND.
- A feed, store, or social surface on the launcher.
- Alphabetical-only, non-arrangeable launcher once tile count grows.
- Relying on vendor FOV numbers for layout math without optical verification.
- Forgetting layouts across restarts (persistence is a day-one feature, not
  polish).

## Sources

Nebula/XREAL: [tutorials.xreal.com display adjustment](https://tutorials.xreal.com/docs/glasses/one-series/osd/dispaly-adjust/) ·
[Side View](https://tutorials.xreal.com/docs/glasses/one-series/osd/side-view/) ·
[Screen Leveling](https://tutorials.xreal.com/docs/glasses/one-series/osd/screen-leveling/) ·
[developer.xreal.com (Nebula deprecation)](https://developer.xreal.com/download/) ·
[Android Police Beam Pro review](https://www.androidpolice.com/xreal-beam-pro-review/) ·
[Windows Central Beam Pro review](https://www.windowscentral.com/accessories/xreal-beam-pro-review) ·
[Tom's Guide Beam Pro review](https://www.tomsguide.com/computing/vr-ar/xreal-beam-pro-review) ·
[Android Central nebulaOS 2.0](https://www.androidcentral.com/gaming/virtual-reality/xreals-nebulaos-2-0-update-for-the-beam-pro-is-crucial-this-is-what-the-huge-patch-brings) ·
[GSMArena Air+Beam review](https://www.gsmarena.com/xreal_air_ar_glasses_and_xreal_beam_review-news-59478.php) ·
[GSMArena Nebula for Mac](https://www.gsmarena.com/xreal_updates_its_nebula_for_mac_app_with_virtual_display_and_virtual_cinema_support-news-59096.php) ·
[Digital Trends Air+Beam](https://www.digitaltrends.com/phones/xreal-air-with-beam-review/) ·
[Tom's Hardware One Pro review](https://www.tomshardware.com/peripherals/wearable-tech/xreal-one-pro-review) ·
[XREAL forum: stuck pointer](https://community.xreal.com/t/laser-pointer-in-nebula-android-is-kind-of-stuck/5186)

Horizon OS/Meta: [Panels](https://developers.meta.com/horizon/design/panels/) ·
[Layouts](https://developers.meta.com/horizon/design/styles_layouts/) ·
[MR design guidelines](https://developers.meta.com/horizon/design/mr-design-guideline/) ·
[Hands](https://developers.meta.com/horizon/design/hands/) ·
[Controllers](https://developers.meta.com/horizon/design/controllers/) ·
[Accessibility](https://developers.meta.com/horizon/design/accessibility/) ·
[Typography](https://developers.meta.com/horizon/design/styles_typography/) ·
[Comfort](https://developers.meta.com/horizon/design/comfort/) ·
[v67 update blog](https://www.meta.com/blog/meta-quest-v67-update-new-window-layout-creator-content-horizon-feed/) ·
[Help: moving/adjusting windows](https://www.meta.com/help/quest/542427545314119/) ·
[UploadVR: Navigator rollout](https://www.uploadvr.com/meta-horizon-os-navigator-ui-finally-rolled-out-to-all-quest-headsets/) ·
[UploadVR: v83 PTC](https://www.uploadvr.com/quest-v83-ptc-evolved-navgiator-horizon-os-ui/) ·
[UploadVR: v81 anchoring](https://www.uploadvr.com/quest-v81-new-immersive-home-window-anchoring-quickplay/) ·
[Immersive media formats](https://creator.oculus.com/getting-started/immersive-media-formats/) ·
[Daydream design requirements (dmm targets)](https://developers.google.com/vr/distribute/daydream/design-requirements)

visionOS/Apple: [Designing for visionOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-visionos) ·
[Eyes](https://developer.apple.com/design/human-interface-guidelines/eyes) ·
[Gestures](https://developer.apple.com/design/human-interface-guidelines/gestures) ·
[Windows](https://developer.apple.com/design/human-interface-guidelines/windows) ·
[Spatial layout](https://developer.apple.com/design/human-interface-guidelines/spatial-layout) ·
[Materials](https://developer.apple.com/design/human-interface-guidelines/materials) ·
[Typography](https://developer.apple.com/design/human-interface-guidelines/typography) ·
[Ornaments](https://developer.apple.com/design/human-interface-guidelines/ornaments) ·
[Motion](https://developer.apple.com/design/human-interface-guidelines/motion) ·
[Playing video](https://developer.apple.com/design/human-interface-guidelines/playing-video) ·
[Immersive experiences](https://developer.apple.com/design/human-interface-guidelines/immersive-experiences) ·
[Support: Dwell Control](https://support.apple.com/guide/apple-vision-pro/perform-actions-with-your-eyes-tan0ba69a1f1/visionos) ·
[Support: Pointer Control](https://support.apple.com/guide/apple-vision-pro/pointer-control-tan3869c8a85/visionos) ·
[Support: Home View](https://support.apple.com/guide/apple-vision-pro/use-home-view-devf42afa74a/visionos) ·
[Apple newsroom: entertainment](https://www.apple.com/newsroom/2024/01/apple-previews-new-entertainment-experiences-launching-with-apple-vision-pro/) ·
[Varrall: windowing teardown](https://varrall.substack.com/p/windowing-on-the-vision-pro) ·
[AppleInsider one-year review](https://appleinsider.com/articles/25/01/29/apple-vision-pro-review-one-year-later-time-to-exit-the-preview) ·
[MacStories visionOS 2](https://www.macstories.net/news/visionos-2-the-macstories-overview/)

Fairphone 5: [FP5 DP-out patch series v2 (patchew)](https://patchew.org/linux/20250312-fp5-pmic-glink-dp-v2-0-a55927749d77@fairphone.com/) ·
[mainline DP demo (Fosstodon)](https://fosstodon.org/@z3ntu/111132695265417281) ·
[Fairphone forum: video out](https://forum.fairphone.com/t/does-the-fairphone-5-support-video-output-over-usb-c/99493)
