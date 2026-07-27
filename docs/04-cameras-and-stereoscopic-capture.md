# 04 — Cameras & Stereoscopic Capture

How the Beam Pro's dual rear cameras capture stereoscopic (3D) photos and videos. Sourced from
`dumpsys media.camera`, vendor camera props, `/vendor/lib64/hw`, and the decompiled XREAL camera app
(`com.xreal.evapro.camera` = `LCCamera.apk`).

---

## Sensors

| Role | Sensor | Vendor debug prop | Notes |
|---|---|---|---|
| Rear **main** | Samsung **S5KJN1** | `s5kjn1_ofilm_main` | 50 MP, 1/2.76", quad-Bayer (Tetracell) |
| Rear **aux** | Samsung **S5KJN1** | `s5kjn1_ofilm_aux` | 50 MP — **identical** second sensor for stereo |
| Front | OmniVision **OV8856** | `ov8856_lce_front` | 8 MP |

The two rear sensors are the same model — a deliberate choice for stereoscopic capture (matched
optics/geometry). Module maker "ofilm" (O-Film); front module "lce".

## Logical multi-camera / hardware sync

`dumpsys media.camera` shows the rear as a **Qualcomm logical multi-camera**:
- `android.logicalMultiCamera.physicalIds` = `byte[4]` (two 2-digit physical camera ids).
- `android.logicalMultiCamera.sensorSyncType` present — the two sensors are **hardware-synchronized**
  (frame-level sync, essential for stereo — both eyes captured at the same instant).
- The logical camera's "resource cost" is **66** (vs **33** for a single physical sensor) — i.e. it
  consumes two sensors' worth of pipeline.
- Capabilities on the rear logical camera include `LOGICAL_MULTI_CAMERA`, `RAW`, `MANUAL_SENSOR`,
  `MANUAL_POST_PROCESSING`, `BURST_CAPTURE`, `YUV_REPROCESSING`, `PRIVATE_REPROCESSING`.
- QTI vendor tags present: `org.codeaurora.qcamera3.logicalCameraType`,
  `com.qti.chi.logicalcamerainfo.NumPhysicalCameras`, `com.qti.chi.cameraconfiguration.PhysicalCameraConfigs`.
- Per-sensor **lens pose** metadata is exposed: `android.lens.poseTranslation` (float[3]),
  `android.lens.poseRotation` (float[4] quaternion), `android.lens.distortion` (float[5]),
  `android.lens.poseReference` — i.e. the relative geometry of the two lenses (the stereo baseline) is
  described in the camera characteristics.

## Resolutions

Rear sensor active array **4080 × 3072** (12.5 MP binned) with full-res **8160 × 6144** (50 MP)
available in the stream-configuration map. Stream configs also list 4080×2296 (16:9), 1920×1080, etc.

## Calibration

`/vendor/etc/camera/dual3d_cali_golden.bin` — the **dual-3D stereo calibration** ("golden") file:
per-unit factory calibration of the geometric/optical relationship between the two rear sensors, used
to rectify the left/right images for 3D.

## Capture pipeline (from `LCCamera` / `com.xreal.evapro.camera`)

The app captures both sensors simultaneously via the **Camera2 logical-multicamera physical-stream
API**:
- `com/android/camera/multi/MultiCameraModule.java` + `CaptureModule.java` use `setPhysicalCameraId` /
  `OutputConfiguration.setPhysicalCameraId` to request per-physical-sensor streams. Log strings:
  `"add output format=jpeg physicalId="`, `"add output format=yuv physicalId="`,
  `"add master full yuv for dual zone"`, `"add Aux full yuv for dual zone"`, `"buildPhysicalCamera ..."`.
- It computes/uses the **stereo baseline**: `"Baseline distance = %fmm"`.
- Spatial media nodes: `com.lc.node.spatialvideo.DualPrv` (dual preview), `com.lc.node.spatialvideo.
  PrivateData`. Vendor prop `vendor.debug.camera.spatialvideo.mode = 3`.
- Output containers: **HEIC / HEICS** (`image/heic`, `image/heics`, `.heic`, `.heics`) for spatial
  stills (the Apple-style spatial-photo container). Spatial video is encoded via XREAL's
  `libXrealSVVideo.so` (stereo video; MV-HEVC-class multiview encoding — inferred from lib name +
  spatial-video nodes).
- `"Can't find depth camera"` string suggests an optional depth path.

## Camera HAL

Qualcomm **CamX / CHI** proprietary userspace HAL. `/vendor/lib64/hw` contains:
- `camera.qcom.so`, `com.qti.chi.override.so` (CHI override — where dual-camera/stereo logic lives),
- sensor drivers `com.qti.sensor.imx318/334/362/386/519/577.so`, and eeprom drivers
  `com.qti.eeprom.*.so`. (Note: the S5KJN1/OV8856 drivers are loaded by the CamX sensor sub-module; the
  listed `imx*` are the HAL's available sensor library set, not necessarily all physically present.)
- Also present: `com.qti.sensor.max7366_6dof.so` and `com.qti.sensor.max7366_eyetrack.so` — sensor
  drivers for **glasses-side** 6DoF / eye-tracking cameras (part of the XR reference design), not the
  phone's own imaging.

## Feature toggles (props)

| Prop | Value | Meaning |
|---|---|---|
| `persist.sys.camera.usbcam.feature` | true | USB-camera support (for glasses cameras) |
| `persist.sys.camera.usbcam.packagelist` | `com.xreal.evapro.nebula` | Nebula is allowed USB-camera access |
| `persist.sys.camera.usbcam.switch` | false | — |
| `vendor.debug.camera.spatialvideo.mode` | 3 | Spatial (3D) video mode |
| `camera.disable_zsl_mode` | 1 | ZSL disabled |

## Why this doesn't port to Linux

The stereo path depends entirely on: the Camera2 logical-multicamera physical-stream API + hardware
sensor sync (Android + CamX), the `dual3d_cali_golden.bin` calibration, and XREAL's HEIC/MV-HEVC
spatial muxing. **S5KJN1 has no mainline V4L2 driver**, SM6450 "parrot" has no mainline CAMSS/libcamera
support, and the CamX HAL is Android-only. See [05](05-postmarketos-feasibility.md).
