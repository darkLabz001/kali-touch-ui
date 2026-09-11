#!/usr/bin/env python3
"""
Wardriving tool for WiFi/BLE scanning with WiGLE upload and Biscuit node integration.
"""

import asyncio
import bisect
import csv
import json
import os
import re
import subprocess
import logging
import threading
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import time
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# WigleWifi-1.4 wants a local wall-clock stamp in this exact shape. The old
# code wrote one ISO8601 '…T…Z' string shared by every row in a scan cycle,
# which WiGLE cannot parse and which threw away *when* each AP was actually
# heard -- the other half of matching a sighting to a position.
WIGLE_TIME_FMT = '%Y-%m-%d %H:%M:%S'


def mono_to_epoch(mono: float) -> float:
    """Convert a time.monotonic() reading to a wall-clock epoch.

    Sightings are timed on the monotonic clock so an NTP step mid-drive can't
    reorder them, but WiGLE needs civil time; convert only at the edge.
    """
    return time.time() + (mono - time.monotonic())


def wigle_time(mono: float) -> str:
    return datetime.fromtimestamp(mono_to_epoch(mono)).strftime(WIGLE_TIME_FMT)


@dataclass
class WiFiNetwork:
    """WiFi Access Point data"""
    bssid: str
    ssid: str
    frequency: int
    signal_level: int
    security: str
    channel: int
    timestamp: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    # time.monotonic() of the sighting itself, not of the scan that reported
    # it. GPS is matched against this, so a beacon heard 4s into a sweep gets
    # the position from 4s in rather than from wherever the sweep ended.
    observed_at: float = field(default_factory=time.monotonic)

    def to_wigle_format(self) -> Dict[str, Any]:
        """Convert to WiGLE CSV format"""
        return {
            'MAC': self.bssid,
            'SSID': self.ssid,
            'AuthMode': self.security,
            'FirstSeen': self.timestamp,
            'Channel': self.channel,
            'RSSI': self.signal_level,
            'CurrentLatitude': self.latitude,
            'CurrentLongitude': self.longitude,
            'AltitudeMeters': self.altitude,
            'AccuracyMeters': self.accuracy,
            'Type': 'WIFI'
        }


@dataclass
class BLEDevice:
    """BLE Device data"""
    mac: str
    name: Optional[str]
    signal_level: int
    timestamp: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    observed_at: float = field(default_factory=time.monotonic)

    def to_wigle_format(self) -> Dict[str, Any]:
        """Convert to WiGLE format (if WiGLE supports BLE)"""
        return {
            'MAC': self.mac,
            'SSID': self.name or '',
            'AuthMode': '',
            'FirstSeen': self.timestamp,
            'Channel': '',
            'RSSI': self.signal_level,
            'CurrentLatitude': self.latitude,
            'CurrentLongitude': self.longitude,
            'AltitudeMeters': self.altitude,
            'AccuracyMeters': self.accuracy,
            'Type': 'BLE'
        }


def _split_terse(line: str) -> List[str]:
    """Split an `nmcli -t` row on field separators only.

    nmcli escapes colons *inside* values as '\\:', so a plain split(':') tears
    a BSSID into six pieces and every row fails to parse.
    """
    return [f.replace('\\:', ':').replace('\\\\', '\\')
            for f in re.split(r'(?<!\\):', line)]


def _quality_to_dbm(quality: int) -> int:
    """nmcli SIGNAL is 0-100 link quality; WiGLE wants dBm."""
    return max(-100, min(-30, int(quality / 2) - 100))


class WiFiScanner:
    """Scan for WiFi access points on Linux"""

    def __init__(self, ifname: str = None, prefer_iw: bool = True):
        self.networks: List[WiFiNetwork] = []
        self.ifname = ifname
        self.prefer_iw = prefer_iw
        self.backend = None

    def scan(self) -> List[WiFiNetwork]:
        """Scan via iw (true dBm) and fall back to nmcli if it yields nothing."""
        if self.prefer_iw and self.ifname:
            networks = self.scan_iw()
            if networks:
                self.backend = 'iw'
                return networks
            logger.warning("iw returned nothing on %s; falling back to nmcli",
                           self.ifname)
        networks = self.scan_nmcli()
        self.backend = 'nmcli'
        return networks

    def scan_nmcli(self, rescan: bool = True) -> List[WiFiNetwork]:
        """Use nmcli to scan for WiFi networks"""
        cmd = ['nmcli', '-t', '-f', 'BSSID,SSID,FREQ,SIGNAL,SECURITY,CHAN',
               'dev', 'wifi', 'list']
        if self.ifname:
            cmd += ['ifname', self.ifname]
        # Without --rescan yes nmcli replays a stale cache, so a moving
        # wardrive would keep re-reporting the APs from where it started.
        if rescan:
            cmd += ['--rescan', 'yes']

        try:
            started = time.monotonic()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            finished = time.monotonic()

            if result.returncode != 0:
                logger.error("nmcli scan failed (rc=%s): %s",
                             result.returncode, result.stderr.strip())
                return []

            networks = []
            # nmcli exposes no per-AP timing, so every AP in the batch can only
            # be placed at the middle of the sweep window -- half the sweep
            # length of error either way. `iw` reports "last seen" per BSS and
            # is preferred precisely because of this.
            observed_at = started + (finished - started) / 2
            timestamp = wigle_time(observed_at)

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = _split_terse(line)
                if len(parts) < 6:
                    logger.warning("short WiFi row (%d fields): %r", len(parts), line)
                    continue

                try:
                    bssid = parts[0].strip()
                    ssid = parts[1].strip()
                    # FREQ arrives as "2437 MHz"
                    freq = int(parts[2].split()[0])
                    signal = _quality_to_dbm(int(parts[3].strip()))
                    security = parts[4].strip() or 'OPEN'
                    channel = int(parts[5].strip())
                except (ValueError, IndexError) as e:
                    logger.warning("failed to parse WiFi row %r: %s", line, e)
                    continue

                networks.append(WiFiNetwork(
                    bssid=bssid,
                    ssid=ssid,
                    frequency=freq,
                    signal_level=signal,
                    security=security,
                    channel=channel,
                    timestamp=timestamp,
                    observed_at=observed_at,
                ))

            self.networks = networks
            logger.info("scanned %d WiFi networks on %s",
                        len(networks), self.ifname or 'any')
            return networks

        except subprocess.TimeoutExpired:
            logger.error("WiFi scan timed out")
            return []
        except Exception as e:
            logger.error(f"WiFi scan error: {e}")
            return []

    def scan_iw(self) -> List[WiFiNetwork]:
        """Scan with `iw`, which reports true per-AP dBm.

        nmcli only exposes a 0-100 quality figure that many drivers (notably
        the Realtek 8812AU) peg at 100, collapsing every AP to the same RSSI.
        WiGLE stores RSSI, so the real value matters.
        """
        if not self.ifname:
            logger.warning("iw scan needs an interface name; falling back")
            return []

        # A full scan needs CAP_NET_ADMIN; 'scan dump' reads the cached
        # results and works unprivileged, so try the active scan and fall
        # back rather than silently returning nothing.
        out = None
        finished = None
        for args in (['iw', 'dev', self.ifname, 'scan'],
                     ['iw', 'dev', self.ifname, 'scan', 'dump']):
            try:
                res = subprocess.run(args, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                logger.error("iw scan timed out on %s", self.ifname)
                continue
            except FileNotFoundError:
                logger.error("iw not installed (apt install iw)")
                return []
            if res.returncode == 0 and res.stdout.strip():
                out = res.stdout
                finished = time.monotonic()
                break
            logger.debug("`%s` rc=%s: %s", ' '.join(args), res.returncode,
                         res.stderr.strip())

        if not out:
            logger.warning("iw produced no scan results on %s", self.ifname)
            return []

        networks = self._parse_iw(out, finished)
        self.networks = networks
        logger.info("scanned %d WiFi networks on %s via iw", len(networks), self.ifname)
        return networks

    @staticmethod
    def _freq_to_channel(freq_mhz: float) -> int:
        f = int(freq_mhz)
        if f == 2484:
            return 14
        if 2412 <= f <= 2472:
            return (f - 2407) // 5
        if 5160 <= f <= 5885:
            return (f - 5000) // 5
        if 5955 <= f <= 7115:          # 6 GHz / WiFi 6E
            return (f - 5950) // 5
        return 0

    @classmethod
    def _parse_iw(cls, out: str, scan_end: float = None) -> List[WiFiNetwork]:
        """Parse `iw scan` output, back-dating each BSS to when it was heard.

        iw prints "last seen: N ms ago" per BSS, measured from when the dump
        was produced. Using it means an AP whose beacon arrived 6s ago is
        placed 6s back along the track instead of at the car's current spot.
        """
        if scan_end is None:
            scan_end = time.monotonic()
        networks = []
        cur = None

        def flush(bss):
            if not bss or not bss.get('bssid'):
                return
            if bss.get('signal') is None:
                return
            observed_at = scan_end - (bss.get('last_seen_ms') or 0) / 1000.0
            if bss.get('rsn_sae'):
                security = 'WPA3'
            elif bss.get('rsn'):
                security = 'WPA2'
            elif bss.get('wpa'):
                security = 'WPA'
            elif bss.get('privacy'):
                security = 'WEP'
            else:
                security = 'OPEN'
            networks.append(WiFiNetwork(
                bssid=bss['bssid'],
                ssid=bss.get('ssid', ''),
                frequency=int(bss.get('freq') or 0),
                signal_level=int(round(bss['signal'])),
                security=security,
                channel=bss.get('channel') or cls._freq_to_channel(bss.get('freq') or 0),
                timestamp=wigle_time(observed_at),
                observed_at=observed_at,
            ))

        for line in out.split('\n'):
            if line.startswith('BSS '):
                flush(cur)
                mac = line[4:].split('(')[0].strip()
                cur = {'bssid': mac.upper()}
                continue
            if cur is None:
                continue

            s = line.strip()
            if s.startswith('freq:'):
                try:
                    cur['freq'] = float(s.split(':', 1)[1])
                except ValueError:
                    pass
            elif s.startswith('signal:'):
                try:
                    cur['signal'] = float(s.split(':', 1)[1].split()[0])
                except (ValueError, IndexError):
                    pass
            elif s.startswith('last seen:'):
                # "last seen: 684 ms ago"
                try:
                    cur['last_seen_ms'] = float(s.split(':', 1)[1].split()[0])
                except (ValueError, IndexError):
                    pass
            elif s.startswith('SSID:'):
                ssid = s.split(':', 1)[1].strip()
                # iw renders a hidden SSID as literal '\x00' escapes.
                if not ssid or set(re.findall(r'\\x[0-9a-fA-F]{2}', ssid)) == {'\\x00'}:
                    ssid = ''
                cur['ssid'] = ssid
            elif s.startswith('capability:'):
                cur['privacy'] = 'Privacy' in s
            elif s.startswith('RSN:'):
                cur['rsn'] = True
                cur['_in'] = 'rsn'
            elif s.startswith('WPA:'):
                cur['wpa'] = True
                cur['_in'] = 'wpa'
            elif s.startswith('* Authentication suites:'):
                if cur.get('_in') == 'rsn' and 'SAE' in s:
                    cur['rsn_sae'] = True
            elif s.startswith('* primary channel:'):
                try:
                    cur['channel'] = int(s.split(':', 1)[1])
                except ValueError:
                    pass
            elif s.startswith('DS Parameter set: channel'):
                try:
                    cur['channel'] = int(s.rsplit(' ', 1)[1])
                except (ValueError, IndexError):
                    pass

        flush(cur)
        return networks


class BLEScanner:
    """Scan for BLE devices"""

    def __init__(self, adapter: str = None):
        self.devices: List[BLEDevice] = []
        self.adapter = adapter
        self.last_error: Optional[str] = None
        self._prepared = False

    def prepare_adapter(self) -> Optional[str]:
        """Start bluetoothd and bring the adapter up.

        BlueZ needs both before any scan works; a DOWN adapter or stopped
        daemon just yields zero devices with no obvious reason why.
        """
        hci = self.adapter or 'hci0'

        active = subprocess.run(['systemctl', 'is-active', 'bluetooth'],
                                capture_output=True, text=True, timeout=10)
        if active.stdout.strip() != 'active':
            logger.info("bluetooth service is %s; starting it", active.stdout.strip())
            started = subprocess.run(['systemctl', 'start', 'bluetooth'],
                                     capture_output=True, text=True, timeout=30)
            if started.returncode != 0:
                return f"could not start bluetooth service: {started.stderr.strip()}"
            time.sleep(2)  # bluetoothd needs a moment to claim the adapter

        state = subprocess.run(['hciconfig', hci], capture_output=True,
                               text=True, timeout=10)
        if state.returncode != 0:
            return f"{hci} not found (is the dongle plugged in?)"
        if 'DOWN' in state.stdout:
            logger.info("%s is DOWN; bringing it up", hci)
            up = subprocess.run(['hciconfig', hci, 'up'],
                                capture_output=True, text=True, timeout=15)
            if up.returncode != 0:
                return f"could not bring {hci} up: {up.stderr.strip() or 'need root?'}"
            time.sleep(1)
        return None

    async def scan_bluez(self, duration: int = 10) -> List[BLEDevice]:
        """Scan for BLE devices using BlueZ via bleak (gives real RSSI)."""
        if not self._prepared:
            problem = self.prepare_adapter()
            self._prepared = True
            if problem:
                self.last_error = problem
                logger.error("BLE unavailable: %s", problem)
                return []

        try:
            from bleak import BleakScanner
        except ImportError:
            self.last_error = "bleak not installed (pip install bleak)"
            logger.error(self.last_error)
            return []

        # BleakScanner.discover() only hands back a dict once the whole sweep
        # is over, so every device would share the sweep's end position -- at
        # 30mph an 8s sweep is 100m of smear. A detection callback fires as
        # each advertisement arrives, so each one can be stamped for real.
        best: Dict[str, BLEDevice] = {}

        def on_detect(device, adv):
            now = time.monotonic()
            rssi = adv.rssi if adv.rssi is not None else -100
            prev = best.get(device.address)
            # Keep the strongest advertisement and *its* timestamp: peak RSSI
            # is the closest approach, which is the best position estimate we
            # have for where the device actually is.
            if prev is not None and rssi <= prev.signal_level:
                # A later sighting can still fill in a name the first lacked.
                if prev.name is None:
                    prev.name = adv.local_name or device.name or None
                return
            best[device.address] = BLEDevice(
                mac=device.address,
                name=(adv.local_name or device.name
                      or (prev.name if prev else None)),
                signal_level=rssi,
                timestamp=wigle_time(now),
                observed_at=now,
            )

        try:
            kwargs = {'detection_callback': on_detect}
            if self.adapter:
                kwargs['adapter'] = self.adapter
            scanner = BleakScanner(**kwargs)
            async with scanner:
                await asyncio.sleep(duration)
        except Exception as e:
            self.last_error = str(e)
            logger.error("BLE scan error: %s", e)
            # Advertisements already collected before the failure are real
            # sightings; keep them rather than discarding the partial sweep.
            return list(best.values())

        devices = list(best.values())
        self.last_error = None
        self.devices = devices
        logger.info("scanned %d BLE devices on %s", len(devices), self.adapter or 'default')
        return devices


class ClockSync:
    """Map a remote clock's timestamps onto the local monotonic clock.

    The phone stamps each fix with its own clock and may hold several before
    the network lets it deliver them. Stamping the whole batch on arrival
    would collapse that stretch of road onto one point, so the offset between
    the two clocks is estimated instead and each fix placed through it.
    """

    def __init__(self):
        self.offset: Optional[float] = None

    def stamp(self, remote_times: List[float], arrival: float) -> List[float]:
        """Convert remote epoch-seconds to monotonic, in arrival order."""
        if not remote_times:
            return []
        newest = max(remote_times)
        # The newest item waited the least, so it bounds the offset tightest;
        # measuring from an older one folds the batching delay into the
        # estimate and drags the whole track backwards.
        candidate = arrival - newest
        if self.offset is None or candidate < self.offset:
            self.offset = candidate
        else:
            # Allow slow upward drift so real clock skew is tracked rather
            # than pinned forever by one early low-latency sample.
            self.offset += (candidate - self.offset) * 0.01
        # Never accept a fix stamped in the future.
        return [min(t + self.offset, arrival) for t in remote_times]


@dataclass
class GPSFix:
    """One position report, stamped on the monotonic clock."""
    at: float                        # time.monotonic() when received
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    speed: Optional[float] = None    # m/s, when the source reports it
    heading: Optional[float] = None  # degrees true
    source: str = 'phone'


class GPSHandler:
    """Match captures to the position the receiver was at when it heard them.

    Keeps a short history of fixes rather than a single "current" location, so
    a sighting can be looked up against the fix that was actually valid at its
    own timestamp. During a sweep the vehicle keeps moving; tagging everything
    with the position at the end of the sweep smears a whole block of APs onto
    one point.
    """

    # A phone browser tab that gets suspended (iOS does this aggressively)
    # silently stops sending fixes. Anything older than this is treated as
    # unknown rather than tagged onto APs we may have driven well past. At
    # 30mph, 15s of extrapolation is already ~200m of error.
    MAX_FIX_AGE = 15.0

    # Beyond this, two fixes are treated as separate legs and the gap between
    # them is not interpolated across -- a phone that went quiet for a minute
    # tells us nothing about the road taken in between.
    MAX_INTERP_GAP = 60.0

    TRACK_LIMIT = 20000

    def __init__(self, max_fix_age: float = None):
        self.max_fix_age = max_fix_age if max_fix_age is not None else self.MAX_FIX_AGE
        self.manual = False
        self.manual_fix: Optional[GPSFix] = None
        self.track: deque = deque(maxlen=self.TRACK_LIMIT)
        self._times: deque = deque(maxlen=self.TRACK_LIMIT)  # parallel, for bisect
        self.source: Optional[str] = None
        self.fix_count = 0
        # Fixes arrive on the HTTP/NMEA threads while the scan thread reads
        # the track; the out-of-order insert below rebuilds both deques and is
        # not atomic on its own.
        self._lock = threading.RLock()

    # -- current state (kept for callers that just want "where am I now") ----

    @property
    def last_fix(self) -> Optional[GPSFix]:
        if self.manual:
            return self.manual_fix
        return self.track[-1] if self.track else None

    @property
    def latitude(self) -> Optional[float]:
        fix = self.last_fix
        return fix.latitude if fix else None

    @property
    def longitude(self) -> Optional[float]:
        fix = self.last_fix
        return fix.longitude if fix else None

    @property
    def accuracy(self) -> Optional[float]:
        fix = self.last_fix
        return fix.accuracy if fix else None

    @property
    def updated_at(self) -> Optional[float]:
        fix = self.last_fix
        return fix.at if fix else None

    def set_location(self, lat: float, lon: float, accuracy: float = None,
                     manual: bool = False, altitude: float = None,
                     speed: float = None, heading: float = None,
                     source: str = None, at: float = None):
        """Record a fix, stamped so it can be matched to sightings by time."""
        fix = GPSFix(
            at=at if at is not None else time.monotonic(),
            latitude=lat, longitude=lon, accuracy=accuracy, altitude=altitude,
            speed=speed, heading=heading,
            source=source or ('manual' if manual else 'phone'),
        )
        with self._lock:
            self.manual = manual
            self.source = fix.source
            self.fix_count += 1
            if manual:
                # A pinned position is an assertion about the whole session,
                # not a point on a track, so it does not belong in the
                # interpolation history where it would drag real fixes to it.
                self.manual_fix = fix
            else:
                # Out-of-order arrivals (a UDP NMEA feed, a delayed HTTP
                # retry) would break the bisect lookup, so insert in order.
                if self._times and fix.at < self._times[-1]:
                    idx = bisect.bisect_left(self._times, fix.at)
                    items = list(self.track)
                    times = list(self._times)
                    items.insert(idx, fix)
                    times.insert(idx, fix.at)
                    self.track = deque(items, maxlen=self.TRACK_LIMIT)
                    self._times = deque(times, maxlen=self.TRACK_LIMIT)
                else:
                    self.track.append(fix)
                    self._times.append(fix.at)
        logger.info("GPS fix: %s, %s (+/-%sm) via %s%s", lat, lon, accuracy,
                    fix.source, " [manual]" if manual else "")

    def age(self) -> Optional[float]:
        """Seconds since the last fix, or None if there has never been one."""
        if self.updated_at is None:
            return None
        return time.monotonic() - self.updated_at

    def is_fresh(self) -> bool:
        """True when the current fix is recent enough to tag captures with.

        A manually entered location never expires -- the user asserted a
        fixed position, so there is no live feed to go stale.
        """
        if self.manual:
            return self.manual_fix is not None
        age = self.age()
        return age is not None and age <= self.max_fix_age

    # -- the actual sync ------------------------------------------------------

    def fix_at(self, when: float) -> Optional[GPSFix]:
        """Where we were at monotonic time `when`, or None if not knowable.

        Interpolates between the two fixes bracketing `when`; outside the
        track it will only reach back/forward by max_fix_age, so a sighting
        from before the phone connected stays unlocated rather than being
        assigned the first fix that happened to arrive.
        """
        with self._lock:
            if self.manual:
                return self.manual_fix
            if not self.track:
                return None

            times = self._times
            idx = bisect.bisect_left(times, when)

            if idx == 0:
                first = self.track[0]
                return first if first.at - when <= self.max_fix_age else None
            if idx >= len(times):
                last = self.track[-1]
                return last if when - last.at <= self.max_fix_age else None

            before = self.track[idx - 1]
            after = self.track[idx]

        gap = after.at - before.at
        if gap > self.MAX_INTERP_GAP:
            # Don't invent a path across a dropout; fall back to whichever end
            # is close enough to stand on its own.
            nearest = before if (when - before.at) <= (after.at - when) else after
            return nearest if abs(when - nearest.at) <= self.max_fix_age else None
        if gap <= 0:
            return after

        ratio = (when - before.at) / gap
        return GPSFix(
            at=when,
            latitude=before.latitude + (after.latitude - before.latitude) * ratio,
            longitude=before.longitude + (after.longitude - before.longitude) * ratio,
            # An interpolated point is no better than the worse of its anchors.
            accuracy=_worse(before.accuracy, after.accuracy),
            altitude=_lerp(before.altitude, after.altitude, ratio),
            speed=_lerp(before.speed, after.speed, ratio),
            heading=after.heading if after.heading is not None else before.heading,
            source=after.source,
        )

    def is_bracketed(self, when: float) -> bool:
        """True once a fix exists at or after `when`.

        Until then any answer for `when` is an extrapolation forward from the
        last fix. Callers use this to hold a sighting back for a moment so it
        can be interpolated between two real fixes instead.
        """
        with self._lock:
            if self.manual:
                return True
            return bool(self._times) and self._times[-1] >= when

    def tag_records(self, records, kind: str = 'record') -> int:
        """Give every record the position that was current when it was heard.

        Returns the number that got located.
        """
        if not records:
            return 0
        located = 0
        for rec in records:
            fix = self.fix_at(rec.observed_at)
            if fix is None:
                continue
            rec.latitude = fix.latitude
            rec.longitude = fix.longitude
            rec.accuracy = fix.accuracy
            rec.altitude = fix.altitude
            located += 1
        if located < len(records):
            logger.debug("no usable fix yet for %d/%d %s record(s)",
                         len(records) - located, len(records), kind)
        return located

    def apply_to_networks(self, networks: List[WiFiNetwork]) -> int:
        return self.tag_records(networks, 'WiFi')

    def apply_to_ble(self, devices: List[BLEDevice]) -> int:
        return self.tag_records(devices, 'BLE')


def _lerp(a: Optional[float], b: Optional[float], ratio: float) -> Optional[float]:
    if a is None or b is None:
        return a if b is None else b
    return a + (b - a) * ratio


def _worse(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return a if b is None else b
    return max(a, b)


class WiGLEUploader:
    """Handle WiGLE API integration"""

    def __init__(self, api_token: str = None):
        self.api_token = api_token
        self.api_url = "https://api.wigle.net/api/v3"

    def save_to_csv(self, networks: List[WiFiNetwork], devices: List[BLEDevice],
                    filename: str = None) -> str:
        """Save scan data to CSV format compatible with WiGLE"""
        if filename is None:
            filename = f"wardriving_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        columns = ['MAC', 'SSID', 'AuthMode', 'FirstSeen', 'Channel', 'RSSI',
                   'CurrentLatitude', 'CurrentLongitude', 'AltitudeMeters',
                   'AccuracyMeters', 'Type']

        rows = [r.to_wigle_format() for r in networks]
        rows += [d.to_wigle_format() for d in devices]

        # A row with no fix would be placed at (0,0) on the map, so drop it.
        located = [r for r in rows
                   if r['CurrentLatitude'] is not None
                   and r['CurrentLongitude'] is not None]
        dropped = len(rows) - len(located)
        if dropped:
            logger.warning("omitted %d record(s) with no GPS fix", dropped)

        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w', newline='', encoding='utf-8') as fh:
            # WiGLE requires this preamble before the column header;
            # without it the upload is rejected as an unknown format.
            fh.write('WigleWifi-1.4,appRelease=1.0.0,model=wardriver,'
                     'release=1.0.0,device=wardriver,display=,board=,brand=\n')
            # QUOTE_MINIMAL + the csv module so an SSID containing a comma or
            # quote can't shift every following column.
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for row in located:
                # None would otherwise be written as the literal text "None".
                writer.writerow({k: ('' if row.get(k) is None else row[k])
                                 for k in columns})

        logger.info("saved %d records to %s (%d without GPS omitted)",
                    len(located), output_path, dropped)
        return str(output_path)

    def load_credentials(self, creds_file: str = "~/.wigle_credentials"):
        """Load WiGLE API credentials from file"""
        try:
            creds_path = Path(creds_file).expanduser()
            with open(creds_path) as f:
                creds = json.load(f)
                self.api_token = creds.get('api_token')
                logger.info("Loaded WiGLE credentials")
        except FileNotFoundError:
            logger.warning(f"Credentials file not found: {creds_file}")
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in {creds_file}")


class WardriveSession:
    """Main wardriving session manager"""

    def __init__(self, wifi_ifname: str = None, ble_adapter: str = None):
        self.wifi_scanner = WiFiScanner(ifname=wifi_ifname)
        self.ble_scanner = BLEScanner(adapter=ble_adapter)
        self.gps = GPSHandler()
        self.wigle = WiGLEUploader()
        # Sightings held back until the GPS track can bracket them; see
        # resolve_pending().
        self._pending: List[Any] = []
        self.session_data = {
            'networks': [],
            'devices': [],
            'start_time': datetime.utcnow().isoformat()
        }

    WIGLE_COLUMNS = ['MAC', 'SSID', 'AuthMode', 'FirstSeen', 'Channel', 'RSSI',
                     'CurrentLatitude', 'CurrentLongitude', 'AltitudeMeters',
                     'AccuracyMeters', 'Type']

    def start_autosave(self, path) -> str:
        """Append captures to disk as they happen.

        Everything otherwise lives in memory until UPLOAD, so a crash or an
        accidental quit loses the whole drive.
        """
        self._autosave_path = Path(path)
        self._autosave_path.parent.mkdir(parents=True, exist_ok=True)
        self._autosave_seen = set()
        fresh = not self._autosave_path.exists()
        self._autosave_fh = self._autosave_path.open('a', newline='', encoding='utf-8')
        self._autosave_writer = csv.DictWriter(
            self._autosave_fh, fieldnames=self.WIGLE_COLUMNS, extrasaction='ignore')
        if fresh:
            self._autosave_fh.write(
                'WigleWifi-1.4,appRelease=1.0.0,model=wardriver,'
                'release=1.0.0,device=wardriver,display=,board=,brand=\n')
            self._autosave_writer.writeheader()
            self._autosave_fh.flush()
        logger.info("autosaving to %s", self._autosave_path)
        return str(self._autosave_path)

    def _autosave(self, records):
        """Write any record that is located and not already logged here."""
        writer = getattr(self, '_autosave_writer', None)
        if writer is None:
            return
        wrote = False
        for rec in records:
            row = rec.to_wigle_format()
            if row['CurrentLatitude'] is None or row['CurrentLongitude'] is None:
                continue
            # Same device at the same spot is not a new observation; a real
            # move (5dp ~ 1m) is.
            key = (row['MAC'], round(row['CurrentLatitude'], 5),
                   round(row['CurrentLongitude'], 5))
            if key in self._autosave_seen:
                continue
            self._autosave_seen.add(key)
            writer.writerow({k: ('' if row.get(k) is None else row[k])
                             for k in self.WIGLE_COLUMNS})
            wrote = True
        if wrote:
            # flush+fsync so a hard kill still leaves the rows on disk
            self._autosave_fh.flush()
            os.fsync(self._autosave_fh.fileno())

    def close_autosave(self):
        # Anything still waiting on a bracketing fix has run out of time;
        # settle it now rather than dropping it on the floor at exit.
        self.resolve_pending(force=True)
        fh = getattr(self, '_autosave_fh', None)
        if fh and not fh.closed:
            fh.flush()
            os.fsync(fh.fileno())
            fh.close()
            logger.info("autosave closed: %s", self._autosave_path)

    def scan_once(self, ble_duration: int = 8):
        """Perform a single scan cycle (WiFi + BLE)."""
        logger.info("Starting scan cycle...")

        networks = self.wifi_scanner.scan()
        self.session_data['networks'].extend(networks)
        self._queue_for_location(networks)

        devices = self.scan_ble_once(ble_duration)
        logger.info("Collected %d WiFi networks and %d BLE devices this cycle",
                    len(networks), len(devices))
        return networks, devices

    def scan_ble_once(self, duration: int = 8) -> List[BLEDevice]:
        """Run one BLE sweep. Safe to call from a worker thread."""
        try:
            devices = asyncio.run(self.ble_scanner.scan_bluez(duration))
        except Exception as e:
            logger.error("BLE cycle failed: %s", e)
            return []

        self.session_data['devices'].extend(devices)
        self._queue_for_location(devices)
        return devices

    # -- deferred geotagging --------------------------------------------------
    #
    # A sighting is only tagged once the GPS track has a fix on *both* sides of
    # it, so its position is interpolated between two real fixes rather than
    # extrapolated forward from the last one. Fixes arrive every second or so;
    # holding a record back that long buys a genuinely correct position instead
    # of one guessed from where we were a moment ago.

    # How long to hold an untagged record hoping for a later fix, before
    # deciding the feed is not going to bracket it.
    LOCATION_GRACE = 8.0

    def _queue_for_location(self, records):
        self._pending.extend(records)
        self.resolve_pending()

    def resolve_pending(self, force: bool = False) -> int:
        """Tag every pending record that can now be placed; autosave those.

        Records still waiting for a bracketing fix stay queued until they run
        past LOCATION_GRACE, at which point we settle for the best available
        answer (which may be none, leaving them unlocated).
        """
        if not self._pending:
            return 0
        now = time.monotonic()
        still_waiting = []
        ready = []
        for rec in self._pending:
            expired = force or (now - rec.observed_at) > self.LOCATION_GRACE
            if self.gps.is_bracketed(rec.observed_at) or expired:
                ready.append(rec)
            else:
                still_waiting.append(rec)
        self._pending = still_waiting
        if not ready:
            return 0

        located = self.gps.tag_records(ready, 'queued')
        self._autosave(ready)
        if located:
            logger.info("geotagged %d/%d pending record(s)", located, len(ready))
        return located

    async def scan_loop(self, interval: int = 10, duration: int = None):
        """Continuous scanning loop"""
        logger.info(f"Starting scan loop (interval: {interval}s)")
        start_time = time.time()

        try:
            while True:
                self.scan_once()

                if duration and (time.time() - start_time) > duration:
                    logger.info("Duration limit reached, stopping scan")
                    break

                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Scan interrupted by user")

    def save_session(self, filename: str = None) -> str:
        """Save session data"""
        # Flush the geotag queue first, or the newest sweep is written out
        # unlocated and silently dropped by save_to_csv.
        self.resolve_pending(force=True)
        self.session_data['end_time'] = datetime.utcnow().isoformat()
        self.session_data['total_networks'] = len(self.session_data['networks'])

        return self.wigle.save_to_csv(
            self.session_data['networks'],
            self.session_data['devices'],
            filename
        )

    def print_summary(self):
        """Print session summary"""
        logger.info(f"\n{'='*60}")
        logger.info("WARDRIVING SESSION SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Start Time: {self.session_data.get('start_time')}")
        logger.info(f"Total Networks Found: {len(self.session_data['networks'])}")
        logger.info(f"Total BLE Devices: {len(self.session_data['devices'])}")
        if self.gps.latitude:
            logger.info(f"Last GPS: {self.gps.latitude}, {self.gps.longitude}")
        logger.info(f"{'='*60}\n")


# Example usage
if __name__ == "__main__":
    session = WardriveSession()

    # Set GPS location (example)
    session.gps.set_location(37.7749, -122.4194, accuracy=5.0)

    # Run scan
    try:
        # Single scan
        session.scan_once()

        # Or continuous scan: asyncio.run(session.scan_loop(interval=10, duration=60))

        # Save results
        session.save_session()
        session.print_summary()

    except PermissionError:
        logger.error("Need sudo for WiFi scanning: sudo python3 wardriver.py")
    except Exception as e:
        logger.error(f"Error: {e}")
