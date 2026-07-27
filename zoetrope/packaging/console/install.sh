#!/bin/bash
# Install zoetrope console mode (sway kiosk on VT8, udev-hotplug-triggered).
# Run as the normal user; uses sudo for system paths.
set -euo pipefail
cd "$(dirname "$0")"

sudo install -d /etc/zoetrope /usr/local/libexec/zoetrope
sudo install -m 0644 sway-kiosk.conf /etc/zoetrope/sway-kiosk.conf
sudo install -m 0755 zoetrope-kiosk.sh zoetrope-vt /usr/local/libexec/zoetrope/
sudo install -m 0644 zoetrope-console.service /etc/systemd/system/zoetrope-console.service
sudo install -m 0644 99-zoetrope-console.rules /etc/udev/rules.d/99-zoetrope-console.rules

sudo systemctl daemon-reload
sudo udevadm control --reload

# Arm hotplug autostart (rm this file to disable hotplug takeover).
sudo touch /etc/zoetrope/console-autostart

# XRLinuxDriver head-tracking config: zoetrope reads opentrack UDP on 127.0.0.1:4242.
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

echo "Installed. Manual test:  sudo systemctl start zoetrope-console"
echo "Disable hotplug:         sudo rm /etc/zoetrope/console-autostart"
