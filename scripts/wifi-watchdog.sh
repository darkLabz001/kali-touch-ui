#!/usr/bin/env bash
# Kali Touch UI — WiFi reconnect + power-save watchdog.
#
# Keeps the preferred WiFi (the NM connection with the highest autoconnect
# priority) connected. Runs from wifi-watchdog.timer every ~20s and exits fast
# when already connected, so it is safe to run that often.
#
# Priority ordering example (device):
#   iPhone   autoconnect-priority=300   (hotspot — try first when present)
#   WentzATT autoconnect-priority=200   (fallback LAN)
set -u

IFACE=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')
[ -n "$IFACE" ] || exit 0

# Keep radios free of power-save micro-dropouts.
for phy in /sys/class/ieee80211/*; do :; done
iw dev "$IFACE" set power_save off >/dev/null 2>&1 || true

# Already connected → nothing to do.
if nmcli -t -f GENERAL.STATE device show "$IFACE" | grep -q connected; then
    exit 0
fi

# Radio off → turn it on and give airtime.
if [ "$(nmcli radio wifi)" != "enabled" ]; then
    nmcli radio wifi on
    sleep 3
fi

# Try configured networks in priority order, then give up until next tick.
nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY connection show | \
    awk -F: '$2=="802-11-wireless"{print $3"\t"$1}' | \
    sort -rn | \
    while IFS=$'\t' read -r _prio name; do
        nmcli connection up "$name" >/dev/null 2>&1 && exit 0
    done

exit 0