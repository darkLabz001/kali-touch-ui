"""Local device telemetry and bounded, user-triggered touchscreen controls."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from recording import RECORDINGS


def run(args, **kwargs):
    env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':0'),
               XAUTHORITY=str(Path.home() / '.Xauthority'),
               XDG_RUNTIME_DIR='/run/user/%s' % os.getuid(),
               DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/%s/bus' % os.getuid(), LC_ALL='C')
    return subprocess.run(args, capture_output=True, text=True, timeout=4, env=env, **kwargs)


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ''


def cpu_counters(text):
    fields = text.splitlines()[0].split()[1:9]
    numbers = [int(n) for n in fields]
    return sum(numbers), numbers[3] + (numbers[4] if len(numbers) > 4 else 0)


def net_counters(text):
    counters = {}
    for line in text.splitlines()[2:]:
        name, values = line.split(':', 1)
        fields = values.split()
        if name.strip() != 'lo':
            counters[name.strip()] = (int(fields[0]), int(fields[8]))
    return counters


def percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('Choose a percentage from 0 to 100.')
    return round(value)


class Device:
    def __init__(self):
        self.lock = threading.Lock()
        self.previous = None
        self.cached = None
        self.audio_at = 0
        self.audio = {'supported': False, 'value': None, 'muted': False}
        self.backlight = next(iter(sorted(Path('/sys/class/backlight').glob('*'))), None)

    def brightness(self):
        try:
            maximum = int(read(self.backlight / 'max_brightness'))
            value = int(read(self.backlight / 'brightness'))
            return {'supported': maximum > 0, 'value': round(value * 100 / maximum), 'minimum': 10}
        except (TypeError, ValueError, ZeroDivisionError):
            return {'supported': False, 'value': None, 'minimum': 10}

    def volume(self):
        if shutil.which('wpctl'):
            result = run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
            match = re.search(r'Volume:\s*([\d.]+)', result.stdout)
            if result.returncode == 0 and match:
                return {'supported': True, 'value': round(float(match[1]) * 100), 'muted': '[MUTED]' in result.stdout}
        return {'supported': False, 'value': None, 'muted': False}

    def status(self):
        with self.lock:
            now = time.monotonic()
            if self.cached and now - self.cached['_monotonic'] < 0.8:
                return self.cached
            total, idle = cpu_counters(read('/proc/stat'))
            network = net_counters(read('/proc/net/dev'))
            routes = read('/proc/net/route').splitlines()[1:]
            iface = next((r.split()[0] for r in routes if len(r.split()) > 3 and r.split()[1] == '00000000' and int(r.split()[3], 16) & 2), None)
            cpu = rx = tx = None
            if self.previous:
                prev = self.previous
                delta = total - prev['total']
                if delta > 0:
                    cpu = round(max(0, min(100, 100 * (1 - (idle - prev['idle']) / delta))), 1)
                elapsed = now - prev['time']
                if iface == prev['iface'] and iface in network and iface in prev['network'] and elapsed > 0:
                    incoming, outgoing = network[iface]; old_in, old_out = prev['network'][iface]
                    if incoming >= old_in and outgoing >= old_out:
                        rx, tx = (incoming - old_in) / elapsed, (outgoing - old_out) / elapsed
            self.previous = {'time': now, 'total': total, 'idle': idle, 'iface': iface, 'network': network}
            memory = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in read('/proc/meminfo').splitlines()}
            disk = shutil.disk_usage('/')
            thermal = read('/sys/class/thermal/thermal_zone0/temp')
            wireless = []
            for line in read('/proc/net/wireless').splitlines()[2:]:
                name, values = line.split(':', 1); fields = values.split()
                wireless.append({'interface': name.strip(), 'signal_dbm': float(fields[2].strip('.')),
                                 'quality': round(max(0, min(100, float(fields[1].strip('.')) / 70 * 100)))})
            if now - self.audio_at > 5:
                try:
                    self.audio = self.volume()
                except (OSError, subprocess.SubprocessError):
                    self.audio = {'supported': False, 'value': None, 'muted': False}
                self.audio_at = now
            self.cached = {'_monotonic': now, 'sampled_at': time.time(), 'hostname': socket.gethostname(),
                'cpu_percent': cpu, 'temperature_c': round(float(thermal) / 1000, 1) if thermal else None,
                'uptime_seconds': float(read('/proc/uptime').split()[0]),
                'memory': {'total': memory.get('MemTotal', 0), 'used': memory.get('MemTotal', 0) - memory.get('MemAvailable', 0)},
                'storage': {'total': disk.total, 'used': disk.used, 'free': disk.free},
                'network': {'interface': iface, 'rx_bps': rx, 'tx_bps': tx}, 'wireless': wireless,
                'controls': {'brightness': self.brightness(), 'volume': self.audio, 'screenshot': bool(shutil.which('import'))}}
            return self.cached

    def control(self, action, value=None):
        if action == 'record_start':
            return RECORDINGS.start()
        if action == 'record_stop':
            return RECORDINGS.stop()
        if action == 'record_send':
            return RECORDINGS.send(value)
        with self.lock:
            if action == 'brightness':
                value = max(10, percent(value))
                if not self.brightness()['supported']:
                    raise ValueError('No adjustable backlight was found.')
                path = self.backlight / 'brightness'
                raw = str(max(1, round(int(read(self.backlight / 'max_brightness')) * value / 100)))
                if os.access(path, os.W_OK):
                    path.write_text(raw)
                else:
                    result = run(['/usr/bin/sudo', '-n', '/usr/bin/tee', str(path)], input=raw)
                    if result.returncode:
                        raise ValueError('Backlight permission was denied.')
                result = self.brightness()
            elif action == 'volume':
                value = percent(value)
                if not self.volume()['supported']:
                    raise ValueError('No active audio output was found.')
                result = run(['wpctl', 'set-volume', '--limit', '1.0', '@DEFAULT_AUDIO_SINK@', str(value / 100)])
                if result.returncode:
                    raise ValueError('The audio output could not be adjusted.')
                result = self.volume(); self.audio = result; self.audio_at = time.monotonic()
            elif action == 'mute':
                if type(value) is not bool:
                    raise ValueError('Mute must be true or false.')
                result = run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1' if value else '0'])
                if result.returncode:
                    raise ValueError('The audio output could not be muted.')
                result = self.volume(); self.audio = result; self.audio_at = time.monotonic()
            elif action == 'screenshot':
                directory = Path.home() / 'Pictures' / 'KaliTouch'
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                filename = 'screen-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6] + '.png'
                path = directory / filename
                result = run(['import', '-window', 'root', str(path)])
                if result.returncode or not path.is_file():
                    raise ValueError('The screenshot could not be saved.')
                path.chmod(0o600)
                result = {'path': str(path), 'filename': filename}
            else:
                raise ValueError('Unknown device control.')
            self.cached = None
            return result


DEVICE = Device()


def handle_device_request(handler, method, path):
    if path not in ('/api/device/status', '/api/device/control', '/api/device/recording'):
        return False
    def reply(code, **body):
        handler._send(code, json.dumps(body).encode()); return True
    host = handler.headers.get('Host', '')
    if (handler.client_address[0] != '127.0.0.1' or host.split(':')[0] not in ('127.0.0.1', 'localhost')
            or handler.headers.get('Origin') not in ('http://127.0.0.1:8080', 'http://localhost:8080')):
        return reply(403, error='Device controls are available on the touchscreen only.')
    try:
        if method == 'GET' and path.endswith('/recording'):
            return reply(200, **RECORDINGS.status())
        if method == 'GET' and path.endswith('/status'):
            return reply(200, **DEVICE.status())
        if method != 'POST' or not path.endswith('/control'):
            return reply(405, error='Method not allowed.')
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 256 or handler.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return reply(400, error='Expected a small JSON control request.')
        body = json.loads(handler.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError('Invalid control request.')
        return reply(200, ok=True, result=DEVICE.control(body.get('action'), body.get('value')))
    except (ValueError, UnicodeError) as error:
        return reply(400, error=str(error))
    except (OSError, subprocess.SubprocessError):
        return reply(503, error='Device control is unavailable. Check the desktop session.')
