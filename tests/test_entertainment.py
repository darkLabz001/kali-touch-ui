"""Validate the local launch boundary without creating desktop processes."""
import io
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import entertainment


class Handler:
    def __init__(self, body=b'{"site":"discord"}', origin='http://127.0.0.1:8080', address='127.0.0.1'):
        self.headers = {'Host': '127.0.0.1:8082', 'Origin': origin, 'Content-Type': 'application/json', 'Content-Length': str(len(body))}
        self.client_address = (address, 1234)
        self.rfile = io.BytesIO(body)
    def _send(self, code, data):
        self.code, self.data = code, data


class LaunchBoundary(unittest.TestCase):
    def test_rejects_remote_browser_and_foreign_origin(self):
        for handler in [Handler(address='192.168.1.10'), Handler(origin='https://example.org'), Handler(origin='null')]:
            with patch.object(entertainment.subprocess, 'Popen') as spawn:
                entertainment.handle_entertainment_request(handler, '/api/entertainment/open')
                self.assertEqual(handler.code, 403)
                spawn.assert_not_called()
    def test_rejects_arbitrary_commands_urls_and_invalid_json(self):
        for body in [b'{"site":"https://example.org"}', b'{"site":"$(touch /tmp/test)"}', b'[]', b'null', b'{', b'{"site":[]}']:
            handler = Handler(body=body)
            with patch.object(entertainment.subprocess, 'Popen') as spawn:
                entertainment.handle_entertainment_request(handler, '/api/entertainment/open')
                self.assertEqual(handler.code, 400)
                spawn.assert_not_called()
    def test_rejects_duplicate_browser(self):
        handler = Handler()
        with patch.object(entertainment, '_process') as process, patch.object(entertainment.subprocess, 'Popen') as spawn:
            process.poll.return_value = None
            entertainment.handle_entertainment_request(handler, '/api/entertainment/open')
            self.assertEqual(handler.code, 409)
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
