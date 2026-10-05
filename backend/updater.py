"""Git updates with streamed progress and a result that survives service restarts."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time


class Updater:
    def __init__(self, repo, directory='/opt/kali-touch-ui', state_directory=None):
        self.repo, self.directory = repo, Path(directory)
        self.state_directory = Path(state_directory) if state_directory else Path.home() / '.local/state/kali-touch-ui'
        self.lock = threading.RLock()
        self.busy = False
        self.job = None
        self.remote = ''
        self.checked_at = -60

    def command(self, args, timeout=30):
        argv = list(args) if os.geteuid() == 0 else ['sudo', '-n'] + list(args)
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                               env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
            return p.returncode, (p.stdout + p.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)

    def git(self, *args, timeout=30):
        return self.command(['git', '-C', str(self.directory), *args], timeout)

    def local_sha(self):
        rc, out = self.git('rev-parse', 'HEAD')
        return out if not rc and re.fullmatch('[0-9a-f]{40}', out) else ''

    def load(self):
        if self.job is None:
            try:
                self.job = json.loads((self.state_directory / 'update.json').read_text())
                if not isinstance(self.job, dict): raise ValueError('Invalid update state')
            except (OSError, ValueError):
                self.job = {'status': 'idle', 'stage': 'idle', 'pct': 0, 'message': '', 'log': []}
        return self.job

    def save(self):
        self.state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.state_directory / 'update.tmp'
        temporary.write_text(json.dumps(self.job))
        temporary.chmod(0o600)
        temporary.replace(self.state_directory / 'update.json')

    def progress(self, stage, pct, message, **fields):
        with self.lock:
            self.load().update(stage=stage, pct=pct, message=message, updated_at=time.time(), **fields)
            self.job['log'] = (self.job.get('log', []) + [message])[-40:]
            self.save()

    def status(self, force=False):
        with self.lock:
            job = dict(self.load())
            busy = self.busy
        local = self.local_sha()
        if not busy and job.get('status') in ('running', 'restarting'):
            if job.get('status') == 'restarting' and job.get('pid') != os.getpid() and local == job.get('target'):
                self.progress('done', 100, 'Update installed successfully.', status='complete', error='')
            elif job.get('status') == 'running' or time.time() - job.get('updated_at', 0) > 90:
                self.progress('failed', job.get('pct', 0), 'Update interrupted. Tap Retry to try again.', status='failed', error='Update interrupted.')
            job = dict(self.load())
        if not busy and job.get('status') != 'restarting' and (force or time.monotonic() - self.checked_at > 60):
            rc, out = self.git('ls-remote', self.repo, 'refs/heads/main')
            self.remote = out.split()[0] if not rc and out.split() else ''
            self.checked_at = time.monotonic()
        remote = self.remote or job.get('target', '') if busy else self.remote
        return dict(version='1.4.3', installed=bool(local), method='git' if local else 'none',
                    local=local, local_short=local[:7], remote=remote, remote_short=remote[:7],
                    up_to_date=bool(remote) and remote == local, busy=busy or job.get('status') == 'restarting',
                    status=job.get('status', 'idle'), stage=job.get('stage'), pct=job.get('pct'),
                    phase_pct=job.get('phase_pct'), message=job.get('message', ''), error=job.get('error', ''),
                    log='\n'.join(job.get('log', [])), job_id=job.get('id'), store_changed=job.get('status') == 'complete')

    def start(self):
        with self.lock:
            if self.busy or self.load().get('status') == 'restarting':
                return {'ok': False, 'msg': 'An update is already running.'}
            if not shutil.which('node'):
                return {'ok': False, 'msg': 'JavaScript validation needs nodejs. Install nodejs on the device, then retry.'}
            self.job = dict(id=str(time.time_ns()), status='running', stage='checking', pct=0,
                            message='Checking installation…', log=[], pid=os.getpid(), updated_at=time.time(), error='')
            try:
                self.save()
            except OSError as error:
                self.job.update(status='failed', stage='failed', error=str(error), message='Cannot save update status: ' + str(error))
                return {'ok': False, 'msg': self.job['message']}
            self.busy = True
            threading.Thread(target=self.run, daemon=True).start()
            return {'ok': True, 'msg': 'Update started.', 'job_id': self.job['id']}

    def fetch(self):
        args = ['git', '-C', str(self.directory), 'fetch', '--progress', self.repo,
                '+refs/heads/main:refs/remotes/touchui-update/main']
        if os.geteuid() != 0: args = ['sudo', '-n'] + args
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=dict(os.environ, GIT_TERMINAL_PROMPT='0'), start_new_session=True)
        timeout = threading.Timer(120, lambda: self.command(['kill', '-KILL', '--', str(-proc.pid)], timeout=5))
        timeout.start()
        try:
            recent, fragment, last_pct = b'', b'', -1
            while True:
                chunk = proc.stdout.read1(4096)
                if not chunk: break
                recent = (recent + chunk)[-8192:]
                fragment += chunk
                lines = re.split(b'[\r\n]', fragment)
                fragment = lines.pop()[-4096:]
                for line in lines:
                    match = re.search(rb'Receiving objects:\s+(\d+)%', line)
                    if match and int(match[1]) != last_pct:
                        last_pct = int(match[1])
                        self.progress('downloading', 10 + round(last_pct * .55), 'Downloading update…', phase_pct=last_pct)
            rc = proc.wait()
            return rc, recent.decode(errors='replace')
        finally:
            timeout.cancel()
            proc.stdout.close()

    def run(self):
        old, applied = '', False
        try:
            old = self.local_sha()
            if not old: raise ValueError('Installation is not a Git checkout. OTA is unavailable.')
            self.progress('downloading', 10, 'Downloading from GitHub…', phase_pct=None)
            rc, out = self.fetch()
            if rc: raise ValueError('Download failed: ' + out[-400:])
            rc, target = self.git('rev-parse', 'refs/remotes/touchui-update/main')
            if rc or not re.fullmatch('[0-9a-f]{40}', target): raise ValueError('Cannot identify the downloaded update.')
            self.remote = target
            self.progress('applying', 70, 'Applying downloaded files…', target=target, phase_pct=None)
            if old == target:
                self.progress('done', 100, 'Already up to date.', status='complete')
                return
            rc, out = self.git('reset', '--hard', target)
            if rc: raise ValueError('Could not apply update: ' + out[-300:])
            applied = True
            self.progress('verifying', 80, 'Checking JavaScript and Python…')
            rc, out = self.command(['node', '--check', str(self.directory / 'web/assets/app.js')])
            if rc: raise ValueError('JavaScript check failed: ' + out[-400:])
            paths = [str(p) for p in (self.directory / 'backend').glob('*.py')]
            code = 'import ast,sys; [ast.parse(open(p, encoding="utf-8").read(), filename=p) for p in sys.argv[1:]]'
            rc, out = self.command([sys.executable, '-c', code, *paths])
            if rc: raise ValueError('Python check failed: ' + out[-400:])
            self.progress('configuring', 90, 'Preparing device services…')
            for args in [
                ['install', '-m', '0644', str(self.directory / 'scripts/touchui-entertainment.service'), '/etc/systemd/system/touchui-entertainment.service'],
                ['systemctl', 'daemon-reload'], ['systemctl', 'enable', 'touchui-entertainment'],
                ['chmod', '+x', str(self.directory / 'scripts/kiosk.sh'), str(self.directory / 'scripts/kali-touch-session')],
            ]:
                rc, out = self.command(args)
                if rc: raise ValueError('Service setup failed: ' + out[-300:])
            self.progress('restarting', 95, 'Restarting touchscreen services…', status='restarting')
            restart = "sleep 2; systemctl restart touchui-entertainment kali-touchui; pkill -u kali -f 'chrom[i]um.*--app=http://127.0.0.1:8080' || true"
            rc, out = self.command(['systemd-run', '--collect', '--quiet', '--no-block', 'sh', '-c', restart])
            if rc: raise ValueError('Service restart failed: ' + out[-300:])
        except Exception as error:
            message = str(error)
            if applied and old:
                rc, out = self.git('reset', '--hard', old)
                message += ' Previous version restored.' if not rc else ' Rollback failed: ' + out[-200:]
            try:
                self.progress('failed', self.load().get('pct', 0), message, status='failed', error=message)
            except OSError:
                self.load().update(status='failed', stage='failed', message=message, error=message)
        finally:
            self.busy = False
