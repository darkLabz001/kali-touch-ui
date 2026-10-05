import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from payloads import PayloadError, PayloadManager, MAX_SCRIPT


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'payloads'
        self.manager = PayloadManager(self.root)

    def tearDown(self):
        self.manager.close()
        if self.manager.proc:
            self.wait(lambda: not self.manager.status()['running'])
        self.tmp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.025)
        self.fail('Timed out waiting for payload')

    def test_discovery_and_upload_do_not_execute(self):
        self.assertEqual(self.manager.listing()['scripts'], [])
        self.manager.upload('hello world.py', "print('hello')")
        (self.root / 'ignore.txt').write_text('not a script')
        (self.root / 'folder.py').mkdir()
        (self.root / 'link.py').symlink_to(self.root / 'hello world.py')
        self.assertEqual([x['name'] for x in self.manager.listing()['scripts']], ['hello world.py'])
        self.assertFalse(self.manager.status()['running'])
        with self.assertRaises(PayloadError):
            self.manager.upload('hello world.py', 'replacement')
        self.assertEqual((self.root / 'hello world.py').read_text(), "print('hello')")

    def test_path_and_upload_validation(self):
        for name in ('../escape.py', '/tmp/escape.py', 'folder/file.py', '.hidden.py', 'x.sh', 'x\0.py', 'a\\b.py', None):
            with self.subTest(name=name), self.assertRaises(PayloadError):
                self.manager.upload(name, '')
        with self.assertRaises(PayloadError):
            self.manager.upload('big.py', 'x' * (MAX_SCRIPT + 1))
        with self.assertRaises(PayloadError):
            self.manager.start('missing.py')

    def test_output_arguments_cwd_exit_and_input(self):
        self.manager.upload('hello world.py', 'import json,sys,os\nprint(json.dumps(sys.argv[1:]))\nprint(os.getcwd())\nprint("stderr",file=sys.stderr)\nprint("prompt>",end="",flush=True)\nprint(input())\nsys.exit(7)\n')
        run = self.manager.start('hello world.py', '"two words" "; touch injected"')
        self.wait(lambda: 'prompt>' in self.manager.status()['output'])
        with self.assertRaises(PayloadError):
            self.manager.start('hello world.py')
        with self.assertRaises(PayloadError):
            self.manager.send_input('stale-run', 'wrong')
        self.manager.send_input(run['run_id'], 'hello input')
        self.wait(lambda: not self.manager.status()['running'])
        status = self.manager.status()
        self.assertEqual(status['exit_code'], 7)
        self.assertIn('["two words", "; touch injected"]', status['output'])
        self.assertIn(str(self.root), status['output'])
        self.assertIn('stderr', status['output'])
        self.assertIn('hello input', status['output'])
        self.assertFalse((self.root / 'injected').exists())

    def test_bounded_output_and_syntax_errors(self):
        self.manager.upload('large.py', 'print("x" * 100000)\n')
        self.manager.start('large.py')
        self.wait(lambda: not self.manager.status()['running'])
        self.assertLessEqual(len(self.manager.status()['output']), 32768)
        self.manager.upload('broken.py', 'def invalid syntax')
        self.manager.start('broken.py')
        self.wait(lambda: not self.manager.status()['running'])
        self.assertNotEqual(self.manager.status()['exit_code'], 0)
        self.assertIn('SyntaxError', self.manager.status()['output'])

    def test_stop_kills_children_even_if_they_ignore_term(self):
        source = '''import subprocess,sys,time,signal
signal.signal(signal.SIGTERM,signal.SIG_IGN)
p = subprocess.Popen([sys.executable,'-u','-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("child-ready",flush=True); time.sleep(60)'])
print('child-pid',p.pid,flush=True)
time.sleep(60)
'''
        self.manager.upload('long.py', source)
        run = self.manager.start('long.py')
        self.wait(lambda: 'child-ready' in self.manager.status()['output'])
        self.manager.stop(run['run_id'])
        self.wait(lambda: not self.manager.status()['running'])
        self.assertEqual(self.manager.status()['exit_code'], -signal.SIGKILL)
        self.manager.start('long.py')
        with self.assertRaises(PayloadError):
            self.manager.stop(run['run_id'])


if __name__ == '__main__':
    unittest.main()
