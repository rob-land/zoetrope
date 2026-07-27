# 05 — postmarketOS / Mainline Linux Feasibility

Assessment of whether the Beam Pro can run postmarketOS (or any mainline-ish Linux), including the
dual-camera stereoscopic capture. Based on on-device state + public mainline/pmOS/community sources.

## Verdict

| Goal | Verdict |
|---|---|
| Boot postmarketOS via **downstream (vendor) kernel** | **Plausible** for a determined porter |
| **Mainline** Linux port (upstream kernel) | **Large from-scratch effort** — SoC not upstreamed |
| **Stereoscopic dual-camera capture** under Linux | **Effectively not portable** near-term |
| Keep the **glasses AR mode** (3D shell) under Linux | **No** — depends on XREAL's proprietary stack |

---

## Bootloader / flashing — OK

The device is a standard Qualcomm A/B fastboot device. Current state is fully **locked**
(`ro.boot.flash.locked=1`, `vbmeta.device_state=locked`, `verifiedbootstate=green`) with OEM-unlock
**disabled** (`sys.oem_unlock_allowed=0`). But that toggle is user-accessible:

1. Enable **Developer Options** → **OEM unlocking** and **USB debugging**.
2. `adb reboot bootloader` (or hold **Power + Vol-Down**).
3. `fastboot flashing unlock` (⚠ wipes all user data).

Community guides confirm `fastboot flashing unlock` works on the Beam Pro (there are XDA/unofficial
root guides and a Magisk boot-image workflow). So the prerequisite for any custom OS is satisfiable —
there is no fused-shut bootloader here.

**Costs of unlocking:** full data wipe; verified-boot state changes (boot warning); **Widevine L1 /
DRM breaks** (so the streaming apps present on this unit — Plex/Max/etc. — lose HD playback); warranty
void.

## SoC mainline status — weak

- **SM6450 "parrot"** has **no upstream device tree**. `arch/arm64/boot/dts/qcom/sm6450.dtsi` does not
  exist in Linus's tree (verified: 404), and there is no `sm6450`/`sm7435`/`parrot` file in the qcom
  DTS directory.
- Do **not** confuse it with **QCM6490** (Snapdragon 7c+ Gen 3 / IoT), which *is* well-supported
  upstream — that's a different die. SM6450/SM7435 share the "parrot" codename but are not upstreamed to
  the same degree.
- postmarketOS has a *tracking wiki page* for "Snapdragon 7s Gen 2 / 6 Gen 1 (SM7435/SM6450)", but no
  evidence of a completed port; no dedicated `sm6450-mainline` community tree was found.
- Mainlining would mean writing, largely from scratch: GCC/RPMh clock controllers, interconnect,
  DISPCC + DSI, UFS PHY, USB/DP PHY, Adreno 710 (a7xx-class) GPU (freedreno/mesa a7xx is emerging),
  and CAMSS.

## The realistic path: downstream/"vendor kernel" pmOS

The pragmatic route (used for most locked-down Qualcomm phones before mainlining) is to reuse XREAL's
own **5.10 android12 kernel** and run a pmOS/Alpine rootfs on top:

- XREAL published a GPL kernel source repo: **`github.com/mmry2940/kernel_xreal_X4000`** ("Beam Pro /
  Parrot"). If it's the real vendor tree, it provides the parrot DTS, the **ILITEK** touch driver, the
  DSI panel driver, and the fuel-gauge/PMIC glue needed to build a boot image.
- Likely to work relatively easily this way: **display** (DSI panel), **touch** (`ILITEK_TDDI`),
  **sensors** (ICM4x6xx, MMC56x3, STK3A5x all have mainline analogues — though on a downstream kernel
  you'd use the vendor drivers anyway), **USB**, **WiFi/BT**.
- Hard parts (as always): **cellular modem** and **camera**.

## The dual stereoscopic cameras — the blocker

Stereo capture is welded to proprietary Android userspace:
- Hardware: two hardware-synced **Samsung S5KJN1** sensors + a `dual3d_cali_golden.bin` factory
  calibration.
- Software: **Camera2 logical-multicamera physical streams** on the **Qualcomm CamX/CHI HAL**, then
  HEIC/MV-HEVC spatial muxing via `libXrealSVVideo.so`.
- Why it won't port: **no mainline S5KJN1 V4L2 driver**, **no parrot CAMSS/libcamera** support, and the
  CamX HAL + XREAL libs are Android-only. On a downstream-kernel pmOS you'd have **no camera HAL** at
  all; on a mainline pmOS you'd be writing the sensor driver + CAMSS + hardware-sync + stereo
  calibration handling essentially from zero. Even single-camera capture needs an S5KJN1 driver first.

**Conclusion:** stereoscopic 3D capture on postmarketOS is not realistic in the near term.

## Sensor / driver availability cheat-sheet (for a mainline attempt)

| Component | Part | Mainline driver? |
|---|---|---|
| IMU | TDK ICM-4x6xx | Yes (`inv_icm42600`) |
| Magnetometer | Memsic MMC56x3 | Yes (`mmc35240`/`mmc56x3`) |
| ALS/Prox | Sensortek STK3A5x | Yes (`stk3310`-family) |
| Touch | ILITEK TDDI | Downstream (needs port from vendor tree) |
| DSI panel | (unknown vendor) | No — needs generated panel driver |
| GPU | Adreno 710 | Emerging (freedreno a7xx) |
| Rear camera | Samsung S5KJN1 | **No** |
| Front camera | OmniVision OV8856 | Yes (`ov8856`) |
| SoC (clocks/display/USB/UFS/CAMSS) | SM6450 parrot | **No upstream dtsi** |

## Bottom line

Booting pmOS to a usable phosh/Plasma desktop (display, touch, sensors, USB, WiFi) is a feasible
**downstream-kernel** project given the unlockable bootloader and available vendor kernel source.
**Mainlining SM6450** is a major undertaking. Both the **stereoscopic capture** and the **glasses AR
experience** are **non-portable** — they depend on Qualcomm's CamX HAL and XREAL's proprietary NRSDK.
