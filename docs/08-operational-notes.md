# 08 — Operational Notes (adb, tooling, capture procedures)

Practical notes for continuing this investigation.

---

## ⚠ Wireless adb is required when glasses are connected

**The USB-C port that carries adb is the same port the glasses plug into.** You cannot have wired adb
and the glasses connected at the same time on that port. (The Beam Pro has two USB-C ports, but the
glasses need the DP-Alt-Mode-capable port, and wired adb typically runs on the same one.)

To observe a live glasses session, use **wireless adb**:

```bash
# One-time, while still on USB:
adb tcpip 5555
# Find the device IP (Settings → About → Status, or):
adb shell ip -f inet addr show wlan0
# Then unplug USB, plug in the glasses, and connect over WiFi:
adb connect <device-ip>:5555
adb devices        # confirm "<ip>:5555   device"
```

Android 11+ also supports **Wireless debugging** with pairing codes (Developer Options → Wireless
debugging → Pair device with pairing code), which survives reboots better:

```bash
adb pair <device-ip>:<pair-port>       # enter the 6-digit code shown on device
adb connect <device-ip>:<connect-port>
```

Both device and host must be on the same network. Keep the screen awake or disable "turn off wireless
debugging when screen is off" if the connection drops.

---

## Tooling used

| Tool | Purpose | Notes |
|---|---|---|
| `adb` | Device shell, dumpsys, pull APKs | Device is non-root — many `/proc`, `/sys`, `/vendor` paths are SELinux-restricted |
| `apktool` | Decode manifest/resources + smali | `apktool d -s` = resources only (fast); `apktool d -r` = smali only |
| `jadx` | Java decompilation | Downloaded to scratchpad; `jadx --no-res -d out app.apk` |
| `unzip` | Inspect APK structure / list `.so` | — |

Decompiled artifacts (from the investigation session, under the scratchpad) — regenerate as needed:
- `nebula.apk` (813 MB) → `nebula_src` (smali), `nebula_jadx` (Java), `nebula_res` (manifest/resources)
- `lccamera.apk` (25 MB, `com.xreal.evapro.camera`) → `lccamera_full`
- `xrvdservice.apk`, `xrcbservice.apk` (Qualcomm QXR) → `xrvd`, `xrcb`

Pull the key APKs again with:
```bash
adb shell pm list packages -f | grep -iE 'xreal|xrvd|xrcb|LCCamera'
adb pull <path-from-above> ./name.apk
```

---

## Useful capture commands

### Baseline hardware
```bash
adb shell getprop | grep -Ei 'ro.product|ro.board|ro.soc|ro.hardware|fingerprint'
adb shell cat /proc/cpuinfo
adb shell dumpsys display        # DRM connectors, panel, external displays
adb shell dumpsys media.camera   # camera characteristics (stereo/logical multicam)
adb shell 'ls -l /dev/block/by-name/'   # partition layout
adb shell dumpsys sensorservice | grep -iE 'accel|gyro|mag|prox|light'
adb shell service list
```

### Glasses-connected capture (over wireless adb)
Run these *while plugging in* the One Pro (+ Eye):
```bash
# Live event stream — filter for glasses/eye/6dof/display:
adb shell "logcat -c && logcat" | grep -iE 'nebula|glass|eye_uvc|6dof|edid|3840|onepro|slam|plug|display'

# What USB devices enumerated (VID/PID, interfaces):
adb shell dumpsys usb                       # host state, ports, DP alt mode
adb shell 'ls -l /sys/bus/usb/devices/'     # may be SELinux-limited on non-root
adb shell 'for d in /sys/bus/usb/devices/*/; do
  echo -n "$d: "; cat $d/idVendor 2>/dev/null; cat $d/idProduct 2>/dev/null; done'

# External display that appeared:
adb shell 'cat /sys/class/drm/card0-DP-1/status'
adb shell 'cat /sys/class/drm/card0-DP-1/modes'
adb shell dumpsys display | grep -Ei '3840|1920|DP|external|state ON'
```

### To characterize the XREAL Eye (for a Monado driver)
Goal: exact UVC PID + supported formats/resolutions, and whether any 6DoF pose crosses to something
host-readable. On a Linux laptop with the Eye plugged in directly:
```bash
lsusb -v                         # find the Eye's VID:PID, UVC descriptors
v4l2-ctl --list-devices
v4l2-ctl -d /dev/videoN --list-formats-ext
```
On the Beam Pro (wireless adb), watch for `eye_uvc_start` in logcat and the `libnr_plugin_6dof` load to
confirm the tracking bring-up order.

---

## Gotchas / limits observed

- **Non-root restrictions:** `/proc/bus/input/devices`, `/proc/cmdline`, `/sys/class/extcon/*`,
  `/vendor/etc/vintf`, and UFS string descriptors returned empty/denied under the `shell` user. Use
  `getevent -pl`, `dumpsys`, and `service list` instead where possible.
- **QXR services are on-demand:** `com.qualcomm.qti.xrvd.service` / `xrcb` and the vendor
  `IQXR*`/`sxrauxd` do **not** appear in `service list`/`ps` until glasses are connected.
- **The 813 MB Nebula APK** is mostly Unity assets + native libs (QNN/Genie AI stacks, NRSDK). Only the
  3 `classes*.dex` (~22 MB) matter for logic; decompile with `-r` (smali) / jadx to skip resources.
- **Don't reboot to bootloader casually** — the device is locked; `fastboot` unlock wipes data. Only do
  it deliberately (see [05](05-postmarketos-feasibility.md)).
