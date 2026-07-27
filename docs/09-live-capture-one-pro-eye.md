# 09 — Live Capture: One Pro + Eye Session

Captured over **wireless adb** (`192.168.1.164:5555`) with the **XREAL One Pro + XREAL Eye** physically
connected and the Nebula spatial launcher running. Date 2026-07-09 ~20:12–20:16. This confirms (and in
places refines) the static analysis in docs 02/03/06.

> Why wireless adb: the glasses occupy the USB-C port that would otherwise carry wired adb, so live
> observation must be done over TCP/IP (`adb tcpip 5555` / Wireless debugging). See
> [08](08-operational-notes.md).

---

## Confirmed: the glasses display (One Pro)

From `dumpsys display` — external display **displayId 9**, `type EXTERNAL`, `"HDMI Screen"`:

| Field | Value |
|---|---|
| EDID product name | **`XREAL One Pro`** |
| EDID manufacturer PnP id | **`MRG`** |
| EDID product-id | **`16640`** |
| Manufacture date | week 49, **2024** |
| Physical port | `port=4`, address model `0x4036474076f896` |
| Active mode | **3840 × 1080 @ 60 Hz** (side-by-side stereo) — mode id 17 |
| Alternate mode | **1920 × 1080 @ 90 Hz** — mode id 18 |
| Flags | `FLAG_SECURE FLAG_SUPPORTS_PROTECTED_BUFFERS FLAG_PRESENTATION FLAG_TRUSTED` |
| Density | 213 dpi (43.157 × 19.455) |

This **exactly matches** the documented model map (One Pro = type 6, EDID product 16640, PnP `MRG`).
The two available modes are the important new detail:
- **3840×1080@60** — the side-by-side 3D mode (each 1920-wide half → one eye). This is what `set2D3D`
  selects for the launcher.
- **1920×1080@90** — a single-image high-refresh mode (mono / 2D, or per-eye 90 Hz). For a Linux stereo
  shell you'd drive **3840×1080@60**.

The internal phone panel (displayId 0) stays **ON** (1080×2400) — it runs the launcher "brain" and the
touchpad, exactly as documented.

## Confirmed: live Nebula VirtualDisplay (floating 2D panel)

A third display was live — **displayId 10**, `type VIRTUAL`, owner **`com.xreal.evapro.nebula` (uid
1000)**:
```
uniqueId = virtual:com.xreal.evapro.nebula,1000,
           com.xreal.virtualdisplay-com.android.settings/.homepage.SettingsHomepageActivity,0
1080 x 1440 @ 45 Hz, density 260,
FLAG_OWN_CONTENT_ONLY FLAG_DESTROY_CONTENT_ON_REMOVAL FLAG_SECURE FLAG_TRUSTED
```
This is **live proof** of the "mirror a 2D Android app as a floating panel in the space" mechanism
(doc 02 §"second display mechanism"): Nebula created a `VirtualDisplay` and launched the **Settings**
app onto it (1080×1440), to be textured onto a panel in the Unity scene. `removeMode 1` +
`DESTROY_CONTENT_ON_REMOVAL` = it's torn down when the panel closes.

## Confirmed: tracking is running in **3DoF** (not 6DoF) for the launcher

NRSDK telemetry (logcat tag `XREAL`, process `com.xreal.evapro.nebula:space`) shows steady-state:
```
[NRSDK] BuildDeviceMessage category:16 description:nr_perception_head_tracking_remote id:0 size:27
[NRSDK] controller imu type:1 recv:5000 ...      # type 1/2/3 = accel/gyro/mag
[NRSDK] NotifyImuDataWrapper <ts> <ts> <ts>, -0.0134 -0.0013 0.0024, 0.001    # gyro triplet
[NRSDK] NotifyControllerImuData <ts> <ts>, 0 0 0, 0.3796 1.6049 9.8395, 2     # accel triplet (~g on Z)
[NRSDK] controller imu temp 29.7 .. 30.0        # IMU die temperature (°C)
```
Key points:
- The active perception module is **`nr_perception_head_tracking_remote`** — head **orientation**
  (3DoF) driven by the glasses IMU. The glasses' **IMU stream reaches the host** (accel/gyro/mag),
  sampled at ~5000 (Hz/units), with die-temperature telemetry.
- **No 6DoF/SLAM was active.** A full-buffer search for `eye_uvc`, `6dof`, `slam`, `plane`, `meshing`,
  `anchor`, `NR_EDID`, `set2D3D`, `SetDpInputMode` returned **nothing** during the session.
- **The Eye camera was not streaming.** `dumpsys media.camera` reports the built-in cameras (4 devices,
  all closed) **plus** a `Camera Provider HAL external/0-0 (v2.7, remote)` reporting **`0 devices`** —
  i.e. the external-camera provider (the path the UVC Eye would use) had no active device. `Active
  Camera Clients` shows only the stereo photo app (`com.xreal.evapro.camera`) earlier in the day, none
  during this session.

**Interpretation:** even with the Eye physically attached, the **default launcher/home experience runs
in 3DoF** (IMU head-tracking; screens are head-locked/orientation-anchored). **6DoF/SLAM is gated** —
it engages only when a 6DoF experience is launched (which spins up the Eye's UVC feed + `libnr_plugin_6dof`
/ `libnr_spatial_anchor`). The bring-up/EDID-switch and any 6DoF init happened before the log ring
buffer window and were not re-captured (would require a re-plug or launching a 6DoF app while capturing).

## Confirmed: foreground / process topology

- `ai.nreal.nebula.space.LaunchSpaceAcrivity` (Unity, `:space` process, PID 8319) is the active
  launcher — running on the phone (display 0) as the "brain". A transient `DummyActivity` and
  `NRShadowActivity` are also present (used for task/activity plumbing).
- Native NRSDK threads log under tag `XREAL` from the `:space` process.

## Confirmed: which USB-C port the glasses use

USB event log: the glasses connect on **port 2** (`SUBSYSTEM=usb2_hint … PORT2=CONNECTED/CONFIGURED`),
while **port 1** reports `PORT1=CHARGING`. So on the Beam Pro the glasses (DP Alt Mode + USB) are on the
`usb2_hint` port; the other port is free for charging. (This is also why wired adb + glasses can't share
one port.)

## What could NOT be captured live (SELinux / non-root)

- `/sys/bus/usb/devices/*` (idVendor/idProduct/interface classes) — **denied** to the shell user, so the
  glasses'/Eye's raw USB VID:PID could not be re-read live. Values from the decompiled device filter
  stand: One Pro = `0x3318:0x435/0x436`; Eye UVC + STM32/OmniVision per doc 03.
- `dumpsys usb` does not print a host-device list on this build.
- `/sys/class/drm/card0-DP-1/{status,modes}` — denied (but the EDID came through `dumpsys display`).
- Fused head **pose** values are not logged at INFO level (only raw IMU + the perception module name).

## Net new facts vs. the static docs

1. One Pro EDID identity confirmed **live** (name/PnP/product/date).
2. One Pro DP exposes **two modes**: 3840×1080@60 (SBS 3D) and **1920×1080@90** (new).
3. The floating-2D-app **VirtualDisplay** mechanism observed live (Settings app @ 1080×1440).
4. The **glasses IMU streams to the host** (accel/gyro/mag, ~5 kHz, with temperature) — the 3DoF source.
5. The default experience is **3DoF**; **6DoF/Eye is gated** and was **idle** (external-cam HAL = 0
   devices, no `eye_uvc`, no camera client).
6. Glasses are on **USB-C port 2**.
