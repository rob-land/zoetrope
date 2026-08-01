#!/bin/bash
# Runs INSIDE the kiosk sway session (exec'd from sway-kiosk.conf).
# Lifecycle:
#   - wait for the XREAL DP output (link training + EDID can take seconds on hotplug)
#   - configure outputs (SBS mode if advertised), run zoetrope
#   - poll outputs every 2s:
#       glasses output gone >8s          -> end session (udev remove is the fast path)
#       output/mode changed (2D<->3D)    -> relaunch zoetrope to match (covers the
#                                           glasses' on-board 3D toggle re-EDID)
#       glasses appeared during preview  -> relaunch in glasses mode
#   - zoetrope exits by itself (Esc)    -> end session

ZOETROPE_DIR=/home/rob/projects/beampro/zoetrope
[ -r /etc/zoetrope/console.conf ] && . /etc/zoetrope/console.conf

# For altmode_failed: the alt-mode timeout fires ~200 ms after the USB plug,
# but this script starts seconds later (udev -> service settle sleep -> sway
# boot) — so look back far enough to cover that gap, not just from script
# start (which reliably missed it).
START_TS=$(date '+%Y-%m-%d %H:%M:%S' -d '10 seconds ago')

outputs_json() { swaymsg -t get_outputs -r 2>/dev/null; }

detect() {
    # Sets DET_OUT (output name, "-" if none), DET_SBS (1 if a 3840x1080 mode
    # exists) and DET_IPC (0 when sway's IPC is unreachable, i.e. sway died).
    local json
    DET_IPC=1
    json=$(outputs_json) || { DET_OUT=-; DET_SBS=0; DET_IPC=0; return; }
    read -r DET_OUT DET_SBS <<< "$(printf '%s' "$json" | python3 -c '
import json, sys
outs = json.load(sys.stdin) if not sys.stdin.isatty() else []
name, sbs = "-", 0
for o in outs or []:
    ident = " ".join(str(o.get(k, "")) for k in ("make", "model", "name")).upper()
    if any(t in ident for t in ("MRG", "NRL", "XREAL", "NREAL")):
        name = o["name"]
        sbs = int(any(m.get("width") == 3840 and m.get("height") == 1080
                      for m in o.get("modes", [])))
        break
print(name, sbs)
' 2>/dev/null || echo '- 0')"
    [ -n "$DET_OUT" ] || DET_OUT=-
}

altmode_failed() {
    # amdgpu logs this when the USB-C DP alt-mode handshake fails; the kernel
    # does not retry on its own, so the DP output will never appear — only a
    # replug renegotiates. (Journal read needs wheel/adm/systemd-journal.)
    journalctl -k -b --since "$START_TS" --no-pager -q 2>/dev/null |
        grep -q 'Alt mode has timed out'
}

STATUS_NAG=
status_nag() {
    # One persistent status bar on the laptop panel (replaced on relaunch).
    [ -n "$STATUS_NAG" ] && kill "$STATUS_NAG" 2>/dev/null
    swaynag -o eDP-1 -e top -y overlay -m "$1" >/dev/null 2>&1 &
    STATUS_NAG=$!
}

DP_FAIL_NAGGED=0
nag_dp_failed() {
    [ "$DP_FAIL_NAGGED" = 1 ] && return
    DP_FAIL_NAGGED=1
    echo "zoetrope-kiosk: USB-C DP alt mode timed out — glasses display cannot appear; replug needed"
    swaynag -t warning \
        -m 'Glasses DP link failed (USB-C alt mode timed out). Unplug, wait ~15 s for the glasses to power down, then replug.' \
        >/dev/null 2>&1 &
}

glasses_usb_present() {
    # XREAL glasses on the USB bus: VID 0x3318, glasses-range PID (0x0423-0x0442).
    local d v p
    for d in /sys/bus/usb/devices/*/idVendor; do
        read -r v < "$d" 2>/dev/null || continue
        [ "$v" = "3318" ] || continue
        read -r p < "${d%idVendor}idProduct" 2>/dev/null || continue
        case "$p" in
            042?|043?|044[0-2]) return 0 ;;
        esac
    done
    return 1
}

# Wait for sway IPC.
for _ in $(seq 1 50); do outputs_json >/dev/null && break; sleep 0.2; done

# Wait for the glasses DP output. While the glasses are physically on USB, do NOT
# fall back to preview — the DP link/EDID can lag the USB attach by several seconds
# (this was the "zoetrope on the laptop panel" bug). Preview is only for a start
# with no glasses plugged at all.
WAITED=0
while :; do
    detect
    [ "$DET_OUT" != "-" ] && break
    if glasses_usb_present; then
        LIMIT=120   # half-second ticks
        if [ "$WAITED" -ge 4 ] && altmode_failed; then
            # The DP output will never appear this session; tell the user and
            # stop sitting on a dark screen for the full 60 s.
            nag_dp_failed
            LIMIT=20
        fi
    else
        LIMIT=10
    fi
    if [ "$WAITED" -ge "$LIMIT" ]; then
        [ "$LIMIT" = 120 ] && echo "zoetrope-kiosk: glasses on USB but no DP output after 60s!"
        break
    fi
    sleep 0.5; WAITED=$((WAITED + 1))
done

while :; do
    detect
    CUR_OUT=$DET_OUT CUR_SBS=$DET_SBS
    if [ "$CUR_OUT" != "-" ]; then
        echo "zoetrope-kiosk: glasses output $CUR_OUT (sbs_mode_present=$CUR_SBS)"
        [ "$CUR_SBS" = 1 ] && swaymsg output "$CUR_OUT" mode 3840x1080@60Hz
        swaymsg output "$CUR_OUT" enable
        # Keep the laptop panel alive with a status bar. It used to be
        # disabled here, but a black laptop made a healthy glasses
        # session indistinguishable from a dead one — which invited
        # unplugging the glasses just to check on the machine.
        swaymsg output eDP-1 enable
        status_nag "zoetrope is running on the glasses ($CUR_OUT). Ctrl+Alt+F2 = back to GNOME (session keeps running) - unplug the glasses to end it."
        ARGS="run --mode glasses"
    else
        echo "zoetrope-kiosk: no XREAL output — preview mode on laptop panel"
        swaymsg output eDP-1 enable
        [ -n "$STATUS_NAG" ] && kill "$STATUS_NAG" 2>/dev/null && STATUS_NAG=
        ARGS="run --mode preview --sway"
    fi

    cd "$ZOETROPE_DIR" || exit 1
    PYTHONUNBUFFERED=1 python3 -m zoetrope $ARGS ${ZOETROPE_EXTRA_ARGS:-} &
    BS=$!

    RELAUNCH=0 MISS=0 IPCMISS=0
    while kill -0 "$BS" 2>/dev/null; do
        sleep 2
        detect
        if [ "$DET_IPC" = 0 ]; then
            # sway itself is gone — nothing to supervise for; tear down.
            IPCMISS=$((IPCMISS + 1))
            if [ "$IPCMISS" -ge 2 ]; then
                echo "zoetrope-kiosk: sway IPC gone — exiting"
                kill "$BS" 2>/dev/null; wait "$BS" 2>/dev/null
                exit 1
            fi
            continue
        fi
        IPCMISS=0
        if [ "$CUR_OUT" != "-" ] && [ "$DET_OUT" = "-" ]; then
            # Gone: unplug — or a brief dropout while the glasses swap EDIDs (2D<->3D).
            MISS=$((MISS + 1))
            if [ "$MISS" -ge 4 ]; then
                echo "zoetrope-kiosk: glasses output gone — ending session"
                kill "$BS" 2>/dev/null; wait "$BS" 2>/dev/null
                swaymsg exit
                exit 0
            fi
        else
            MISS=0
            if [ "$DET_OUT" != "$CUR_OUT" ] || [ "$DET_SBS" != "$CUR_SBS" ]; then
                echo "zoetrope-kiosk: display changed ($CUR_OUT sbs=$CUR_SBS -> $DET_OUT sbs=$DET_SBS) — relaunching"
                RELAUNCH=1
                kill "$BS" 2>/dev/null; wait "$BS" 2>/dev/null
                break
            fi
        fi
    done

    if [ "$RELAUNCH" != 1 ]; then
        wait "$BS" 2>/dev/null
        echo "zoetrope-kiosk: zoetrope exited rc=$? — ending session"
        swaymsg exit
        exit 0
    fi
done
