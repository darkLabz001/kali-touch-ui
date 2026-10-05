import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'web_surface_mapper', Path(__file__).resolve().parents[1] / 'payloads/web_surface_mapper.py')
mapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mapper)


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append(self.path)
        if self.path == '/':
            body = '''<title>Fixture &amp; App</title><a href="/linked#section">linked</a>
                <a href="/linked">duplicate</a><a href="/redirect">redirect</a>
                <script src="/app.js"></script><a href="/external">external redirect</a>
                <a href="https://outside.invalid/path">outside</a>
                <form action="/session" method="post"><input name="user">
                <input name="password" type="password" value="DO_NOT_SAVE"></form>'''
            return self.respond(200, body)
        if self.path == '/robots.txt':
            return self.respond(200, 'Disallow: /hidden\nSitemap: /extra.xml', 'text/plain')
        if self.path in ('/sitemap.xml', '/extra.xml'):
            return self.respond(200, '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>/mapped</loc></url></urlset>', 'application/xml')
        if self.path == '/app.js':
            return self.respond(200, 'fetch("/api/users"); const dynamic = `/api/${id}`;', 'application/javascript')
        if self.path == '/redirect':
            return self.respond(302, '', location='/linked')
        if self.path == '/external':
            return self.respond(302, '', location=self.server.external_url)
        if self.path == '/cycle':
            return self.respond(302, '', location='/cycle')
        if self.path == '/limited':
            return self.respond(429, 'Slow down')
        if self.path == '/large':
            return self.respond(200, 'x' * (mapper.MAX_BODY + 20), 'text/plain')
        if self.path == '/private':
            return self.respond(403, 'Denied')
        if self.path == '/gone':
            return self.respond(404, 'Gone')
        if self.path in ('/linked', '/hidden', '/mapped', '/api/users'):
            return self.respond(200, '<title>Found ' + self.path + '</title>')
        return self.respond(200, '<title>Missing</title>No route for ' + self.path)

    def respond(self, status, body, content_type='text/html', location=None):
        raw = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        if location:
            self.send_header('Location', location)
        self.end_headers()
        self.wfile.write(raw)


class WebSurfaceMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.external = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        cls.external.requests = []
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        cls.server.requests = []
        cls.server.external_url = f'http://127.0.0.1:{cls.external.server_port}/should-not-fetch'
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.threads = []
        for server in (cls.server, cls.external):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.server, cls.external):
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join()

    def setUp(self):
        self.server.requests.clear()
        self.external.requests.clear()

    def scan(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return mapper.Mapper(self.base, delay=0, **kwargs).run()

    def test_crawl_routes_forms_deduplication_and_scope(self):
        report = self.scan(paths=())
        urls = {r['url']: r for r in report['results']}
        for path in ('/linked', '/hidden', '/mapped', '/api/users'):
            self.assertIn(self.base + path, urls)
        self.assertEqual(self.server.requests.count('/linked'), 1)
        self.assertFalse(self.external.requests)
        self.assertFalse(urls[self.base + '/external']['redirect_in_scope'])
        self.assertIn(self.server.external_url, report['excluded_external_urls'])
        self.assertEqual(urls[self.base + '/']['title'], 'Fixture & App')
        self.assertTrue(urls[self.base + '/']['login_candidate'])
        self.assertEqual(report['forms'][0]['method'], 'POST')
        self.assertNotIn('/session', self.server.requests)
        self.assertNotIn('DO_NOT_SAVE', json.dumps(report))
        self.assertFalse(any('${' in path for path in self.server.requests))

    def test_soft_404_restricted_missing_and_redirect_cycle(self):
        report = self.scan(paths=('made-up', 'private', 'gone', 'cycle'))
        results = {r['url']: r for r in report['results']}
        self.assertEqual(results[self.base + '/made-up']['assessment'], 'possible wildcard / soft 404')
        self.assertIn('existence unconfirmed', results[self.base + '/private']['assessment'])
        self.assertEqual(results[self.base + '/gone']['assessment'], 'not found')
        self.assertEqual(self.server.requests.count('/cycle'), 1)

    def test_budget_depth_and_body_cap(self):
        report = self.scan(max_requests=5, paths=())
        self.assertEqual(report['requests'], 5)
        self.assertEqual(len(self.server.requests), 5)
        self.assertGreater(report['pending_urls'], 0)
        report = self.scan(depth=0, paths=('large',))
        self.assertNotIn(self.base + '/linked', [r['url'] for r in report['results']])
        large = next(r for r in report['results'] if r['url'].endswith('/large'))
        self.assertTrue(large['truncated'])
        self.assertEqual(large['bytes_read'], mapper.MAX_BODY)

    def test_rate_limit_stops_requests(self):
        report = self.scan(paths=('limited', 'must-not-fetch'))
        self.assertEqual(report['results'][-1]['status'], 429)
        self.assertNotIn('/must-not-fetch', self.server.requests)
        self.assertGreater(report['pending_urls'], 0)
        self.assertEqual(report['stop_reason'], 'rate limited')

    def test_baseline_rate_limit_stops_before_target(self):
        with patch.object(mapper.Mapper, 'fetch', return_value=(
                {'url': self.base, 'status': 429, 'source': 'baseline'}, 'Slow down')) as fetch:
            report = self.scan()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(report['stop_reason'], 'rate limited')

    def test_malformed_html_base_does_not_abort_scan(self):
        scanner = mapper.Mapper(self.base, delay=0)
        result = {'url': self.base + '/', 'content_type': 'text/html'}
        scanner.discover(result, '<base href="http://["><a href="/linked">link</a>', 0)
        self.assertEqual(scanner.queue[0][0], self.base + '/linked')

    def test_interactive_entry_reports_and_custom_wordlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / 'paths.txt'
            wordlist.write_text('# Comment\nprivate\nhttps://outside.invalid/skip\n', encoding='utf-8')
            with patch('builtins.input', return_value=self.base), contextlib.redirect_stdout(io.StringIO()):
                result = mapper.main(['--delay', '0', '--wordlist', str(wordlist), '--output-dir', tmp])
            self.assertEqual(result, 0)
            report = json.loads(next(Path(tmp).glob('*.json')).read_text())
            self.assertEqual(report['target'], self.base + '/')
            self.assertTrue(list(Path(tmp).glob('web-surface-*.txt')))
            self.assertIn('/private', self.server.requests)
            self.assertNotIn('/admin/', self.server.requests)

    def test_url_normalization_rejects_credentials_and_bad_schemes(self):
        self.assertEqual(mapper.normalize_url('HTTP://EXAMPLE.org:80/a#fragment'), 'http://example.org/a')
        self.assertEqual(mapper.normalize_url('http://[::1]:8080/'), 'http://[::1]:8080/')
        for url in ('file:///etc/passwd', 'https://user:pass@example.org',
                    'https://example.org:bad/', 'https://example.org/a\n', 'https://example.org\\@other.test'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                mapper.normalize_url(url)

    def test_network_failure_still_saves_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mapper.Mapper, 'fetch', return_value=(
                {'url': self.base, 'status': None, 'source': 'target', 'error': 'offline'}, '')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapper.main([self.base, '--max-requests', '5', '--output-dir', tmp]), 1)
            self.assertTrue(list(Path(tmp).glob('*.json')))


if __name__ == '__main__':
    unittest.main()
