# 01 — Hardware Overview

Everything known about the XREAL Beam Pro (`X4000`) hardware, from `getprop`, `dumpsys`, `/sys`,
`/proc`, and the DRM/sensor/camera subsystems.

## Identity

| Field | Value |
|---|---|
| Brand / Manufacturer | XREAL |
| Model | `X4000` |
| Device / board / platform | `X4000` / `parrot` / `parrot` |
| Marketing name | Beam Pro |
| OTA model | `XREAL_X4000_ROW` (ROW = Rest Of World / global) |
| Android version | 14 (SDK 34) |
| Build fingerprint | `XREAL/X4000/X4000:14/UKQ1.231222.001/X4000_X502_260518_ROW:user/release-keys` |
| Build id / incremental | `UKQ1.231222.001` / `X4000_X502_260518_ROW` |
| Build date | 2026-05-18 (`Mon May 18 09:26:19 CST 2026`) |
| Build type | `user` (release-keys) — production build |
| First API level | 34 |

## SoC — Qualcomm SM6450 "parrot" (Snapdragon 6 Gen 1)

| Field | Value |
|---|---|
| `ro.soc.manufacturer` | QTI (Qualcomm Technologies Inc.) |
| `ro.soc.model` | **SM6450** |
| `ro.board.platform` | `parrot` |
| `ro.hardware` | `qcom` |
| Board API level | 31 (SoC bring-up baseline) |
| Fab/process | 4 nm (Snapdragon 6 Gen 1, public spec) |

**CPU** — arm64 (`arm64-v8a`), big.LITTLE, 8 cores:
- 4× **Cortex-A78** performance cores — `CPU part 0xd41`, variant `0x1` (reported as `kryo300`-class in `dalvik.vm.isa.arm64.variant`).
- 4× **Cortex-A55** efficiency cores — `CPU part 0xd05`.
- Public spec: 4×A78 @ up to ~2.2 GHz + 4×A55 @ ~1.8 GHz.
- CPU features: `fp asimd aes pmull sha1 sha2 crc32 atomics fphp asimdhp asimdrdm lrcpc dcpop asimddp`.

**GPU** — **Adreno 710** (`/sys/class/kgsl/kgsl-3d0/gpu_model` → `Adreno710v1`).
- `ro.hardware.egl = adreno`, `ro.hardware.vulkan = adreno`. GLES 3.x + Vulkan.

**Kernel** — `5.10.240-android12-9-g10cb5814f5f0-ab467`, `#1 SMP PREEMPT`, built `2026-03-31`, aarch64
(Toybox userland tools). Android Common Kernel (ACK) `android12-5.10` branch.

## Memory & storage

| Resource | Value |
|---|---|
| RAM | **8 GB** (`MemTotal: 7,660,940 kB`) |
| Storage | **UFS**, ~256 GB class (user data ~211 GB available on `/data`) |
| Storage topology | UFS with multiple logical units exposed as `/dev/block/sda`–`sdf` |
| Page size | 4096 (`ro.product.cpu.pagesize.max`) |

## Display (internal panel)

| Field | Value |
|---|---|
| Panel type | MIPI **DSI**, DRM connector `card0-DSI-1` |
| Resolution | **1080 × 2400** |
| Refresh | 60 Hz |
| Density | 480 dpi (`ro.sf.lcd_density`), ~403 × 406 physical dpi |
| Diagonal | 6.497" (`ro.odm.xreal.lcdsize = 6.497`) |
| Panel vendor | Reports EDID PnP `QCM` internally; exact panel model not exposed to non-root |
| Max luminance | ~500 nits; brightness LUT present in `DisplayDeviceConfig` |
| Rounded corners | 60 px radius all corners |

**Display engine:** Qualcomm **SDE / MDSS** ("Snapdragon Display Engine"). DRM shows 3 CRTCs
(`sde-crtc-0/1/2`) and connectors `card0-DSI-1` (internal), **`card0-DP-1`** (DisplayPort — this is
where glasses attach via USB-C DP Alt Mode), and `card0-Virtual-1`. QTI display services present:
`display.smomoservice` (SmoMo smooth-motion), `vendor.qti.hardware.display.config.IDisplayConfig`,
`dpmservice` (`com.qti.dpm` display post-processing).

## Sensors

| Type | Part | Vendor |
|---|---|---|
| Accelerometer + Gyroscope (IMU) | **ICM-4x6xx** | TDK InvenSense |
| Magnetometer | **MMC56x3x** | Memsic |
| Ambient light + Proximity | **STK3A5x** | Sensortek |
| SAR (specific absorption rate, 5 ch) | **SMTC** SAR | Semtech |

Note: these are the *phone's* sensors. The glasses have their own IMU (read over USB — see
[02](02-glasses-detection-and-mode-swap.md)/[03](03-usb-protocol-and-glasses-models.md)).

## Cameras

Full detail in [04 — Cameras & stereoscopic capture](04-cameras-and-stereoscopic-capture.md). Summary:

| Role | Sensor | Notes |
|---|---|---|
| Rear main | Samsung **S5KJN1** (`s5kjn1_ofilm_main`) | 50 MP, 1/2.76" |
| Rear aux | Samsung **S5KJN1** (`s5kjn1_ofilm_aux`) | 50 MP — second stereo sensor |
| Front | OmniVision **OV8856** (`ov8856_lce_front`) | 8 MP |

The two rear sensors form a hardware-synced **logical multi-camera** used for stereoscopic 3D
photo/video (`persist...spatialvideo.mode = 3`, calibration file `dual3d_cali_golden.bin`).

## USB & connectivity

- **Dual USB-C ports.** The USB event log shows two custom port subsystems, `usb1_hint` (port_1) and
  `usb2_hint` (port_2), and both `dumpsys usb` ports report `can_change_mode=true` (dual-role capable).
  At least one supports **DisplayPort Alt Mode** (the glasses connector). The internal glasses/DP link
  is the `card0-DP-1` DRM connector.
- **USB controller:** `a600000.dwc3` (Synopsys DesignWare USB3 DRD), configfs gadget.
- A custom `com.xreal.water.ACTION_WATER_PORT` intent + `usbX_hint` subsystems handle per-port
  state/liquid detection.
- **WiFi / Bluetooth:** Qualcomm connectivity (companion combo chip; full BT profile set enabled —
  A2DP, AVRCP, HFP, HID host/device, MAP, OPP, PAN, PBAP, ASHA, etc.). Exact WCN part not exposed to
  non-root.
- **Cellular:** RIL present (`ril.subscription.types = NV,RUIM`) — modem exists (SM6450 has an
  integrated modem), though the Beam Pro is marketed WiFi-centric.

## Power

- PMIC via **`pmic_glink`** / **UCSI** (USB-C PD). Power-supply nodes: `battery`, `bms` (battery
  monitoring system / fuel gauge), `charger_standalone`, `usb`, `ac`, plus `-bak` (backup) variants.
- Standard Qualcomm PMIC family for SM6450 (PM6450/PMK-class).

## Bootloader & secure boot

| Field | Value |
|---|---|
| `ro.boot.flash.locked` | **1** (locked) |
| `ro.boot.vbmeta.device_state` | **locked** |
| `ro.boot.verifiedbootstate` | **green** |
| `ro.boot.secureboot` | 1 |
| `sys.oem_unlock_allowed` | **0** (OEM-unlock toggle currently OFF) |
| `ro.secure` / `ro.debuggable` | 1 / 0 |
| AVB | vbmeta AVB v1.0, SHA-256, `invalidate_on_error=yes` |
| A/B slots | Yes (`ro.build.ab_update = true`, current slot `_a`) |

The device is fully locked, but the OEM-unlock toggle in Developer Options is user-accessible and
`fastboot flashing unlock` is reported to work (see [05](05-postmarketos-feasibility.md)).

## Partition layout (A/B, UFS)

Standard Qualcomm A/B super-partition layout across UFS LUNs `sda`–`sdf`. Key partitions
(`/dev/block/by-name/`): `boot_a/b`, `dtbo_a/b`, `vbmeta`/`vbmeta_system`, `abl_a/b` (Android
bootloader), `xbl`/`aop`/`hyp`/`tz`(keymaster)/`devcfg`/`cpucp`/`featenabler`, `modem_a/b`, `bluetooth_a/b`,
`dsp_a/b`, `recovery_a/b`, `super` (dynamic: `product/system/system_ext/vbmeta_system` per
`ro.product.ab_ota_partitions`), `metadata`, `persist`, `frp`, `misc`, `userdata`. Full list in the
[appendix](appendix-raw-evidence.md).

## Notable XREAL system software (from `pm list packages`)

| Package | Role |
|---|---|
| `com.xreal.evapro.nebula` | **Nebula** — the spatial launcher / glasses driver (system UID) |
| `com.xreal.evapro.camera` (`LCCamera.apk`) | Stereoscopic camera app |
| `com.xreal.evapro.store` | App store |
| `com.xreal.evapro.id.universal` | XREAL account |
| `com.xreal.evapro.systemupdate` | OTA (`XrealOtaService`) |
| `com.xreal.analytics`, `com.lct.infoupload` | Analytics / log upload |
| `com.phxreal.setupwizardrow` | Setup wizard |
| `com.qualcomm.qti.xrvd.service` | **Qualcomm QXR** "XR Virtual Display" service |
| `com.qualcomm.qti.xrcb` | **Qualcomm QXR** bridge (Core/Cam/Split/Mod/Comm) |
| `com.qualcomm.wfd.service` | WiFi Display |

The user's unit also runs a large set of third-party F-Droid/FOSS apps (Fennec, VLC, Jellyfin,
Syncthing, Termux, KeePass, Bitwarden, etc.) — i.e. it's used as a general Android device, not just a
glasses companion.
