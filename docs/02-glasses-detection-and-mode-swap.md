# 02 — Glasses Detection & Mode Swap (the "secret sauce")

How the Beam Pro notices that XREAL glasses were plugged in, launches a 3D spatial environment on the
glasses, and turns the phone into a touchpad.

Reverse-engineered from the decompiled Nebula app (`com.xreal.evapro.nebula`, decompiled with
`apktool` + `jadx`) plus on-device `dumpsys`/`service list`/SELinux contexts. Confirmed vs inferred is
flagged throughout.

---

## Architecture at a glance

There are **three software layers** on the device that can drive AR glasses:

1. **Nebula** (`com.xreal.evapro.nebula`) — the XREAL launcher app. Runs as
   `android:sharedUserId="android.uid.system"` (i.e. **system UID**), so it holds `INJECT_EVENTS`,
   `WRITE_SECURE_SETTINGS`, `MANAGE_USB`, `FORCE_STOP_PACKAGES`, etc. This is the orchestrator.
2. **XREAL NRSDK native stack** — bundled `.so` libraries (`libnr_api.so`, `libnr_service.so`,
   `libnr_plugin_6dof.so`, …) that talk to the glasses over USB and composite the stereo image to the
   DisplayPort output. **This is the path Nebula actually uses.**
3. **Qualcomm QXR framework** (`com.qualcomm.qti.xrvd.service`, `com.qualcomm.qti.xrcb`, vendor
   `vendor.qti.hardware.qxr.IQXR*` HALs, `sxrauxd` daemon) — Qualcomm's generic Snapdragon-XR
   companion-glasses framework. **Present in firmware but NOT the path Nebula's Beam Pro launcher
   uses** (it's a generic capability; see the "QXR" section below).

---

## Step 1 — Detection (dual-signal)

Two independent detectors run, both funneling into `GlassesInitSetting` → `GlassesManager`.

### (a) USB device attach

XREAL glasses enumerate as a USB device with **vendor id `0x3318` (13080 decimal)** — XREAL/Nreal's
registered USB VID — and a model-specific product id in the range `0x423`–`0x442`.

- Nebula's `SplashActivity` declares an intent-filter for `android.hardware.usb.action.USB_DEVICE_ATTACHED`
  with `meta-data android.hardware.usb.action.USB_DEVICE_ATTACHED = @xml/glasses_device_filter_not_ella`.
  That resource lists every XREAL VID/PID. So the OS's normal **USB-device-to-app association**
  auto-launches Nebula when glasses are plugged in. (Confirmed — manifest + resource XML.)
- At runtime, `com.xreal.glassesdisplayplugevent.receiver.UsbAttachDetachReceiver` handles
  `USB_DEVICE_ATTACHED`/`USB_DEVICE_DETACHED` and forwards to `UsbAttachDetachHelper.onReceive()`, which
  classifies the device via `GlassesTypeUtil.checkGlassesType(usbDevice)` and, on a match, fires
  `IUsbPlugEvent.onPlugIn(glassesType)` to listeners.

### (b) DisplayPort external-display appearance

The glasses also assert **DisplayPort Alt Mode** on the USB-C link, so an external display appears on
DRM connector `card0-DP-1`.

- `com.xreal.glassesdisplayplugevent.display.DisplayObserverHelper` registers a display listener and
  enumerates existing `PRESENTATION`-category displays at startup.
- The concrete listener is product-specific (`display/observers/BaseDisplay.java`): on the Beam Pro
  (`Build.PRODUCT == "eva"`) it uses `EvaDisplay`, which registers a **custom framework listener**
  `DisplayManager.Display3566Listener` with extra callbacks `onDisplay3566Added(int)` /
  `onDisplay3566Removed(int)`. This is **not** a stock AOSP API — XREAL patched `DisplayManager` in the
  framework. Other products fall back to a stock `DisplayManager.DisplayListener`.
- A newly added display is positively identified as glasses in `DisplayModel`:
  - `isHdmi()` — on `"eva"` reflectively calls the custom `Display.isRealDisplayConnected()`; elsewhere
    matches `display.getName()` containing `"XREAL"`/`"Air"`/`"HDMI"` or the `FLAG_PRESENTATION` flag.
  - `isNrealDisplay()` reads the display's `DeviceProductInfo` (from **EDID**) and calls
    `_equalsPidVid(name, productId, manufacturerPnpId)`.
  - `_equalsPidVid()` matches the EDID **manufacturer PnP id** against `"MRG"` (new glasses) or `"NRL"`
    (old "Nreal Light"), and the EDID **product-id** against `USBVendorProductID.sDisplayPidMap`.

So detection = **USB VID/PID match AND/OR EDID product match**. The USB path drives SDK bring-up; the
display path confirms the glasses screen actually appeared (and, on removal, triggers the fall back to
2D — `GlassesManager.onDisplayRemove()` reports `onHardwareTo2D()` when the 3840×1080 glasses display
goes away).

---

## Step 2 — Bring-up (grab the glasses' USB interfaces + start NRSDK)

On a confirmed plug-in (`GlassesManager.onPlugIn` → `startGlasses(...)` → `XREALManager`), Nebula:

1. Requests permission for the glasses' individual **USB interfaces** via five custom actions handled
   by `ai.nreal.glasses.control.permission`:
   `GRANT_USB_HID`, `GRANT_USB_TTY`, `GRANT_USB_AUDIO`, `GRANT_USB_OV580`, `GRANT_USB_RGB`.
   (Detail of what each interface is in [03](03-usb-protocol-and-glasses-models.md).)
2. Opens each interface via `UsbManager.openDevice()` → `UsbDeviceConnection.getFileDescriptor()` and
   hands the **file descriptor to native** (`libota-lib.so` / `libnr_libusb.so`). Note: it does **not**
   open `/dev/tty*` — the "TTY"/serial control channel is raw USB.
3. Starts the native SDK: `NRServiceControl.startBackgroundSdk(...)` (loads `libnr_service.so`, which is
   backed by `libnr_api.so`). This begins IMU read (`nativeImuInit`), tracking, and — with cameras —
   6DoF/SLAM.

---

## Step 3 — The mode swap (switch the glasses display into 3D and composite to it)

This is the important correction to the "obvious" guess: **the launcher activity is NOT routed onto the
glasses display.** Instead:

1. `NRServiceControl.set2D3D(edidIndex)` reconfigures the **physical DisplayPort output** of the
   glasses:
   ```
   if (isEthernetSeries) {                 // One / One Pro / 1S (types 6–9)
       nativeSetDpCurrentEdid(i);
       nativeSetDpInputMode( (i in {5,6,7,8}) ? 1 : 0 );   // 1 = side-by-side / 3D
   } else {                                // Air series (types 2–5)
       nativeSet2D3DMode(i);
   }
   ```
   For the DP/"Ethernet/G" series it selects a stereo **EDID** and toggles **side-by-side 3D input
   mode**; for the Air series it uses the equivalent `nativeSet2D3DMode`. The EDID it picks comes from
   `getFinalDisplayConfig()` (user prefs `displayMonoScreen` default 10, `displayStereoScreen` default
   4; G-series is forced to index **5** = `NR_EDID_3840_1080_60`).
2. Switching the EDID makes the OS **drop and re-add** the external display, now at **3840×1080@60**.
   The re-enumeration re-fires the display listener.
3. The **XREAL NRSDK native compositor** (inside `libnr_api.so`/`libnr_service.so`) renders the stereo
   3D scene directly to that DisplayPort framebuffer. (Confirmed: the DP EDID/mode switch is in code;
   the exact native surface handoff to the DP framebuffer lives in the un-decompiled `.so` and is
   **inferred**.)
4. Meanwhile the **Unity launcher** (`ai.nreal.nebula.space.LaunchSpaceAcrivity`, its own `:space`
   process, translucent portrait theme) is launched on **phone display 0** — confirmed by
   `ActivityOptions.makeBasic().setLaunchDisplayId(0)` in `NRXRApp.startUnityActivityInternal()`. It is
   a plain `startActivity` with flags `402653184`, **no `setLaunchDisplayId(externalId)`**. The Unity
   app is the "brain" running on the phone SoC; head pose comes from the glasses IMU via native.

So: the glasses show a native-composited stereo scene; the phone runs the Unity launcher logic; the two
are joined by the NRSDK.

---

## Step 4 — Phone becomes a touchpad

- Nebula displays a virtual-controller fragment on the phone: `ai.nreal.extension.virtualcontroller.
  TouchPadPortraitFragment` / `TouchPadLandscapeFragment` / `AirMouseFragment`, hosted by
  `UltraVirtualControllerFragment` (which is just a **container** that swaps in the right page — it is
  **not** a 6DoF/IMU controller; grep for `SensorManager`/`SensorEvent`/`ROTATION_VECTOR` in that
  package returns zero hits).
- Each fragment installs an `OnTouchListener` and converts touches to Y-flipped, clamped `[-1,1]`
  coordinates:
  ```
  float x = ((event.getX(i)/width)  * 2f) - 1f;
  float y = 1f - ((event.getY(i)/height) * 2f);
  systemButtonDataReceiver.FillTouchpadInput(action, index, pointerIds, padTouchX, padTouchY);
  ```
- The data leaves Java **only** through the callback interface
  `ai.nreal.extension.virtualcontroller.ISystemButtonDataReceiver` (methods `FillTouchpadInput`,
  `FillHomeButtonInput`, `FillBackButtonInput`, `FillScreenUnlockInput`). **No Java class implements
  that interface** — the implementer is a Unity **C# `AndroidJavaProxy`** passed into
  `RegisterFragment(activity, receiver, theme)`. So the touchpad pushes normalized pointer data across
  JNI into the Unity `:space` engine, which moves the on-glasses cursor. (The final native hop is
  inferred.)
- There is **no `injectInputEvent`, socket, or `/dev` write** in the touchpad package — it's pure input
  capture → JNI.

---

## The privilege layer

- Nebula's own `ai.nreal.nebula.service.PrivilegeManager` / `BasePrivilegeManager` **does** perform
  privileged input injection, but via the **standard reflected `input` service**:
  `IInputManager$Stub.asInterface(ServiceManager.getService("input"))`, then
  `injectInputEvent(InputEvent, 0)` after `setDisplayId(...)`. It works only because Nebula is system
  UID with `INJECT_EVENTS`. This path is used to inject events into **mirrored 2D-app VirtualDisplays**
  (floating Android app panels in the space), **not** the main touchpad.
- A separate **platform** service `semprivilege` (interface `com.nreal.android.privilege.
  IPrivilegeManager`) exists — confirmed in the device's SELinux `plat_service_contexts`
  (`semprivilege u:object_r:semprivilege_service:s0`), i.e. baked into `system_server`, not an app.
  **Nebula never calls it** (grep of the whole APK for `semprivilege`/`IPrivilegeManager` = zero hits).
  It's a platform capability that other XREAL system components could use.
- Other privileged ops Nebula does directly (as system UID): force-stop packages
  (`ActivityManager.forceStopPackage` / `am force-stop`), secure/global settings writes, trusted
  `VirtualDisplay` creation.

---

## The Qualcomm QXR framework (present, but not Nebula's launcher path)

The firmware also ships Qualcomm's Snapdragon-XR companion framework. Documented here because it's on
the device and is the mechanism a *generic* Qualcomm AR-glasses app would use:

- **`XRVD` — XR Virtual Display** (`com.qualcomm.qti.xrvd.service.XRVD`, system UID, holds
  `INJECT_EVENTS` + `INTERNAL_SYSTEM_WINDOW`). Binder interface `XRVDInterface` with:
  `createXRVirtualDisplay`, `setSurfaceXRVirtualDisplay`, `resizeXRVirtualDisplay`,
  `startActivityOnXRVirtualDisplay(id, intent)`, `setCurrentXRVirtualDisplay`, and
  `injectMotionEvent`/`injectKeyEvent`. Talks to the native compositor over a "**Mink**" socket
  (`XRVDMinkSocketOpener`). Has an `XRVDAccessibilityService`.
- **`XRCB` — QXR bridge** (`com.qualcomm.qti.xrcb`) with services `XRCBCore/Cam/Split/SplitRVR/Mod/Comm`,
  protected by `QXRServiceClientPermission`. It opens USB FDs and passes them (`setFd()`) to the vendor
  HALs `vendor.qti.hardware.qxr.IQXR{Core,Cam,Split,SplitRVR,Mod,Comm,Audio}Service` and the native
  `sxrauxd` ("Snapdragon XR aux daemon"). `IQXRSplitService`/`SplitRVR` do split/stereo rendering
  (render on the phone SoC, reproject per-eye frames to the glasses).

These services only register/run when glasses are attached (they were not in `service list`/`ps` while
the glasses were unplugged). The decompiled Nebula Beam Pro path uses the **XREAL NRSDK** rather than
XRVD; XRVD may be used for other products or other modes.

---

## End-to-end sequence (corrected)

```
Glasses plugged into USB-C
  ├─ USB device (VID 0x3318, PID 0x4xx) enumerates ──► USB_DEVICE_ATTACHED
  │      └─ matches Nebula SplashActivity glasses_device_filter ──► Nebula auto-launches
  └─ DisplayPort Alt Mode ──► external display on card0-DP-1
         └─ Display3566Listener + DisplayModel confirm via EDID PnP "MRG"/"NRL" + product-id
  ↓
GlassesTypeUtil / USBVendorProductID classify model type (e.g. One Pro = type 6)
  ↓
Grant glasses USB interfaces (HID/TTY/AUDIO/OV580/RGB) → hand FDs to native
  ↓
NRServiceControl.startBackgroundSdk()  → libnr_service.so / libnr_api.so  → IMU + tracking start
  ↓
set2D3D(edidIndex):  nativeSetDpCurrentEdid + nativeSetDpInputMode(1)  (→ 3840×1080 SBS 3D)
  ↓
DP display re-enumerates at 3840×1080  → NRSDK native compositor renders stereo scene to it
  ↓
goLauncher(): Unity LaunchSpaceAcrivity starts on PHONE display 0 (the "brain")
  ↓
Phone shows TouchPad*Fragment  → normalized [-1,1] touches cross JNI into Unity → on-glasses cursor
```

## Why this can't be reproduced by an ordinary app

It requires (a) the platform signature / `android.uid.system` sharedUserId, (b) the XREAL NRSDK native
libraries (which live in the system image and are Android/arm64-only), and (c) the glasses' USB
protocol. See [07](07-linux-3d-shell-plan.md) for what a non-XREAL host *can* do instead.
