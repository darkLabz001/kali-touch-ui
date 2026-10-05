"""Update failures, live progress, restart recovery, and dependency preflight."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from updater import Updater


class OtaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manager = Updater('https://github.com/example/screen.git', self.root / 'app', self.root / 'state')
        self.old, self.new = 'a' * 40, 'b' * 40
        self.manager.local_sha = lambda: self.old
        self.manager.job = dict(status='running', stage='checking', pct=0, log=[], pid=os.getpid(), id='test')
        self.manager.fetch = Mock(return_value=(0, ''))
        def git(*args, **kwargs):
            if args[0] == 'rev-parse': return 0, self.new
            if args[0] == 'ls-remote': return 0, self.new + '\trefs/heads/main'
            return 0, ''
        self.manager.git = Mock(side_effect=git)
        self.manager.command = Mock(return_value=(0, ''))

    def test_restart_result_survives_backend_restart(self):
        self.manager.run()
        self.assertEqual(self.manager.job['status'], 'restarting')
        restored = Updater(self.manager.repo, self.manager.directory, self.manager.state_directory)
        restored.local_sha = lambda: self.new
        restored.git = Mock(return_value=(0, self.new + '\trefs/heads/main'))
        persisted = json.loads((self.manager.state_directory / 'update.json').read_text())
        persisted['pid'] = -1
        (self.manager.state_directory / 'update.json').write_text(json.dumps(persisted))
        result = restored.status()
        self.assertEqual((result['status'], result['pct'], result['busy']), ('complete', 100, False))
        self.assertTrue(result['up_to_date'])
        self.assertTrue(any(c.args[0][0] == 'systemd-run' for c in self.manager.command.call_args_list))

    def test_syntax_failure_reports_reason_and_rolls_back(self):
        self.manager.command.side_effect = lambda args, *a: (1, 'Unexpected token') if args[0] == 'node' else (0, '')
        self.manager.run()
        self.assertEqual(self.manager.job['status'], 'failed')
        self.assertIn('Unexpected token', self.manager.job['error'])
        self.manager.git.assert_any_call('reset', '--hard', self.old)
        self.assertFalse(any(c.args[0][0] == 'systemd-run' for c in self.manager.command.call_args_list))

    def test_download_failure_never_applies_or_claims_success(self):
        self.manager.fetch.return_value = 1, 'GitHub unreachable'
        self.manager.run()
        self.assertEqual(self.manager.job['status'], 'failed')
        self.assertIn('GitHub unreachable', self.manager.job['error'])
        self.manager.git.assert_not_called()

    def test_missing_node_fails_before_start(self):
        with patch('updater.shutil.which', return_value=None): result = self.manager.start()
        self.assertFalse(result['ok']); self.assertIn('nodejs', result['msg'])
        self.manager.fetch.assert_not_called()

    def test_streamed_git_percentage_is_visible_before_download_finishes(self):
        del self.manager.fetch
        process = Mock(stdout=io.BytesIO(b'Receiving objects: 0%\rReceiving objects: 50%\rReceiving objects: 100%\n'))
        process.wait.return_value = 0
        with patch('updater.subprocess.Popen', return_value=process):
            rc, out = self.manager.fetch()
        self.assertEqual(rc, 0)
        self.assertEqual(self.manager.job['phase_pct'], 100)
        self.assertEqual(self.manager.job['pct'], 65)
        self.assertEqual(self.manager.job['stage'], 'downloading')

    def test_failed_state_write_returns_immediate_error(self):
        self.manager.save = Mock(side_effect=OSError('No space left'))
        with patch('updater.shutil.which', return_value='/usr/bin/node'):
            result = self.manager.start()
        self.assertFalse(result['ok']); self.assertIn('No space left', result['msg'])
        self.assertFalse(self.manager.busy)

    def test_interrupted_update_is_reported_after_restart(self):
        self.manager.save()
        self.manager.local_sha = lambda: self.old
        result = self.manager.status()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('interrupted', result['error'])

    def test_busy_poll_does_not_wait_for_github(self):
        self.manager.busy = True
        self.manager.status()
        self.manager.git.assert_not_called()


if __name__ == '__main__': unittest.main()
