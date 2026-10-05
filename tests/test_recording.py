"""Recording lifecycle and mocked Discord transport; nothing is sent to Discord."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import recording
import device
from test_device import Handler

HOOK = 'https://discord.com/api/webhooks/12345/' + 'test-token_' * 5
CLIP = 'recording-20260923-063000-1234abcd.mp4'


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.options = kwargs
        self.done = threading.Event()
        self.stdin = io.BytesIO()
        self.returncode = 0
        Path(command[-1]).write_bytes(b'test mp4 bytes')

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.returncode


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'webhook'
        self.config.write_text(HOOK + '/github')
        self.manager = recording.Recordings(self.root / 'clips', self.config)

    def saved_clip(self):
        self.manager.directory.mkdir()
        clip = self.manager.directory / CLIP
        clip.write_bytes(b'clip bytes')
        self.manager.last = {'filename': CLIP, 'duration': 3, 'sent': False}
        self.manager.persist()
        return clip

    def wait_upload(self):
        deadline = time.monotonic() + 2
        while self.manager.uploading and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.manager.uploading)

    def test_webhook_validation_and_github_adapter(self):
        self.assertEqual(recording.webhook_url(HOOK + '/github'), HOOK)
        for value in ('http://discord.com/api/webhooks/123/token', HOOK + '?x=y',
                      HOOK.replace('discord.com', 'discord.com.evil.test'),
                      HOOK.replace('discord.com', 'user@discord.com'), HOOK + '/slack',
                      'file:///etc/passwd'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recording.webhook_url(value)
        self.assertTrue(self.manager.status()['discord_configured'])
        self.assertNotIn('test-token', json.dumps(self.manager.status()))

    def test_capture_stop_finalize_private_file_and_restore_latest(self):
        processes = []
        def popen(command, **kwargs):
            proc = FakeProcess(command, **kwargs)
            processes.append(proc)
            return proc
        def run(command, **kwargs):
            output = 'Screen 0: minimum 8 x 8, current 800 x 480, maximum 4096 x 4096' if command[0] == 'xrandr' else '{"format":{"duration":"3.25"}}'
            return subprocess.CompletedProcess(command, 0, output, '')
        with patch.object(recording.shutil, 'which', return_value='/usr/bin/tool'), patch.object(recording.subprocess, 'Popen', side_effect=popen), patch.object(recording.subprocess, 'run', side_effect=run), patch.object(recording, 'upload_clip') as upload:
            self.assertEqual(self.manager.start()['state'], 'recording')
            with self.assertRaises(ValueError):
                self.manager.start()
            self.assertEqual(self.manager.stop()['state'], 'stopping')
            proc = processes[0]
            self.assertEqual(proc.stdin.getvalue(), b'q\n')
            proc.done.set()
            self.manager.worker.join(2)
            self.assertEqual(self.manager.status()['state'], 'ready')
            self.assertEqual(proc.options['umask'], 0o077)
            self.assertIn('-an', proc.command)
            self.assertIn(str(recording.MAX_SECONDS), proc.command)
            self.assertNotIn('shell', proc.options)
            self.assertEqual(Path(self.manager.status()['last']['path']).stat().st_mode & 0o777, 0o600)
            upload.assert_not_called()
        restored = recording.Recordings(self.manager.directory, self.config)
        self.assertEqual(restored.status()['last']['filename'], self.manager.last['filename'])

    def test_failed_encoder_preserves_earlier_clip(self):
        self.saved_clip()
        command = ['ffmpeg', str(self.manager.directory / 'failed.mp4')]
        proc = FakeProcess(command)
        proc.returncode = 1
        proc.done.set()
        self.manager.proc = proc
        self.manager.finish(proc, Path(command[-1]), io.BytesIO())
        self.assertEqual(self.manager.state, 'error')
        self.assertEqual(self.manager.last['filename'], CLIP)
        self.assertIsNone(self.manager.proc)

    def test_send_requires_explicit_clip_and_prevents_duplicates(self):
        clip = self.saved_clip()
        with patch.object(recording, 'upload_clip') as upload:
            self.manager.status()
            upload.assert_not_called()
            for value in ('/etc/passwd', '../secret', 'other.mp4', None):
                with self.assertRaises(ValueError):
                    self.manager.send(value)
            self.manager.send(CLIP)
            self.wait_upload()
            self.manager.send(CLIP)
            upload.assert_called_once_with(HOOK, clip)
        self.assertTrue(self.manager.last['sent'])
        self.assertTrue(recording.Recordings(self.manager.directory, self.config).last['sent'])

    def test_send_rejects_oversize_and_symlink(self):
        clip = self.saved_clip()
        with clip.open('wb') as handle:
            handle.truncate(recording.MAX_BYTES + 1)
        with self.assertRaises(ValueError):
            self.manager.send(CLIP)
        clip.unlink()
        clip.symlink_to(self.config)
        with self.assertRaises(ValueError):
            self.manager.send(CLIP)

    def test_upload_uses_multipart_and_wait_without_mentions(self):
        clip = self.saved_clip()
        with patch.object(recording, 'build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"id":"123"}'
            recording.upload_clip(HOOK, clip)
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, HOOK + '?wait=true')
            self.assertIn(b'name="files[0]"', request.data)
            self.assertIn(b'"allowed_mentions": {"parse": []}', request.data)
            self.assertIn(b'clip bytes', request.data)

    def test_upload_errors_are_secret_free_and_preserve_local_clip(self):
        clip = self.saved_clip()
        for error in (URLError(HOOK), HTTPError(HOOK, 429, 'limited', {}, None), HTTPError(HOOK, 413, 'too large', {}, None)):
            with patch.object(recording, 'build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(recording.UploadError) as raised:
                    recording.upload_clip(HOOK, clip)
                self.assertNotIn('test-token', str(raised.exception))
        with patch.object(recording, 'upload_clip', side_effect=recording.UploadError('Discord rate limit reached.')):
            self.manager.send(CLIP)
            self.wait_upload()
        self.assertIn('rate limit', self.manager.upload_error)
        self.assertTrue(clip.exists())
        self.assertFalse(self.manager.last['sent'])

    def test_upload_in_progress_blocks_new_recording_and_resend(self):
        self.saved_clip()
        self.manager.uploading = True
        with self.assertRaises(ValueError):
            self.manager.send(CLIP)
        with self.assertRaises(ValueError):
            self.manager.start()

    def test_recording_endpoint_and_controls_keep_origin_boundary(self):
        for path in ('/api/device/recording', '/api/device/control'):
            handler = Handler({'action': 'record_start'}, origin='https://example.org')
            with patch.object(device.RECORDINGS, 'start') as start:
                device.handle_device_request(handler, 'POST', path)
                self.assertEqual(handler.status, 403)
                start.assert_not_called()
        with patch.object(device, 'RECORDINGS', self.manager), patch.object(self.manager, 'start') as start:
            handler = Handler()
            device.handle_device_request(handler, 'GET', '/api/device/recording')
            self.assertEqual(handler.status, 200)
            start.assert_not_called()
            self.assertNotIn('test-token', json.dumps(handler.body))


if __name__ == '__main__':
    unittest.main()
