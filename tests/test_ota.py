"""Exercise the updater alone, with Git and service restarts mocked."""
import pathlib
import re
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / 'backend/server.py').read_text()
BLOCK = SOURCE.split('# ---------------- OTA update ----------------')[1].split('class Handler(')[0]


class OtaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ns = dict(os=__import__('os'), re=re, time=time, threading=threading, subprocess=Mock())
        exec(BLOCK, self.ns)
        self.ns['OTA_LOG'] = str(pathlib.Path(self.tmp.name) / 'ota.log')
        self.old, self.new = 'a' * 40, 'b' * 40
        self.ns['ota_local_sha'] = lambda: self.old

    def test_download_uses_same_repo_as_check_and_applies_fetched_commit(self):
        commands = []
        def shell(cmd, timeout=60):
            commands.append(cmd)
            return (0, self.new) if 'rev-parse refs/remotes/touchui-update/' in cmd else (0, '')
        self.ns['_ota_sh'] = shell
        self.ns['_ota_run']()
        repo = self.ns['OTA_REPO']
        self.assertTrue(repo.endswith('/kali-touch-ui.git'))
        self.assertTrue(any('fetch --progress ' + repo in cmd for cmd in commands))
        self.assertIn('git -C /opt/kali-touch-ui reset --hard ' + self.new, commands)
        self.assertFalse(any('origin/' in cmd for cmd in commands))
        self.assertIn('touchui-entertainment kali-touchui', self.ns['subprocess'].Popen.call_args.args[0])

    def test_failed_fetch_and_non_git_install_never_restart(self):
        for installed in (True, False):
            with self.subTest(installed=installed):
                self.ns['ota_local_sha'] = lambda: self.old if installed else ''
                self.ns['_ota_sh'] = Mock(return_value=(1, 'offline'))
                self.ns['_ota_run']()
                self.ns['subprocess'].Popen.assert_not_called()
                self.assertFalse(self.ns['_ota_busy'])

    def test_validation_failure_rolls_back_without_restart(self):
        def shell(cmd, timeout=60):
            if 'rev-parse refs/remotes/' in cmd: return 0, self.new
            if 'node --check' in cmd: return 1, 'bad syntax'
            return 0, ''
        self.ns['_ota_sh'] = Mock(side_effect=shell)
        self.ns['_ota_run']()
        self.assertTrue(any('reset --hard ' + self.old in c.args[0] for c in self.ns['_ota_sh'].call_args_list))
        self.ns['subprocess'].Popen.assert_not_called()


if __name__ == '__main__': unittest.main()
