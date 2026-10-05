"""Private local screen recordings and explicit uploads to one configured webhook."""
import atexit
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

MAX_SECONDS = 120
MAX_BYTES = 9 * 1024 * 1024
FILENAME = re.compile(r'recording-\d{8}-\d{6}-[a-f0-9]{8}\.mp4')


class UploadError(ValueError):
    """An upload failure with a fixed message safe to show in the UI."""


def webhook_url(value):
    """Use the normal upload endpoint of a GitHub-compatible Discord webhook."""
    parts = urlsplit(value.strip())
    match = re.fullmatch(r'/api(?:/v\d+)?/webhooks/(\d+)/([A-Za-z0-9_-]{20,200})(?:/github)?/?', parts.path)
    if (parts.scheme != 'https' or parts.netloc not in ('discord.com', 'discordapp.com')
            or parts.query or parts.fragment or not match):
        raise ValueError('Configure a valid Discord webhook on the device.')
    return 'https://discord.com/api/webhooks/' + '/'.join(match.groups())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upload_clip(url, path):
    """Never return network exception text: it may contain the secret webhook URL."""
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise UploadError('This clip exceeds the 9 MiB upload limit. It is still saved on the device.')
    boundary = 'KaliTouch' + uuid.uuid4().hex
    payload = json.dumps({'content': 'Kali Touch screen recording', 'allowed_mentions': {'parse': []},
                          'attachments': [{'id': 0, 'filename': path.name}]}).encode()
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
            'Content-Type: application/json\r\n\r\n').encode() + payload
    data += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
             f'filename="{path.name}"\r\nContent-Type: video/mp4\r\n\r\n').encode()
    data += raw + f'\r\n--{boundary}--\r\n'.encode()
    request = Request(url + '?wait=true', data=data, headers={
        'Content-Type': 'multipart/form-data; boundary=' + boundary,
        'User-Agent': 'KaliTouch-ScreenRecorder/1.0'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            result = json.loads(response.read(65536))
            if not isinstance(result, dict) or not result.get('id'):
                raise UploadError('Discord did not confirm delivery. Check the channel before retrying.')
    except HTTPError as error:
        code = error.code
        error.close()
        if code == 429:
            raise UploadError('Discord rate limit reached. Wait before tapping Send again.') from None
        if code == 413:
            raise UploadError('Discord rejected the clip size. The recording is still saved locally.') from None
        raise UploadError(f'Discord rejected the upload (HTTP {code}). The recording is still saved locally.') from None
    except (URLError, OSError, HTTPException, json.JSONDecodeError):
        raise UploadError('Upload not confirmed. Check Discord before retrying; the clip is saved locally.') from None


class Recordings:
    def __init__(self, directory=None, config=None):
        self.directory = Path(directory) if directory else Path.home() / 'Videos' / 'KaliTouch'
        self.config = Path(config) if config else Path.home() / '.config' / 'kali-touch-ui' / 'discord-webhook'
        self.lock = threading.RLock()
        self.proc = None
        self.state = 'idle'
        self.started = 0
        self.error = ''
        self.upload_error = ''
        self.uploading = False
        self.last = None
        self.worker = None
        try:
            last = json.loads((self.directory / 'latest.json').read_text())
            if isinstance(last, dict) and self.clip_path(last.get('filename')).is_file():
                self.last = last
        except (OSError, ValueError, TypeError):
            pass

    def clip_path(self, filename):
        if not isinstance(filename, str) or not FILENAME.fullmatch(filename):
            raise ValueError('Choose the latest finished recording.')
        path = self.directory / filename
        if path.is_symlink():
            raise ValueError('Recording links are not supported.')
        return path

    def configured_url(self):
        try:
            return webhook_url(self.config.read_text())
        except (OSError, ValueError):
            return None

    def status(self):
        with self.lock:
            last = dict(self.last) if self.last else None
            if last:
                try:
                    path = self.clip_path(last['filename'])
                    last['size'] = path.stat().st_size
                    last['path'] = str(path)
                except (OSError, ValueError):
                    last = None
            return {'supported': bool(shutil.which('ffmpeg') and shutil.which('ffprobe') and shutil.which('xrandr')),
                    'state': self.state, 'elapsed': max(0, int(time.monotonic() - self.started)) if self.proc else 0,
                    'max_seconds': MAX_SECONDS, 'last': last, 'error': self.error,
                    'discord_configured': bool(self.configured_url()), 'uploading': self.uploading,
                    'upload_error': self.upload_error}

    def persist(self):
        path = self.directory / 'latest.json'
        temporary = self.directory / ('latest-' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(self.last, handle)
        temporary.replace(path)

    def start(self):
        with self.lock:
            if self.proc or self.uploading:
                raise ValueError('Finish the current recording or upload first.')
            if not self.status()['supported']:
                raise ValueError('Install ffmpeg and xrandr to record this display.')
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if shutil.disk_usage(self.directory).free < 100 * 1024 * 1024:
                raise ValueError('Recording needs at least 100 MiB of free disk space.')
            env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':0'),
                       XAUTHORITY=str(Path.home() / '.Xauthority'), LC_ALL='C')
            display = subprocess.run(['xrandr', '--current'], capture_output=True, text=True, timeout=4, env=env)
            match = re.search(r'current (\d+) x (\d+)', display.stdout)
            if display.returncode or not match:
                raise ValueError('The desktop display could not be read.')
            width, height = map(int, match.groups())
            if not 2 <= width <= 4096 or not 2 <= height <= 4096:
                raise ValueError('The display size is unsupported for recording.')
            filename = 'recording-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.mp4'
            path = self.clip_path(filename)
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostats', '-n',
                       '-f', 'x11grab', '-framerate', '15', '-video_size', f'{width}x{height}',
                       '-i', env['DISPLAY'], '-an', '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                       '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                       '-b:v', '450k', '-maxrate', '500k', '-bufsize', '1M',
                       '-t', str(MAX_SECONDS), '-fs', str(MAX_BYTES - 128 * 1024),
                       '-movflags', '+faststart', str(path)]
            log = tempfile.TemporaryFile()
            try:
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=log, env=env, start_new_session=True, umask=0o077)
            except OSError:
                log.close()
                raise
            self.proc = proc
            self.started = time.monotonic()
            self.state = 'recording'
            self.error = self.upload_error = ''
            self.worker = threading.Thread(target=self.finish, args=(proc, path, log), daemon=True)
            self.worker.start()
            return self.status()

    def finish(self, proc, path, log):
        try:
            code = proc.wait()
            with self.lock:
                self.state = 'stopping'
            if code != 0 or not path.is_file() or not path.stat().st_size:
                raise ValueError('Recording failed. Check the desktop and FFmpeg encoder.')
            result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                     '-of', 'json', str(path)], capture_output=True, text=True, timeout=10)
            duration = float(json.loads(result.stdout)['format']['duration'])
            if result.returncode or not 0 < duration < MAX_SECONDS + 10:
                raise ValueError('The recording could not be finalized.')
            path.chmod(0o600)
            with self.lock:
                self.last = {'filename': path.name, 'duration': round(duration, 1), 'sent': False}
                self.persist()
                self.state = 'ready'
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            with self.lock:
                self.state = 'error'
                self.error = 'Recording could not be finalized. Any earlier completed clip is still saved.'
        finally:
            log.close()
            with self.lock:
                if proc.stdin:
                    proc.stdin.close()
                self.proc = None

    def stop(self):
        with self.lock:
            if not self.proc:
                return self.status()
            if self.state != 'stopping':
                self.state = 'stopping'
                try:
                    self.proc.stdin.write(b'q\n')
                    self.proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                threading.Thread(target=self.stop_timeout, args=(self.proc,), daemon=True).start()
            return self.status()

    @staticmethod
    def stop_timeout(proc):
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def send(self, filename):
        with self.lock:
            if self.proc or self.uploading:
                raise ValueError('Finish the current recording or upload first.')
            if not self.last or filename != self.last.get('filename'):
                raise ValueError('Choose the latest finished recording.')
            path = self.clip_path(filename)
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
                raise ValueError('The saved clip is missing, empty or larger than 9 MiB.')
            if self.last.get('sent'):
                return self.status()
            url = self.configured_url()
            if not url:
                raise ValueError('Discord webhook is not configured on the device.')
            self.uploading = True
            self.upload_error = ''
            threading.Thread(target=self.deliver, args=(url, path), daemon=True).start()
            return self.status()

    def deliver(self, url, path):
        try:
            upload_clip(url, path)
            with self.lock:
                self.last['sent'] = True
                try:
                    self.persist()
                except OSError:
                    self.upload_error = 'Sent to Discord, but the delivery receipt could not be saved locally.'
        except UploadError as error:
            with self.lock:
                self.upload_error = str(error)
        except (ValueError, OSError):
            with self.lock:
                self.upload_error = 'Upload not confirmed. Check Discord before retrying; the clip is saved locally.'
        finally:
            with self.lock:
                self.uploading = False

    def close(self):
        self.stop()
        if self.worker:
            self.worker.join(timeout=22)


RECORDINGS = Recordings()
atexit.register(RECORDINGS.close)
