# 12 — Interaction design: driving a spatial shell on phone and desktop

*Companion to [11](11-xr-landscape-and-vision.md) (vision) and
[13](13-app-catalog-and-roadmap.md) (apps). This doc answers: what do your hands do?*

## Principles

1. **Head gaze is the cursor you always have.** It's fast but coarse
   ([study](https://arxiv.org/pdf/1905.05810)), so every gaze-selectable target stays
   big (our tiles are ~20° apart). Gaze *highlights*; something else *commits*.
2. **Every input is an event source emitting one small vocabulary.** zoetrope already
   runs on `prev/next/up/down/activate/back/recenter` + pointer yaw/pitch + text.
   Keyboard, Daydream, head gaze, and the phone web-remote all speak it; adding a ring,
   a watch, or voice later is a new emitter, not a redesign.
3. **No input hostage-taking.** Any single device must be sufficient: glasses alone
   (gaze + dwell as last resort), phone alone, keyboard alone, controller alone.
4. **Comfort beats immersion.** Recenter is always one action away; nothing requires
   holding your head still or craning; long sessions default to anchor-style stability.

## The input matrix

| Context | Point/select | Commit | Text | Notes |
|---|---|---|---|---|
| **Desktop, supplementary** (real monitor + glasses surround) | mouse stays primary on the real screen; head gaze picks *panels* | click / Enter | physical keyboard | Glasses panels are glanceable; deep interaction can "focus" a panel to the main screen |
| **Desktop, primary** (kiosk, lid closed) | head gaze; mouse optional as a spatial ray | Enter / click / Daydream click | physical keyboard | Today's kiosk already works this way minus mouse-ray |
| **Linux phone, primary** (phone in pocket or hand) | head gaze; **phone screen = touchpad** (web-remote today, native later) | tap | phone OSK for short text; BT keyboard for real work; voice later | The phone is the Daydream: swipe = prev/next, tap = open, two-finger tap = back, hold = recenter |
| **On the move** (sideview-style) | nothing — glanceable only | single button/tap at most | none | Interaction while walking is a glance, not a session ([13](13-app-catalog-and-roadmap.md) has the safety rules) |
| **Anywhere** | Daydream/ring controller if you have one | click | — | Nice-to-have, never required |

**Do we need a separate controller?** No — that's the design decision. The Daydream
support we built is an *enhancer* (laser-pointer precision, off-desk media control),
but the phone (on phones) and the keyboard+mouse (on desktops) are the canonical
inputs because they're already in your hands. This matches where the industry went:
phone-as-trackpad for phone-tethered glasses, neural bands/rings as premium extras
([taxonomy](https://ar5iv.labs.arxiv.org/html/1707.09728)).

**Text input** is honest tiers: physical keyboard (best, desktop), phone keyboard
(fine, short strings), voice (future, needs on-device STT), dwell keyboard (worst,
accessibility fallback). The terminal app scaffolded in `apps/term.py` routes real
keystrokes already — the same path an OSK or STT would feed.

## Primary *and* supplementary from one UI: the layer model

The same scene serves both postures by stacking three layers, differing only in
which are populated:

```
Layer 2  AMBIENT   clock, battery, notifications, now-playing — small, peripheral,
                   low-refresh, never focused, auto-hides when a panel is fullscreen
Layer 1  PANELS    the working set: virtual monitors, app windows, media viewers,
                   arranged on the arc; one can be "focused" (bigger, centered)
Layer 0  ANCHOR    the stage: floor grid, recenter reference, (later) passthrough hint
```

- **Supplementary mode** = Layer 1 holds 1-3 *virtual monitors* mirroring/extending the
  host session, parked at arc positions your physical monitor doesn't occupy (e.g.
  main screen dead ahead through the glasses' transparent center, panels at ±25°).
  Ambient layer on. zoetrope adds no chrome over the desktop's own.
- **Primary mode** = Layer 1 holds the launcher arc and native/hosted apps; ambient on;
  zoetrope owns all chrome.
- The **same panel** can migrate: a movie started as a floating panel next to your
  monitor (supplementary) survives unplugging the monitor and becomes the primary
  session's fullscreen panel. Panels are the unit; posture is just layout policy.

### Display-behavior modes (the Nebula parity set)

Per-panel, not global — this is where we can beat the vendor software:

| Mode | Behavior | Implementation status |
|---|---|---|
| **Head-locked** | follows the head rigidly (HUD) | trivial (skip view rotation) — for ambient layer |
| **Anchor** | fixed in world yaw; you look around it | today's default |
| **Smooth follow** | eases toward gaze center with damping | small: low-pass the shell's view of head yaw |
| **Sideview** | small panel parked at an edge, head-locked | small: head-locked + corner offset + shrink |
| **Ultrawide** | one panel spanning ~2 tiles' arc | mostly a width_m change + curved mesh later |

The glasses can also do anchor/follow *on-chip* (better latency). Long-term:
host-side modes for the surround layer, on-chip mode for the main mirrored screen,
switched over the USB control protocol once we've reverse-engineered mode-set
(see backlog in [13](13-app-catalog-and-roadmap.md)).

## Gesture and mapping reference (current + planned)

```
                     launcher            app (media)         app (terminal/hosted)
head gaze            select tile         —                   —
←/→  · h-swipe · vol prev/next tile      smaller/bigger      sent to app (ANSI)  [planned]
↑/↓  · v-swipe       —                   push/pull           sent to app         [planned]
Enter · click · tap  open                (app-defined)       sent to app
Backspace · app-btn  —                   back to launcher    back (Esc leaves app first) [planned]
R · home-btn · hold  recenter            recenter            recenter
Esc                  quit                back                back                [planned]
phone remote         same vocabulary over the web-remote (scaffolded in remote.py)
```

Open questions parked for later: dwell-to-click tuning (ms vs. false positives),
voice command grammar, whether smooth-follow should be per-panel or per-layer, and
phone-as-6DoF-wand (phone IMU streamed like the Daydream — plausible, silly, fun).
