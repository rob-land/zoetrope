# 06 — XREAL One Pro & XREAL Eye

Analysis of the specific glasses this unit uses: the **XREAL One Pro** (with the onboard **X1** chip)
and the detachable **XREAL Eye** camera that adds 6DoF. Sourced from the Nebula model map + native
libs, the `eye_uvc` code strings, and public XREAL/community documentation.

---

> **Live-confirmed 2026-07-09** (this unit, over wireless adb — see
> [09](09-live-capture-one-pro-eye.md)): EDID `name=XREAL One Pro, PnP=MRG, product=16640, mfg wk49/2024`;
> DP exposes **3840×1080@60** (SBS) **and 1920×1080@90**; the launcher ran in **3DoF** (IMU
> head-tracking) with the **Eye idle / 6DoF gated** (external-camera HAL = 0 devices, no `eye_uvc`, no
> camera client); the glasses' **IMU streams to the host** (accel/gyro/mag); glasses on **USB-C port 2**.

## XREAL One Pro

| Field | Value |
|---|---|
| Nebula model type | **6** ("Ethernet/G" series) |
| USB PIDs | `0x435` / `0x436` (VID `0x3318`) |
| EDID product-id | `16640` (matched with PnP id `MRG`) — **confirmed live** |
| Display modes | **3840×1080@60** (SBS 3D, active) and **1920×1080@90** (mono/high-refresh) — confirmed live |
| Display switch path | `nativeSetDpCurrentEdid(5)` + `nativeSetDpInputMode(1)` → **3840×1080@60 side-by-side 3D** |
| Optics | "X-Prism" birdbath, real-3D stereo; ~57° FoV; up to 120 Hz FHD per eye (public spec) |
| Onboard compute | **XREAL X1** co-processor |

**The X1 chip is the key differentiator.** Unlike the Air series (where the *host* reads the raw IMU
and does all stabilization), the One series runs tracking **on the glasses**:
- **Native 3DoF anchoring** onboard: the glasses can lock a screen in space themselves, on a plain
  video feed, with **no host software** (press the glasses' Space button). The X1 reprojects/warps the
  displayed image in-glasses.
- Very low latency: XREAL advertises **~3 ms motion-to-photon** because the tracking→warp path is
  entirely on-device.

Implication for a third-party host: the One Pro will hold a screen steady in space on **any** host
(including a Linux laptop) with zero software — but that stabilization is done by the glasses, and the
host is not told the pose.

---

## XREAL Eye

| Field | Value |
|---|---|
| What it is | Detachable camera module that clips onto the XREAL One / One Pro |
| Sensor | **12 MP RGB** camera |
| USB class | **UVC** (USB Video Class) — code strings `eye_uvc_start` / `eye_uvc_end` |
| Adds | Native **6DoF** spatial anchor + spatial photo/video capture |
| SLAM | **Monocular SLAM, computed on the X1 chip in the glasses** (not the host) |
| NRSDK lib | Handled via `libnr_external_sensor.so` (+ `libnr_plugin_6dof.so`, `libnr_spatial_anchor.so`) |

**How 6DoF works (per XREAL docs):** the Eye provides the camera input; the **X1 chip does the spatial
computing** (monocular SLAM) — no external base stations. With the Eye attached, a screen stays locked
in world space as you walk around / lean in. Limitations: poor performance in low light, outdoors, or
scenes with only distant features (typical of monocular VIO).

**Two facts that matter enormously for a Linux port:**
1. The Eye is a **standard UVC camera** → its frames are trivially available on Linux via `uvcvideo`
   with zero reverse engineering. (Confirmed from the `eye_uvc_start`/`eye_uvc_end` code strings; the
   exact UVC PID/formats would need a live capture — see [08](08-operational-notes.md).)
2. The **6DoF pose is computed on the X1 and consumed only inside XREAL's NRSDK** — there is **no
   `nativeGetPose`/`nativeGet6Dof`** in the Java-visible JNI surface (see
   [03](03-usb-protocol-and-glasses-models.md)). So a non-XREAL host cannot simply *ask the glasses*
   for 6DoF pose.

---

## What Nebula does with One Pro + Eye

- Detects type 6, runs the "Ethernet/G" display path (SBS 3D EDID).
- Strings observed: `"XREAL One Pro"`, `display6DofHome`, `"6DoF glasses Home display, default on"`,
  `HEADLOCKED_CHANNEL0/1`, `HEADLOCKED_STEREO`, `"slam"`, `AnchorInfo`, `AnchorType`, `eye_uvc_start`
  (referenced from `LauncherMRAPPReceiver` — MR apps start/stop the Eye UVC feed).
- Bundles the full host-side CV SDK (`libnr_plugin_6dof`, `libnr_spatial_anchor`, `libnr_meshing`,
  `libnr_hand_tracking`, `libnr_image_tracking`, `libopencv_java4`). Note the tension: the One Pro does
  its core anchoring **onboard on the X1**, while this bundled SDK is the general NRSDK (also serving
  the older Air 2 Ultra host-SLAM path). Which features run where for One Pro + Eye specifically is best
  confirmed by a live capture.

---

## Linux support status (community)

| Project | One / One Pro support | Tracking | Notes |
|---|---|---|---|
| **XRLinuxDriver** (`wheaney`) | **Yes** (One, One Pro listed) | **3DoF** (reads glasses IMU) | Requires **disabling the onboard stabilizer/anchor** on the glasses + latest firmware; "unofficial, open-source SDK", noted drift |
| **Monado** (OpenXR runtime) | **No** (Air/Air2/Air2Pro only) | 3DoF | No One-series driver yet; 6DoF only via external SLAM (Basalt/ORB-SLAM3/Kimera) |
| **Breezy Desktop** (`wheaney`) | Via XRLinuxDriver | 3DoF | Virtual anchored monitors on GNOME 45–50 / KDE Plasma 6 |

**Net:** host-driven **3DoF** on the One Pro is available today (XRLinuxDriver reads the IMU). Host-driven
**6DoF via the Eye is not available in open tooling** — the X1's pose is closed, Monado has no One-series
6DoF, and XRLinuxDriver is 3DoF-only and explicitly wants onboard anchoring turned off. See
[07](07-linux-3d-shell-plan.md) for the plan and the two 6DoF options.
