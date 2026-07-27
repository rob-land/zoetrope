#!/bin/bash
# Install beamshell console mode (sway kiosk on VT8, udev-hotplug-triggered).
# Run as the normal user; uses sudo for system paths.
set -euo pipefail
cd "$(dirname "$0")"

sudo install -d /etc/beamshell /usr/local/libexec/beamshell
sudo install -m 0644 sway-kiosk.conf /etc/beamshell/sway-kiosk.conf
sudo install -m 0755 beamshell-kiosk.sh beamshell-vt /usr/local/libexec/beamshell/
sudo install -m 0644 beamshell-console.service /etc/systemd/system/beamshell-console.service
sudo install -m 0644 99-beamshell-console.rules /etc/udev/rules.d/99-beamshell-console.rules

sudo systemctl daemon-reload
sudo udevadm control --reload

# Arm hotplug autostart (rm this file to disable hotplug takeover).
sudo touch /etc/beamshell/console-autostart

# XRLinuxDriver head-tracking config: beamshell reads opentrack UDP on 127.0.0.1:4242.
# The driver's compiled-in default is disabled=true, so all three lines are required.
XR_CONF="${XDG_CONFIG_HOME:-$HOME/.config}/xr_driver/config.ini"
mkdir -p "$(dirname "$XR_CONF")"
touch "$XR_CONF"
for kv in "disabled=false" "output_mode=external_only" "external_mode=opentrack"; do
    k="${kv%%=*}"
    if grep -q "^${k}=" "$XR_CONF"; then
        sed -i "s|^${k}=.*|${kv}|" "$XR_CONF"
    else
        echo "$kv" >> "$XR_CONF"
    fi
done

echo "Installed. Manual test:  sudo systemctl start beamshell-console"
echo "Disable hotplug:         sudo rm /etc/beamshell/console-autostart"
