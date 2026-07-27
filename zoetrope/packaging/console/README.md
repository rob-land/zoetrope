# zoetrope console mode

Runs zoetrope in a **dedicated sway kiosk session on VT8**, outside GNOME, triggered
by plugging in XREAL glasses. This sidesteps Mutter entirely: sway is DRM master on
its VT, so fullscreen-on-output, output modes, and direct scanout all work — the
suspected cause of the glasses-black-screen problem under GNOME/Mutter Wayland.
GNOME keeps running on tty2 (suspended, not killed); unplugging the glasses (or the
shell exiting) switches back automatically.

## Files

| File | Installs to | Role |
|---|---|---|
| `99-zoetrope-console.rules` | `/etc/udev/rules.d/` | start unit on glasses plug (USB 0x3318, PIDs 0x0423–0x0442), stop on unplug |
| `zoetrope-console.service` | `/etc/systemd/system/` | logind session on `/dev/tty8` as `rob` (`PAMName=login`), runs sway; saves/restores the previous VT |
| `sway-kiosk.conf` | `/etc/zoetrope/` | kiosk sway config; execs the launcher |
| `zoetrope-kiosk.sh` | `/usr/local/libexec/zoetrope/` | supervise loop inside sway: waits up to 12 s for the XREAL output (DP link is slow on hotplug), sets 3840×1080@60 if advertised, disables eDP, runs zoetrope; **relaunches zoetrope when the display changes** (e.g. the glasses' on-board 2D↔3D toggle re-EDIDs — zoetrope comes back in the matching stereo mode ~5 s later); output gone >8 s or zoetrope exit → session ends; no glasses at all → preview mode on eDP |
| `zoetrope-vt` | `/usr/local/libexec/zoetrope/` | root helper: chvt to 8 / restore previous VT |

Install/update everything: `./install.sh` (idempotent).

## Controls

- **Hotplug arm/disarm:** `sudo touch|rm /etc/zoetrope/console-autostart`
  (the unit's `ConditionPathExists`; disarmed = plugging glasses does nothing).
- **Manual run (works without glasses — preview on laptop panel):**
  `sudo systemctl start|stop zoetrope-console`
- **Escape hatches from inside the kiosk:** Esc quits zoetrope (ends the session),
  `Ctrl+Alt+q` exits sway, `Ctrl+Alt+F2` switches back to GNOME's VT manually.
- **Logs:** lifecycle via `journalctl -u zoetrope-console`; the kiosk/zoetrope
  output lands in the PAM *session scope*, not the unit — find it with
  `sudo journalctl -b -g 'zoetrope-kiosk|\[run\]'`.
- Extra zoetrope args / media dir: put `ZOETROPE_EXTRA_ARGS="..."` (e.g.
  `--media /path --stereo sbs`) in `/etc/zoetrope/console.conf`.

## Verified (2026-07-16)

- **With glasses:** hotplug start works and the glasses render zoetrope's UI —
  the GNOME/Mutter black-screen problem does not occur under the VT kiosk.
- Nested sway test: kiosk script falls back to preview, zoetrope renders.
- VT round trip: unit start → chvt tty2→tty8, sway + zoetrope fullscreen on eDP-1
  (confirmed via sway IPC get_tree), stop → back on tty2, GNOME session intact,
  no leaked processes or tty8 sessions after stop.
- `udevadm verify` passes on the rule; unit passes `systemd-analyze verify`.

## Unplug / teardown design (learned the hard way)

Three redundant layers end the session on unplug, because each alone proved flaky:
1. udev remove rule → `systemctl stop`. Matches kernel-provided `ENV{PRODUCT}`
   ("3318/436/…"), NOT `ID_VENDOR_ID`/`ID_MODEL_ID` (udev-DB props, unreliable on
   remove — the original rule never fired).
2. Kiosk watcher: polls sway outputs every 2 s; XREAL output gone → `swaymsg exit`.
3. `zoetrope-vt restore` (ExecStopPost): `PAMName=login` moves the session's
   processes into a logind session scope, OUTSIDE the service cgroup — plain unit
   stop kills only sway (MainPID) and leaks the rest. The helper cgroup.kill's every
   session on tty8, then restores the previous VT.

## To verify with glasses plugged in (DP on the laptop's USB-C)

1. `sudo journalctl -fu zoetrope-console` in a terminal first (or check after).
2. Plug in the One Pro → screen should switch to VT8; glasses should show the
   zoetrope grid + tiles (the GNOME black-screen suspect test). Laptop panel goes dark.
3. In the journal: `zoetrope-kiosk: glasses output DP-? (sbs_mode_present=0|1)`.
   `sbs_mode_present=1` would mean the 3840×1080 mode exists (glasses already in 3D
   — normally 0 until the mode-switch problem is solved separately).
4. Unplug → back to GNOME on tty2.
5. If the glasses are ever switched into 3D (on-board menu / RE'd USB command), the
   kiosk picks 3840×1080@60 automatically and zoetrope's `--stereo auto` goes SBS.

## Known limitations

- If zoetrope exits while glasses stay plugged (Esc), the session ends and won't
  restart until replug (or `systemctl start`).
- `User=rob` and the zoetrope path are hardcoded in the unit/launcher.
- The udev PID match must stay range-limited: the Beam Pro phone's own USB gadget is
  also VID 0x3318 (PID 0x0528).
