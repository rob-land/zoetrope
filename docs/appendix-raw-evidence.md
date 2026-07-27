# Appendix — Raw Evidence

Verbatim (lightly trimmed) captures from the device, for reference. Collected 2026-07-09 over `adb`
(non-root). Firmware `X4000_X502_260518_ROW`.

---

## Device identity (`getprop`, excerpt)

```
[ro.product.manufacturer]: [XREAL]
[ro.product.model]: [X4000]
[ro.product.device]: [X4000]
[ro.product.board]: [parrot]
[ro.board.platform]: [parrot]
[ro.boot.hardware]: [qcom]
[ro.soc.manufacturer]: [QTI]
[ro.soc.model]: [SM6450]
[ro.hardware.egl]: [adreno]
[ro.hardware.vulkan]: [adreno]
[ro.build.fingerprint]: [XREAL/X4000/X4000:14/UKQ1.231222.001/X4000_X502_260518_ROW:user/release-keys]
[ro.build.description]: [X4000-user 14 UKQ1.231222.001 X4000_X502_260518_ROW release-keys]
[ro.product.build.date]: [Mon May 18 09:26:19 CST 2026]
[ro.product.ota.model]: [XREAL_X4000_ROW]
[ro.product.cpu.abi]: [arm64-v8a]
[ro.product.cpu.abilist]: [arm64-v8a,armeabi-v7a,armeabi]
[ro.board.first_api_level]: [31]
[ro.product.first_api_level]: [34]
[dalvik.vm.isa.arm64.variant]: [kryo300]
[ro.treble.enabled]: [true]
[ro.product.ab_ota_partitions]: [product,system,system_ext,vbmeta_system]
```

## Kernel

```
Linux localhost 5.10.240-android12-9-g10cb5814f5f0-ab467 #1 SMP PREEMPT Tue Mar 31 09:07:12 UTC 2026 aarch64 Toybox
```

## CPU (`/proc/cpuinfo`, part ids)

- CPUs 0–3: `CPU part 0xd05` (Cortex-A55), variant `0x2`
- CPUs 4–7: `CPU part 0xd41` (Cortex-A78), variant `0x1`
- Features: `fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp`

## GPU

```
/sys/class/kgsl/kgsl-3d0/gpu_model  ->  Adreno710v1
```

## Boot / verified boot

```
[ro.boot.flash.locked]: [1]
[ro.boot.secureboot]: [1]
[ro.boot.vbmeta.device_state]: [locked]
[ro.boot.verifiedbootstate]: [green]
[ro.boot.vbmeta.avb_version]: [1.0]
[ro.boot.vbmeta.hash_alg]: [sha256]
[ro.secure]: [1]
[ro.debuggable]: [0]
[sys.oem_unlock_allowed]: [0]
[ro.boot.slot_suffix]: [_a]
[ro.build.ab_update]: [true]
```

## DRM connectors (`/sys/class/drm`)

```
card0            card0-DP-1        card0-DSI-1       card0-Virtual-1
renderD128       sde-crtc-0        sde-crtc-1        sde-crtc-2
```
- `card0-DSI-1` = internal 1080×2400 panel.
- `card0-DP-1` = DisplayPort (glasses via USB-C DP Alt Mode).

## Internal display (`dumpsys display`, excerpt)

```
DisplayDeviceInfo{"Built-in Screen": 1080 x 2400, 60.000004 Hz, density 480,
  403.411 x 406.4 dpi, type INTERNAL, deviceProductInfo{manufacturerPnpId=QCM},
  roundedCorners radius=60, FLAG_SECURE FLAG_SUPPORTS_PROTECTED_BUFFERS FLAG_TRUSTED}
mLightSensor = stk_stk3a5x Ambient Light Sensor (sensortek)
```

## Sensors (`dumpsys sensorservice`, excerpt)

```
icm4x6xx Accelerometer            | TDK-Invensense
icm4x6xx Gyroscope                | TDK-Invensense
icm4x6xx Accelerometer/Gyro Uncalibrated | TDK-Invensense
mmc56x3x Magnetometer             | memsic
stk_stk3a5x Ambient Light Sensor  | sensortek
stk_stk3a5x Proximity Sensor      | sensortek
(SMTC SAR Sensor CH0..CH4         | Semtech, via getevent)
```

## Input devices (`getevent -pl`)

```
ILITEK_TDDI              (touchscreen)
parrot-qrd-sku1-snd-card Button Jack / Headset Jack
SMTC SAR Sensor CH0..CH4
pmic_resin / pmic_pwrkey / gpio-keys
ant_check-input / ant_div_check-input / meta_event
```
Sound card `parrot-qrd-sku1-snd-card` confirms Qualcomm QRD "parrot" SKU1 reference design.

## Cameras (`dumpsys media.camera` + vendor props)

```
[vendor.debug.camera.sensorinfo.main]:  [s5kjn1_ofilm_main]   (Samsung S5KJN1, 50MP)
[vendor.debug.camera.sensorinfo.aux]:   [s5kjn1_ofilm_aux]    (Samsung S5KJN1, 50MP)
[vendor.debug.camera.sensorinfo.front]: [ov8856_lce_front]    (OmniVision OV8856, 8MP)
[vendor.debug.camera.spatialvideo.mode]:[3]
[persist.sys.camera.usbcam.feature]:    [true]
[persist.sys.camera.usbcam.packagelist]:[com.xreal.evapro.nebula]

Rear logical multi-camera:
  Resource cost: 66   (vs 33 single)   Facing: Back
  android.logicalMultiCamera.physicalIds = byte[4]
  android.logicalMultiCamera.sensorSyncType present
  Capabilities: LOGICAL_MULTI_CAMERA RAW MANUAL_SENSOR BURST_CAPTURE YUV/PRIVATE_REPROCESSING ...
  android.lens.poseTranslation float[3], poseRotation float[4], distortion float[5]
  Stream config: 8160x6144 (50MP), 4080x3072, 4080x2296, 1920x1080, ...

/vendor/etc/camera/dual3d_cali_golden.bin   (stereo calibration)
/vendor/lib64/hw: camera.qcom.so, com.qti.chi.override.so, com.qti.sensor.*.so, com.qti.eeprom.*.so,
                  com.qti.sensor.max7366_6dof.so, com.qti.sensor.max7366_eyetrack.so
```

## Partitions (`/dev/block/by-name`, A/B, UFS LUNs sda–sdf; excerpt)

```
abl_a/b  aop_a/b  aop_config_a/b  apdp/apdpb  bluetooth_a/b  boot_a/b  cdt  connsec
cpucp_a/b  ddr  devcfg_a/b  devinfo  dip  dsp_a/b  dtbo_a/b  featenabler_a/b  frp  fsc/fsg
hyp_a/b  imagefv_a/b  keymaster_a/b  keystore  limits  logdump/logfs  mdtp*_a/b  metadata
misc  modem_a/b  modemst1/2  multiimg{oem,qti}_a/b  oemowninfo  persist  qupfw_a/b
recovery_a/b  rtice  secdata  ...  (super: product/system/system_ext/vbmeta_system)
```

## Service list (XREAL / XR-relevant, `service list`)

```
188  semprivilege: [com.nreal.android.privilege.IPrivilegeManager]     (platform system service)
239  virtualdevice: [android.companion.virtual.IVirtualDeviceManager]
 79  display / 80 display.smomoservice / 83 dpmservice
236  vendor.qti.hardware.display.config.IDisplayConfig/default
```
SELinux: `plat_service_contexts` contains `semprivilege  u:object_r:semprivilege_service:s0`.

QXR services (`com.qualcomm.qti.xrvd.service`, `com.qualcomm.qti.xrcb`) are installed but only register
when glasses are connected.

## USB event log (`dumpsys usb`, excerpt) — dual-port hints + water intent

```
SUBSYSTEM=usb1_hint  DEVPATH=/devices/virtual/usb1_hint/port_1  PORT1=CHARGING
SUBSYSTEM=usb2_hint  DEVPATH=/devices/virtual/usb2_hint/port_2  PORT2=CONNECTED/CONFIGURED/DISCONNECTED
USB intent: Intent { act=com.xreal.water.ACTION_WATER_PORT ... }
ports: current_mode=none can_change_mode=true ; current_mode=ufp can_change_mode=true
```

## USB device filter (`res/xml/glasses_device_filter_not_ella.xml`, excerpt)

```xml
<usb-device product-id="0x423" vendor-id="13080" />   <!-- 13080 = 0x3318 = XREAL -->
<usb-device product-id="0x424" vendor-id="13080" />
<usb-device product-id="0x425" vendor-id="13080" />   <!-- ... 0x423..0x442 ... -->
<usb-device product-id="0x435" vendor-id="13080" />   <!-- One Pro -->
<usb-device product-id="0x436" vendor-id="13080" />
<usb-device product-id="0x109b" vendor-id="0x6002" /> <!-- custom/Vidda -->
<usb-device product-id="0x109b" vendor-id="0x6003" />
```
The full `glasses_device_filter.xml` additionally lists STM32 CDC `0x0483:0x5740`, OmniVision `0x05A9`,
and Realtek `0x0BDA` (the composite "Ella" glasses).

## RAM / storage

```
MemTotal:        7660940 kB          (8 GB)
/data available: ~211 GB             (UFS ~256 GB class)
```
