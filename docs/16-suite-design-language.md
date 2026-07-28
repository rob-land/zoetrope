# 16 — Suite design language: zoetrope · couch · hearth

*Drafted 2026-07-28. The overarching UI design that makes the three shells
read as one family. Canonical copy lives here (the design-research home);
couch and hearth should reference or vendor it. Builds on the research in
[14](14-ui-research-nebula-quest-visionos.md) and
[15](15-ui-research-round2.md).*

## The family

| Shell | Host | Stack | Viewing distance | Input class |
|---|---|---|---|---|
| **zoetrope** | XREAL glasses (laptop / Linux phone) | Python + moderngl | virtual ~1.7 m | head-gaze + buttons/remote |
| **couch** | TV box (N100 mini-PC) | GTK4 + libadwaita | ~3 m ("10-foot") | remote/D-pad |
| **hearth** | Pi 5 smart display | Vue 3 kiosk | 0.5–3 m, touch + glance | touch + voice-ish + glance |

One user, three distances, one design language. The unifying insight from
the research: **all three are focus-first, content-first shells** — a TV
remote, a head-gaze ray, and a glanceable touch panel are the same design
problem at different angular resolutions. The design system is therefore
specified in **angular terms** and rendered per-shell.

## Principle stack (ordered; earlier wins conflicts)

1. **Adwaita is the mother tongue.** Where a shell can literally use
   GTK4/libadwaita (couch), it does, unmodified. Where it can't, it speaks
   Adwaita with an accent: hearth mirrors Adwaita tokens in CSS custom
   properties; zoetrope adapts them for additive optics (below). Nobody
   invents a third-party visual language.
2. **Focus is the interface.** Exactly one unmistakably focused element at
   all times on remote/gaze shells; focus = scale (1.05–1.1×) + accent
   ring + optional parallax tilt; animated <150 ms; input acknowledged
   <50 ms even if content is still loading (skeletons).
3. **Content-first, chrome-collapsing.** Full-bleed artwork is the UI.
   Chrome (nav, status) collapses when idle, returns on input or focus
   approach. Launcher = launcher: no feeds, no ads, no news.
4. **Overlay, don't navigate.** Transport controls, quick settings, and
   profile switching are transient overlays above live content (PS5
   Control Center / Meta Navigator lesson), never a page navigation away
   from what's playing. System overlays never reflow the working set.
5. **Density is a feature.** Rails show 5–7 posters, next card peeking;
   clicks/selections-to-playback ≤ 2 from the home surface (Switch
   lesson; Netflix-2025 anti-lesson).
6. **Ambient is a first-class state.** Every shell has Active → Ambient →
   Dimmed states (hearth: the whole point; couch: after ~10 min idle;
   zoetrope: the AMBIENT layer). Return from ambient resumes exactly
   where the user left off. No static chrome while ambient (burn-in +
   OLED discipline).
7. **Profiles gate everything, including ambient.** Kid-mode filtering
   applies to artwork rotations and rails, not just playback (couch
   already models this; zoetrope/hearth adopt).

## Shared design tokens

Specified abstractly; each shell maps to its native units. Reference
implementations: couch uses Adwaita defaults + a `tv.css` layer; hearth
mirrors in `:root` CSS vars; zoetrope maps to dmm at the 1.7 m arc.

**Color.** GNOME palette, Adwaita semantic roles:
- Accent: Adwaita blue (`#3584e4`) for focus rings, selection, progress.
- Surfaces: Adwaita dark surfaces on couch/hearth (media shells default
  dark: `#1d1d20`-family); zoetrope substitutes translucency for
  darkness (below).
- Success/warning/error: Adwaita green/orange/red, used sparingly.
- Artwork saturation is the color of the UI; chrome stays neutral/muted
  (TVs oversaturate; AR optics bloom — same rule).

**Type.** One ramp, angular floor of ~0.55°/cap-height for body:
- Family: **Inter or Cantarell** (Adwaita's face) everywhere; hearth may
  fall back to system-ui. No weights below Regular on TV/glasses; prefer
  Medium+ in-lens (thin strokes die on both).
- Roles (angular → per-shell): Display (page titles) ≈ 2× body ·
  Title ≈ 1.5× · Body · Caption ≈ 0.85×. Concretely: couch ≥29 pt body /
  ≥48 pt titles @1080p; zoetrope ≥24 dmm body (≥1.5° subtense);
  hearth ≥ 18 px at arm's length, doubled in far/ambient density.

**Focus ring.** 3-px-equivalent accent ring + 1.05× scale + soft shadow;
radius follows Adwaita (12 px-equivalent on cards); on zoetrope the ring
is drawn by the shell (compositor-owned focus — apps never render their
own), plus gentle parallax tilt from sub-threshold pointer/head motion.

**Cards & lockups.** Poster 2:3, episode/video 16:9, person/logo 1:1.
Image + label are one focusable unit; text below art, scrim over art when
overlaid; 20 dp-equivalent gaps; skeleton shimmer while loading.

**The resume row.** First rail everywhere, Android TV Watch Next
semantics: CONTINUE (with progress bar) / NEXT / WATCHLIST / NEW, ordered
by recency. couch aggregates it across sources; zoetrope surfaces the
same row from the ripsaw library (and later from couch's aggregator —
see "Shared services" below).

**Iconography.** GNOME symbolic icons (single-color, stroke-based) tinted
to the text color. zoetrope already draws vector glyphs; align them to
symbolic style.

**Motion.** 150–250 ms ease-out for focus/navigation; nothing autoplays
with sound on dwell; ambient transitions are slow fades (≥500 ms);
zoetrope adds: relocate panels by fade-out/fade-in, never fly them
across the sphere; no motion in the periphery.

**Sound.** Subtle click/confirm ticks (Switch-style) on couch/zoetrope;
hearth silent by default (shared-space device).

## Where libadwaita applies, per shell

- **couch** — native. AdwNavigationSplitView/AdwCarousel etc. where they
  fit, but 10-foot pages prefer full-bleed custom widgets (rails, tiles)
  with Adwaita styling; dialogs/preferences stay stock Adwaita (they're
  2-foot tasks done with a keyboard nearby). Focus ring via CSS on
  `:focus` states, hover disabled.
- **hearth** — visual mimicry: CSS custom properties mirroring Adwaita
  colors/radii/type; Adwaita-like toggles and list rows in the setup
  wizard; the ambient card deck is custom but tokens-conformant. (If
  hearth is ever rebuilt native, it becomes a GTK app with couch's
  ambient layer; the token sheet makes that migration cosmetic-free.)
- **zoetrope** — adapted, not adopted: see-through optics invert the
  premise (black = transparent, dim backgrounds are free, opaque panels
  are rude). Zoetrope uses the **"Adwaita-through-glass" variant**:
  Adwaita accent + type ramp + radii, but panels are translucent
  bright-stroke surfaces per Android XR/Glimmer guidance
  ([15](15-ui-research-round2.md) §B). Dialog/preferences UI that would
  be Adwaita on desktop appears as a panel rendered with the same
  spacing/roles so it *reads* Adwaita.

## Shared grammars (behavior, not pixels)

1. **Input vocabulary** (zoetrope docs/12, now suite-wide):
   `prev/next/up/down/activate/back/recenter` + pointer + text. Couch's
   remote and hearth's touch/swipe map onto the same verbs; any new
   input device (ring, watch, voice) is a new emitter for all three.
2. **The three-layer stage** (ambient / content / anchor) from docs/12
   generalizes: hearth is 90% ambient layer + 10% panels; couch is 90%
   panels + ambient screensaver; zoetrope is the full stack.
3. **Overlay control center**: same anatomy everywhere — now-playing +
   transport, volume/brightness, profile chip, settings entry — summoned
   by one action (long-press / look-down / swipe-down), dismissed by
   back.
4. **First-run + recovery**: setup wizards are 2-foot Adwaita-style
   flows (couch has this; hearth's web wizard adopts tokens); every
   shell has a one-action "recenter/reset view" concept (zoetrope:
   recenter; couch: Home; hearth: tap-anywhere-from-ambient).

## Shared services (beyond pixels — the deeper cohesion)

- **Library**: ripsaw's `library_root` + Jellyfin naming is the common
  content substrate (zoetrope + couch today; hearth's Jellyfin app
  container already speaks Jellyfin).
- **Resume/watch-state**: couch's ContentAggregator is the natural home
  of the cross-source Watch Next row; zoetrope should consume it (HTTP,
  same LAN) rather than reinventing state.
- **Playback engine**: stereoscope `probe`/`stream` for 3D on zoetrope;
  mpv/libmpv everywhere; identical mpv option conventions.
- **Profiles**: couch's profile/kid-mode schema is the reference;
  zoetrope/hearth adopt its semantics (even if enforcement is lighter).

## Roadmap for cohesion (cheap first)

1. Publish the token sheet (colors/type/radii/focus) as a small file each
   repo vendors: `suite-tokens.{css,py}` generated from one YAML source
   (this doc's appendix when implemented).
2. couch: align focus ring + rail metrics to tokens (mostly already
   true); adopt the resume-row semantics formally.
3. zoetrope: apply the Adwaita-through-glass palette + type ramp in
   `apps/base.py` texture drawing (single file change); align tile
   radii/focus ring.
4. hearth: swap kiosk CSS palette to token values; adopt ambient
   card-deck grammar from [15](15-ui-research-round2.md) §E.
5. Later: shared `suite-ui` Python helpers (rail/tile/focus logic) used
   by couch and zoetrope's picker once both stabilize.
