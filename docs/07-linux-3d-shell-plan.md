# 07 — Plan: a Nebula-like 3D Shell on Linux

Goal: on a Linux laptop (or any Linux host), launch a Nebula-like spatial environment on the XREAL
glasses — floating/anchored 3D panels with head tracking — instead of just extending the desktop as a
flat second monitor.

Core insight: **you don't reverse-engineer XREAL's `.so` files.** They're Android/arm64, bound to
SurfaceFlinger/Unity/Android-USB, won't run on Linux, and only wrap a USB protocol + IMU stream that's
already open. The task is a **rendering/compositor** problem, and most of the software already exists as
FOSS on **Monado** (the open OpenXR runtime).

---

## What the glasses actually are

- A **USB-C DisplayPort stereo monitor** (two ~1080p micro-OLED panels; birdbath optics → negligible
  lens distortion, unlike VR).
- Plus a **USB HID sensor** (IMU) and (on One Pro) the **X1** onboard tracker + optional **Eye** UVC
  camera.

"3D" is not something the glasses compute for you — it's you rendering a left/right (side-by-side) image
and telling the glasses to split it per-eye. Head tracking is the IMU/pose.

---

## Feasibility, layered

| Tier | Result | How |
|---|---|---|
| 0 | Giant flat screen | Plug in DisplayPort — any OS, zero software |
| 0+ | One screen **anchored** in space (3/6DoF) | The One Pro + Eye do it **onboard** (X1) — press Space button, no host software |
| 1 | **Host-driven 3DoF spatial shell** (many head-tracked floating panels) — *the real "Nebula-like" target* | XRLinuxDriver (One Pro IMU) → Monado → Stardust XR / xrdesktop |
| 2 | **Host-driven 6DoF shell** (walk around, world-locked panels via the Eye) | Not open — onboard-anchoring only, or DIY SLAM (research-grade) |

---

## The plan (staged)

### Stage 0 — Prove the easy wins (an afternoon)
- Plug the One Pro into the laptop USB-C (DP-alt port) → confirm the display.
- Toggle the glasses' onboard anchor (Space button) → confirm onboard 3DoF/6DoF holds a screen still.
- Deliverable: validated hardware path + the zero-software baseline.

### Stage 1 — Host 3DoF into Monado
- Install **XRLinuxDriver**; confirm it reads the One Pro IMU. **Disable the glasses' onboard
  stabilizer/anchor** (the driver requires this) and update glasses firmware.
- Expose that orientation to **Monado** as a 3DoF HMD device; set the display to SBS/3D.
- The one XREAL-specific bit: the **command that puts the glasses into 3840×1080 SBS 3D mode**. The One
  may switch via EDID/a hardware hotkey, or you may need to replay the `nativeSetDpInputMode`/EDID
  command. **The Beam Pro is the perfect reference to capture this from** (see
  [08](08-operational-notes.md)).
- Deliverable: a working 3DoF OpenXR HMD on Linux.

### Stage 2 — Run the shell
Pick an existing FOSS spatial shell on top of Monado:
- **Stardust XR** (`stardustxr.org`) — an XR *display server* that runs Wayland apps as objects in 3D
  space. The closest open analog to Nebula; best for a bespoke spatial UI.
- **xrdesktop** (Collabora/Valve) — spatializes your existing GNOME/KDE desktop windows in 3D via
  OpenXR.
- **wlx-overlay-s / wayvr** — float Wayland/X11 screens as overlays in an OpenXR scene.
- Deliverable: multiple curved/floating, head-locked panels in the glasses — a genuine Nebula-like
  environment in **3DoF**, built almost entirely from existing parts.

### Stage 3 — 6DoF (optional, hard frontier)
Two honest options:
- **Cheap:** don't fight the X1 — render a wide/curved static canvas and let the glasses' **onboard**
  6DoF anchor it. Walk-around stability, but the host can't place panels at distinct host-controlled
  world coordinates.
- **Full control:** build a **Monado 6DoF driver** running visual-inertial SLAM (**Basalt** /
  OpenVINS) on the **Eye's UVC feed** + an IMU source, ignoring the X1's own tracking. Camera input is
  easy (UVC); the effort is real SLAM integration + calibration, and it duplicates what the X1 already
  does. Research-grade, not a weekend.
- Reverse-engineering the X1→host pose stream is a wildcard — it's unclear the pose is even sent to the
  host (the One does anchoring internally).

---

## Component map

```
[XREAL One Pro]  --DisplayPort SBS 3D-->  [laptop GPU]  <-- renders stereo scene
       |  IMU (USB HID)                          |
       v                                         v
[XRLinuxDriver] --3DoF orientation--> [Monado (OpenXR runtime)] --> [Stardust XR / xrdesktop]
                                                 ^
[XREAL Eye] --UVC frames--> (optional) [Basalt/OpenVINS VIO] --6DoF--/
```

## Prior art to build on (all FOSS)

- **Monado** — OpenXR runtime; has XREAL Air/Air2/Air2Pro 3DoF drivers (extend for One Pro).
- **XRLinuxDriver / Breezy Desktop** (`wheaney`) — already supports One/One Pro (3DoF), virtual monitors.
- **Stardust XR** — spatial display server / 3D Wayland shell.
- **xrdesktop** — desktop-in-VR/AR via OpenXR.
- **wlx-overlay-s**, **wayvr** — Wayland screens as OpenXR overlays.
- **Basalt** / **OpenVINS** / **ORB-SLAM3** — VIO/SLAM for the DIY 6DoF route.

## Bottom line

A **3DoF Nebula-like shell is very achievable** by assembling Monado + XRLinuxDriver + Stardust XR /
xrdesktop, with only a small XREAL-specific SBS-mode command to nail down (capturable from the Beam
Pro). **True host-driven 6DoF via the Eye is the wall** — XREAL keeps the X1's pose closed, so you
either accept onboard anchoring or reimplement SLAM yourself.
