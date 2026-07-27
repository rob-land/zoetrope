# 03 — USB Protocol & Glasses Models

The USB identity of XREAL glasses, the per-model map Nebula uses, and the glasses' USB interface
composition. Sourced from the decompiled Nebula device-filter resources and the
`com.xreal.glassesdisplayplugevent` / `ai.nreal.glasses.control` code.

---

## Vendor IDs

| VID (dec) | VID (hex) | Owner | Used for |
|---|---|---|---|
| 13080 | **0x3318** | XREAL / Nreal | Main glasses VID (Air/One series, `AIR_SERIES_VID`) |
| 1155 | 0x0483 | STMicroelectronics | STM32 CDC control MCU in composite ("Ella") glasses |
| 1158 | 0x0486 | STMicroelectronics | STM32 in HID class-3 mode (sensor/OTA) |
| 1449 | 0x05A9 | OmniVision | OV580 stereo-camera hub / RGB camera |
| 3034 | 0x0BDA | Realtek | USB audio codec |
| 2071 | 0x0817 | (RGB camera bridge) | RGB world camera |
| 21315 | 0x5343 | (misc) | Present in filter (product 0x200) |
| 24578/24579 | 0x6002/0x6003 | (custom) | Vidda/custom glasses variant (product 0x109B) |

`0x3318` = 13080 decimal (`3*4096 + 3*256 + 1*16 + 8`). This is the value seen throughout the
device-filter XML as `vendor-id="13080"`.

---

## Model map (type ↔ USB PID ↔ EDID product-id ↔ name)

From `com/xreal/glassesdisplayplugevent/util/USBVendorProductID.java` (`sUSBPidMap`) +
`ai/nreal/nebula/constant/GlassesNameConstant.java`. Each model exposes **two** USB PIDs (its two USB
configurations/interfaces). "EDID product-id" is what the DisplayPort EDID reports (matched with PnP id
`MRG` new / `NRL` old).

| Type | USB PIDs (VID 0x3318) | EDID product-id | Model | Series |
|---|---|---|---|---|
| 1 | STM32 0x0483:0x5740 (+HID 0x0486:0x573C) | 12593 / 12594 (`NRL`) | **Ella** (composite, Ultra-class MCU device) | special |
| 2 | 0x423 / 0x424 | 12594 | XREAL Air | Air |
| 3 | 0x431 / 0x432 | 12597 | XREAL Air 2 Pro | Air |
| 4 | 0x427 / 0x428 | 12596 | XREAL Air 2 | Air |
| 5 | 0x425 / 0x426 | 12598 | XREAL Air 2 Ultra | Air |
| 6 | 0x435 / 0x436 | 16640 | **XREAL One Pro** | One / "Ethernet/G" |
| 7 | 0x437 / 0x438 | 16641 | XREAL One | One / "Ethernet/G" |
| 8 | 0x439 / 0x43A | 16656 | XREAL (generic/default) | One / "Ethernet/G" |
| 9 | 0x43D / 0x43E | 16642 | XREAL 1S | One / "Ethernet/G" |
| 10 | 0x43F / 0x440 | 12599 | xbx a01 | — |
| 11 | 0x441 / 0x442 | 12600 | xbx a01+ | — |
| 1002 | VID 0x109B, PID 0x6003/0x6002 | — | custom/Vidda variant | custom |

Helper logic:
- `GlassesTypeUtil.isAir()` — product id in `sUSBPidMap`.
- `GlassesTypeUtil.isElla()` — STM32-class MCU VIDs (0x0483/0x0486/0x0482).
- `GlassesInitSetting.isEthernetSeriesGlasses()` — true when type ∉ [1..5] and ∉ [10..19]; i.e. the
  **One series (types 6–9)**. This selects the DP-EDID display-switch path (`nativeSetDpCurrentEdid` +
  `nativeSetDpInputMode`) rather than the Air-series `nativeSet2D3DMode`.

**Code quirk:** `sUSBPidMap.put(DisplayObserverHelper.MR_DISPLAY_HEIGHT, 7)` reuses the constant `1080`
(= 0x438) as the PID key for type 7.

**Two USB device filters** ship in Nebula:
- `res/xml/glasses_device_filter_not_ella.xml` — used by `SplashActivity` for auto-launch; the XREAL
  VID entries only (0x3318 PIDs + a couple of misc).
- `res/xml/glasses_device_filter.xml` — the full set, additionally matching the STM32 CDC
  (0x0483:0x5740), OmniVision (0x05A9), and Realtek (0x0BDA) devices of the composite ("Ella") glasses.

---

## Glasses USB interface composition (the "grants")

When glasses attach, Nebula requests permission for each USB function via
`ai.nreal.glasses.control` custom actions. These map to the glasses' USB interfaces:

| Grant action | Device / VID:PID | Role |
|---|---|---|
| `GRANT_USB_TTY` | STMicro CDC **0x0483:0x5740** | MCU **serial/CDC control channel** — set display mode, brightness, DoF mode, read firmware ("APP A") |
| `GRANT_USB_HID` | STMicro **0x0486:0x573C** | MCU in **HID class-3** mode — IMU/sensor reports, buttons, HID-mode OTA |
| `GRANT_USB_OV580` | OmniVision **0x05A9:0x0680 / 0xF580** | **OV580 stereo tracking cameras** (also reused as an IMU/config fd) |
| `GRANT_USB_RGB` | 0x0817/0x3318 : 0x0909/0x0910 | **RGB world/front camera** |
| `GRANT_USB_AUDIO` | Realtek **0x0BDA:0x4B77** | **USB audio** (glasses speakers/mic, UAC) |

Key implementation facts:
- Interfaces are opened via `UsbManager.openDevice()` → `UsbDeviceConnection.getFileDescriptor()`; the
  **fd is handed to native** (`libota-lib.so`, `libnr_libusb.so`). There is **no `/dev/tty*`** — the
  "TTY" name refers to the CDC control channel, accessed as raw USB.
- Direct Java `bulkTransfer`/`claimInterface` to the MCU HID class-3 interface (two ≥64-byte endpoints)
  lives in `ai/nreal/glasses/control/d.java`, used by `XrealGlasses` OTA (`NROTA*` / `build_cmd` /
  `nativeGlassesOtaControl*`).
- Realtek `controlTransfer` (in `com/aarlibr/aarlib/RtsVendorReq.java`) is **audio-codec firmware
  update**, not glasses control.

---

## The IMU / control JNI surface

From `com.xreal.glasses.api.Control` / `com.xreal.glasses.api.Startup` (native methods, satisfied by
`libnr_api.so`). Notable natives:

**DisplayPort / EDID / HDCP:**
`nativeGetDpCurrentEdid`, `nativeSetDpCurrentEdid`, `nativeGetDpInputMode`, `nativeSetDpInputMode`,
`nativeGetDpWorkingState`, `nativeSetDpWorkingMode`, `nativeSetDpDataFilterMode`,
`nativeGetDPFwVersion`, `nativeSetDPHDCPEnable`, `nativeSetDPLevel`, `nativeSetDPESDParam`,
`nativeSetAudioDpVolumeLevel`/`nativeGetAudioDpVolumeLevel`.

**IMU / tracking:**
`nativeImuInit`, `nativeImuResume`, `nativeImuPause`, `nativeImuDeInit`, `nativeSetIMUFrequencyDivider`,
`nativeGetImuInterruptCount`, `nativeRecenterGlasses`, `nativeSetZeroDofStableCtrl` /
`nativeGetZeroDofStableCtrl` (the smooth-follow / anchoring stabilization), `nativeSetControllerTrackingConfig`,
`nativeSendPrivilegedActivation`.

**Important:** there is **no `nativeGetPose` / `nativeGet6Dof`** in this Java-visible surface. Pose/6DoF
is computed and consumed **inside** the native SDK (`libnr_plugin_6dof.so`, `libnr_service.so`) and used
by the native compositor / Unity — it is not exposed as a clean host getter. This is central to why a
third-party host can't trivially get 6DoF pose (see [06](06-xreal-one-pro-and-eye.md)).

---

## Bundled NRSDK native libraries (in `com.xreal.evapro.nebula`)

The Nebula APK ships a full spatial-computing SDK (arm64 `.so`), including:

| Library | Purpose |
|---|---|
| `libnr_api.so` (38 MB) | Core NRSDK API (device control, display, IMU) |
| `libnr_service.so` (38 MB) | NRSDK service/runtime |
| `libnr_glasses_api.so` | Glasses API surface |
| `libnr_loader.so` | Loader |
| `libnr_libusb.so` | libusb-based USB access |
| `libnr_plugin_6dof.so` | **6DoF positional tracking** |
| `libnr_spatial_anchor.so` | **Spatial anchors** |
| `libnr_meshing.so` (29 MB) | **Environment meshing / reconstruction** |
| `libnr_hand_tracking.so` (44 MB) | **Hand tracking** |
| `libnr_image_tracking.so` | **Image/marker tracking** |
| `libnr_dual_agent_tracking.so` | Dual-agent tracking |
| `libnr_external_sensor.so` | **External sensor** (the XREAL Eye) |
| `libnr_rgb_camera.so` | RGB camera |
| `libNRBiasService_jni.so` | IMU bias calibration (→ `/data/vendor/xreal/online_bias.json`) |
| `libopencv_java4.so` (19 MB) | OpenCV |
| `libXREALXRPlugin.so`, `libXrealSVVideo.so` | XR plugin / stereo-video |

Also bundled: Qualcomm **QNN** (Neural Network) + **Genie** (on-device LLM) stacks
(`libQnnHtp*.so`, `libGenie.so`) — Nebula has on-device AI features.

The glasses driver also references a system-provided native lib
`libnr_api.xreal.so` (declared via `<uses-native-library>` in the manifest) that lives in the device's
`/system/lib64` (confirmed present on-device), plus `libXrealSVVideo.so`.
