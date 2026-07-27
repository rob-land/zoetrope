# XREAL Beam Pro (X4000) + Glasses — Investigation Docs

Reverse-engineering and hardware notes for the **XREAL Beam Pro** spatial-computing companion
device (model `X4000`, codename `parrot`) and the XREAL AR glasses it drives, plus feasibility
studies for postmarketOS and a Linux "Nebula-like" 3D shell.

All findings were gathered from a physical unit over `adb` (device **not rooted**, bootloader
**locked**) and by decompiling the on-device system apps (Nebula launcher, XREAL camera, the
Qualcomm QXR services). Where a claim is inferred rather than directly observed in code/props,
it is flagged inline.

## Contents

| Doc | What's in it |
|---|---|
| [01 — Hardware overview](01-hardware-overview.md) | SoC, CPU/GPU, RAM/storage, sensors, display, USB, power, bootloader, partitions |
| [02 — Glasses detection & mode swap](02-glasses-detection-and-mode-swap.md) | The "secret sauce": how plugging in glasses launches the 3D shell and turns the phone into a touchpad |
| [03 — USB protocol & glasses models](03-usb-protocol-and-glasses-models.md) | XREAL VID/PID map, per-model table, the glasses' USB interfaces & permission grants |
| [04 — Cameras & stereoscopic capture](04-cameras-and-stereoscopic-capture.md) | Dual 50 MP sensors, spatial photo/video pipeline, camera HAL |
| [05 — postmarketOS feasibility](05-postmarketos-feasibility.md) | Mainline status, bootloader unlock, what ports and what doesn't |
| [06 — XREAL One Pro & XREAL Eye](06-xreal-one-pro-and-eye.md) | The specific glasses this unit uses: X1 chip, onboard 6DoF, the Eye camera |
| [07 — Linux 3D shell plan](07-linux-3d-shell-plan.md) | Plan for a Nebula-like spatial shell on a Linux laptop |
| [08 — Operational notes](08-operational-notes.md) | Wireless adb (required when glasses occupy the USB-C port), tooling, how to reproduce captures |
| [09 — Live capture: One Pro + Eye](09-live-capture-one-pro-eye.md) | Live wireless-adb session with the glasses attached — EDID, display modes, 3DoF-vs-6DoF state, IMU stream |
| [10 — Design: beamshell Linux shell](10-linux-shell-design.md) | Architecture of the `../beamshell/` Nebula-like shell (Python + moderngl + mpv) |
| [11 — XR landscape & vision](11-xr-landscape-and-vision.md) | Research pass over the Linux XR ecosystem + what beamshell 1.0 is (phone + desktop, two postures) |
| [12 — Interaction design](12-interaction-design.md) | How you drive it: input matrix per platform, the layer model, display-behavior modes |
| [13 — App catalog & roadmap](13-app-catalog-and-roadmap.md) | What's worth building for a face-worn display; walking/driving analysis; backlog + milestones |
| [Appendix — Raw evidence](appendix-raw-evidence.md) | Verbatim dumps: partitions, props, services, sensors, camera configs |

A runnable v0.1 of the shell lives in [`../beamshell/`](../beamshell/) (18 passing unit tests).

## TL;DR

- **Device:** Qualcomm **SM6450 "parrot"** (Snapdragon 6 Gen 1), Adreno 710, 8 GB RAM, ~256 GB UFS,
  Android 14, kernel 5.10.240. Dual USB-C, dual rear **Samsung S5KJN1 50 MP** cameras for stereoscopic
  3D capture.
- **Glasses detection** = USB **VID `0x3318`** (XREAL) attach **+** DisplayPort Alt-Mode display with an
  EDID whose PnP id is `MRG`/`NRL`. A system-privileged launcher app (**Nebula**, runs as
  `android.uid.system`) auto-starts and drives XREAL's native SDK.
- **Mode swap** = XREAL's NRSDK native libraries switch the glasses' DisplayPort into a 3840×1080
  side-by-side 3D mode and composite a stereo scene to it; the Unity launcher runs on the phone's own
  display as the "brain"; the phone screen becomes a touchpad whose touches are piped into the launcher.
- **postmarketOS:** downstream-kernel port is plausible (bootloader is unlockable); mainline is a
  from-scratch effort (no `sm6450.dtsi` upstream); stereoscopic camera capture is effectively
  non-portable.
- **Linux 3D shell:** a **3DoF** Nebula-like shell is achievable by assembling existing FOSS
  (Monado + XRLinuxDriver + Stardust XR / xrdesktop). **6DoF via the XREAL Eye is closed** (the X1 chip
  computes it and does not expose pose to the host).

## Provenance / method

- Data collected via `adb shell` (getprop, dumpsys, /sys, /proc, service list) and `adb pull` of APKs.
- APKs decompiled with `apktool` (smali + resources) and `jadx` (Java).
- Cross-checked against XREAL/community/Qualcomm public documentation (cited in the relevant docs).
- Investigation date: 2026-07-09. Firmware: `X4000_X502_260518_ROW` (build `UKQ1.231222.001`, 2026-05-18).
