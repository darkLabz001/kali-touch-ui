"""User-installed Python scripts, kept outside the application checkout."""
import atexit
import codecs
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import uuid

MAX_SCRIPT = 1024 * 1024
MAX_OUTPUT = 32768


class PayloadError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class PayloadManager:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get(
            'TOUCHUI_PAYLOADS_DIR', str(Path.home() / 'payloads'))).expanduser().absolute()
        self.lock = threading.RLock()
        self.proc = None
        self.run_id = None
        self.name = None
        self.output = ''
        self.exit_code = None
        self.running = False
        self.stopping = False

    def path(self, name):
        if (not isinstance(name, str) or not name or len(name.encode()) > 240
                or name.startswith('.') or '/' in name or '\\' in name
                or any(ord(c) < 32 for c in name) or not name.endswith('.py')):
            raise PayloadError('Choose a Python filename ending in .py, without folders.')
        path = self.directory / name
        if path.is_symlink():
            raise PayloadError('Symbolic links are not supported.')
        return path

    def listing(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        scripts = []
        for item in sorted(self.directory.iterdir(), key=lambda p: p.name.casefold()):
            try:
                path = self.path(item.name)
                if path.is_file():
                    scripts.append({'name': item.name, 'size': path.stat().st_size})
            except (PayloadError, OSError):
                continue
        return {'directory': str(self.directory), 'scripts': scripts}

    def upload(self, name, source):
        path = self.path(name)
        if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_SCRIPT:
            raise PayloadError('Python files must be UTF-8 text, at most 1 MiB.')
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            # Exclusive creation also refuses an existing file or symlink.
            with path.open('x', encoding='utf-8') as f:
                f.write(source)
        except FileExistsError:
            raise PayloadError('That filename already exists. Rename the file before uploading.', 409)
        return {'ok': True, 'name': name}

    def start(self, name, arguments=''):
        path = self.path(name)
        if not path.is_file():
            raise PayloadError('Script not found. Refresh the payload list.', 404)
        if not isinstance(arguments, str) or len(arguments) > 4096:
            raise PayloadError('Arguments must be text, at most 4096 characters.')
        try:
            args = shlex.split(arguments)
        except ValueError as e:
            raise PayloadError(str(e))
        if any('\0' in arg for arg in args):
            raise PayloadError('Arguments cannot contain NUL characters.')
        with self.lock:
            if self.running:
                raise PayloadError('A payload is already running. Stop it first.', 409)
            proc = subprocess.Popen(
                [sys.executable, '-u', str(path), *args], cwd=self.directory,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                start_new_session=True, env=dict(os.environ, PYTHONUNBUFFERED='1'))
            os.set_blocking(proc.stdin.fileno(), False)
            self.proc = proc
            self.run_id = uuid.uuid4().hex
            self.name = name
            self.output = ''
            self.exit_code = None
            self.running = True
            self.stopping = False
            threading.Thread(target=self._read, args=(proc,), daemon=True).start()
            return self.status()

    def _read(self, proc):
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        try:
            while True:
                data = os.read(proc.stdout.fileno(), 4096)
                if not data:
                    break
                with self.lock:
                    self.output = (self.output + decoder.decode(data))[-MAX_OUTPUT:]
            with self.lock:
                self.output = (self.output + decoder.decode(b'', final=True))[-MAX_OUTPUT:]
        finally:
            code = proc.wait()
            proc.stdout.close()
            proc.stdin.close()
            with self.lock:
                self.exit_code = code
                self.running = False
                self.stopping = False

    def status(self):
        with self.lock:
            return {'ok': True, 'run_id': self.run_id, 'name': self.name,
                    'running': self.running, 'stopping': self.stopping,
                    'exit_code': self.exit_code, 'output': self.output}

    def _check_run(self, run_id):
        if not run_id or run_id != self.run_id or not self.running:
            raise PayloadError('This payload is no longer running.', 409)

    def send_input(self, run_id, text):
        if not isinstance(text, str) or len(text.encode()) > 4095:
            raise PayloadError('Input must be text, at most 4095 bytes.')
        with self.lock:
            self._check_run(run_id)
            try:
                data = (text + '\n').encode()
                if os.write(self.proc.stdin.fileno(), data) != len(data):
                    raise PayloadError('Input buffer is full. Wait before sending more.', 409)
            except (BrokenPipeError, BlockingIOError, ValueError):
                raise PayloadError('The script is not accepting input.', 409)
        return {'ok': True}

    @staticmethod
    def _signal(proc, sig):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass

    def stop(self, run_id):
        with self.lock:
            self._check_run(run_id)
            proc = self.proc
            self.stopping = True
            self._signal(proc, signal.SIGTERM)
            threading.Thread(target=self._finish_stop, args=(proc,), daemon=True).start()
        return {'ok': True}

    def _finish_stop(self, proc):
        # Kill the whole group, including children that ignore TERM or retain stdout.
        threading.Event().wait(1)
        self._signal(proc, signal.SIGKILL)

    def close(self):
        with self.lock:
            if self.running:
                self._signal(self.proc, signal.SIGKILL)


PAYLOADS = PayloadManager()
atexit.register(PAYLOADS.close)


def handle_payload_request(handler, method, path):
    """Return True when this request belongs to the payload API."""
    if path != '/api/payloads' and not path.startswith('/api/payloads/'):
        return False
    try:
        if method == 'GET' and path == '/api/payloads':
            result = PAYLOADS.listing()
        elif method == 'GET' and path == '/api/payloads/status':
            result = PAYLOADS.status()
        elif method == 'POST':
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_SCRIPT * 6 + 4096:
                handler.close_connection = True
                raise PayloadError('Invalid request size.', 413)
            body = json.loads(handler.rfile.read(length))
            if not isinstance(body, dict):
                raise PayloadError('Expected a JSON object.')
            if path == '/api/payloads/upload':
                result = PAYLOADS.upload(body.get('name'), body.get('source'))
            elif path == '/api/payloads/run':
                result = PAYLOADS.start(body.get('name'), body.get('arguments', ''))
            elif path == '/api/payloads/stop':
                result = PAYLOADS.stop(body.get('run_id'))
            elif path == '/api/payloads/input':
                result = PAYLOADS.send_input(body.get('run_id'), body.get('text'))
            else:
                raise PayloadError('Not found.', 404)
        else:
            raise PayloadError('Not found.', 404)
        code = 200
    except PayloadError as e:
        code, result = e.status, {'ok': False, 'error': str(e)}
    except (ValueError, UnicodeError):
        code, result = 400, {'ok': False, 'error': 'Invalid JSON request.'}
    except OSError as e:
        code, result = 500, {'ok': False, 'error': e.strerror or 'Unable to access payloads.'}
    handler._send(code, json.dumps(result).encode())
    return True
