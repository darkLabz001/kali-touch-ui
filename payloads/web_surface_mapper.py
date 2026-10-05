#!/usr/bin/env python3
"""Map a website's pages, scripts, forms and common exposed paths.

Python standard library only. GET requests stay on the supplied origin; forms
are inventoried but never submitted. Reports contain metadata, not response bodies.
"""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
from html import escape
from html.parser import HTMLParser
from http.client import HTTPException
import json
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
import uuid
import xml.etree.ElementTree as ET

MAX_BODY = 256 * 1024
MAX_CANDIDATES = 2000
COMMON_PATHS = (
    'admin/', 'administrator/', 'login', 'signin', 'dashboard/', 'wp-login.php',
    'api/', 'api/v1/', 'api/v2/', 'graphql', 'swagger/', 'swagger.json',
    'openapi.json', 'api-docs/', 'docs/', '.well-known/security.txt',
    'backup/', 'backups/', 'backup.zip', 'site.zip', 'index.php.bak',
    'config.php.bak', '.git/HEAD', '.env', 'server-status',
)
SKIP_EXTENSIONS = re.compile(r'\.(?:png|jpe?g|gif|svg|ico|webp|woff2?|ttf|mp[34]|pdf|css)(?:$)', re.I)
JS_ROUTE = re.compile(r'''["'`]((?:https?://|/|\./|\.\./)[^\s"'`<>\\]{1,500})["'`]''')


def clean(value):
    return ''.join(c if c.isprintable() else ' ' for c in str(value))


def normalize_url(value):
    if not value or len(value) > 4096 or any(ord(c) < 33 or c == '\\' for c in value):
        raise ValueError('Use an HTTP/HTTPS URL without spaces or control characters.')
    parts = urlsplit(value)
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError('Use an HTTP/HTTPS URL without embedded credentials.')
    host = parts.hostname.encode('idna').decode('ascii').lower()
    port = parts.port
    if ':' in host:
        host = '[' + host + ']'
    if port is not None and port != (443 if parts.scheme.lower() == 'https' else 80):
        host += ':' + str(port)
    return urlunsplit((parts.scheme.lower(), host,
                      quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~"),
                      quote(parts.query, safe="/%?:@!$&'()*+,;=-._~"), ''))


def origin(url):
    parts = urlsplit(url)
    return parts.scheme, parts.netloc


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.forms = []
        self.current_form = None
        self.base = None
        self.title = ''
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base' and self.base is None:
            self.base = attrs.get('href')
        if tag == 'title':
            self.in_title = True
        if tag in ('a', 'iframe', 'script'):
            value = attrs.get('href' if tag == 'a' else 'src')
            if value:
                self.links.append((value, 'javascript' if tag == 'script' else 'link'))
        if tag == 'form':
            self.current_form = {'action': attrs.get('action', ''),
                                 'method': attrs.get('method', 'GET').upper(), 'fields': []}
            self.forms.append(self.current_form)
        if tag in ('input', 'select', 'textarea', 'button') and self.current_form is not None:
            self.current_form['fields'].append({'name': attrs.get('name', ''),
                                               'type': attrs.get('type', tag)})

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'form':
            self.current_form = None

    def handle_data(self, data):
        if self.in_title:
            self.title += data


class Mapper:
    def __init__(self, target, max_requests=60, depth=2, timeout=8, delay=0.2,
                 insecure=False, paths=COMMON_PATHS):
        self.target = normalize_url(target)
        self.scope = origin(self.target)
        self.root = urlunsplit((*self.scope, '/', '', ''))
        self.max_requests = max_requests
        self.depth = depth
        self.timeout = timeout
        self.delay = delay
        self.insecure = insecure
        self.paths = paths
        self.requests = 0
        self.last_request = None
        self.queue = deque()
        self.seen = set()
        self.results = []
        self.forms = []
        self.excluded = set()
        self.baselines = []
        self.rate_limited = False
        self.candidate_limit_reached = False
        context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        # Direct requests keep environment proxy settings from changing scan routing.
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def resolve(self, value, base):
        try:
            url = normalize_url(urljoin(base, value))
        except (ValueError, UnicodeError):
            return None
        if origin(url) != self.scope:
            if len(self.excluded) < MAX_CANDIDATES:
                self.excluded.add(url)
            return None
        return url

    def enqueue(self, value, base, source, depth=0):
        url = self.resolve(value, base)
        if url is None or url in self.seen or depth > self.depth:
            return
        if len(self.seen) >= MAX_CANDIDATES:
            self.candidate_limit_reached = True
            return
        if source in ('link', 'javascript-route') and SKIP_EXTENSIONS.search(urlsplit(url).path):
            return
        self.seen.add(url)
        self.queue.append((url, source, depth))

    def fetch(self, url, source):
        if self.last_request is not None:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        self.requests += 1
        result = {'url': url, 'source': source, 'status': None}
        body = ''
        try:
            request = Request(url, headers={'User-Agent': 'KaliTouch-WebSurfaceMapper/1.0',
                                           'Accept-Encoding': 'identity'})
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                result['status'] = response.code
                result['content_type'] = response.headers.get_content_type()
                result['location'] = response.headers.get('Location', '')
                result['server'] = response.headers.get('Server', '')
                raw = response.read(MAX_BODY + 1)
                result['bytes_read'] = min(len(raw), MAX_BODY)
                result['truncated'] = len(raw) > MAX_BODY
                encoding = response.headers.get_content_charset() or 'utf-8'
                try:
                    body = raw[:MAX_BODY].decode(encoding, errors='replace')
                except LookupError:
                    body = raw[:MAX_BODY].decode('utf-8', errors='replace')
        except (URLError, OSError, ValueError, HTTPException) as error:
            result['error'] = clean(error)
        return result, body

    @staticmethod
    def fingerprint(result, body):
        # Normalize reflected paths before comparing generic error pages.
        path = urlsplit(result['url']).path
        for value in (result['url'], escape(result['url']), path, escape(path)):
            if value != '/':
                body = body.replace(value, '<requested-path>')
        return result['status'], hashlib.sha256(body.encode()).hexdigest()

    def discover(self, result, body, depth):
        url = result['url']
        kind = result.get('content_type', '')
        if kind in ('text/html', 'application/xhtml+xml'):
            page = PageParser()
            page.feed(body)
            result['title'] = clean(' '.join(page.title.split()))[:200]
            try:
                base = normalize_url(urljoin(url, page.base)) if page.base else url
            except (ValueError, UnicodeError):
                base = url
            for value, source in page.links:
                self.enqueue(value, base, source, depth + 1)
            for form in page.forms:
                try:
                    form['action'] = normalize_url(urljoin(base, form['action']) if form['action'] else url)
                except (ValueError, UnicodeError):
                    continue
                form['page'] = url
                form['in_scope'] = origin(form['action']) == self.scope
                form['login_candidate'] = any(f['type'].lower() == 'password' for f in form['fields'])
                self.forms.append(form)
            if any(f['login_candidate'] for f in self.forms if f['page'] == url):
                result['login_candidate'] = True
        if 'javascript' in kind or urlsplit(url).path.endswith('.js'):
            for value in JS_ROUTE.findall(body):
                if '${' not in value:
                    self.enqueue(value, url, 'javascript-route', depth + 1)
        if urlsplit(url).path == '/robots.txt':
            for line in body.splitlines():
                key, sep, value = line.partition(':')
                value = value.split('#', 1)[0].strip()
                if sep and value and key.strip().lower() in ('allow', 'disallow', 'sitemap') and '*' not in value and '$' not in value:
                    self.enqueue(value, url, 'robots', depth + 1)
        if 'xml' in kind or urlsplit(url).path.endswith('.xml'):
            try:
                tree = ET.fromstring(body)
                for item in tree.iter():
                    if item.tag.rsplit('}', 1)[-1] == 'loc' and item.text:
                        self.enqueue(item.text.strip(), url, 'sitemap', depth + 1)
            except ET.ParseError:
                pass

    def run(self):
        print('WEB SURFACE MAPPER · ' + self.target, flush=True)
        print(f'GET only · same origin · at most {self.max_requests} requests', flush=True)
        # Two shapes catch common SPA fallback pages and extension-specific errors.
        for suffix in ('/', '.bak'):
            url = urljoin(self.root, '__touchui_missing_' + uuid.uuid4().hex + suffix)
            result, body = self.fetch(url, 'baseline')
            if 'error' not in result:
                self.baselines.append(self.fingerprint(result, body))
            result['assessment'] = 'missing-path baseline'
            self.results.append(result)
            if result['status'] == 429:
                self.rate_limited = True
                print('Server rate limit reached during baseline checks; stopping.', flush=True)
                break
        self.enqueue(self.target, self.root, 'target')
        self.enqueue('robots.txt', self.root, 'robots')
        self.enqueue('sitemap.xml', self.root, 'sitemap')
        for path in self.paths:
            self.enqueue(path, self.root, 'common-path')
        while self.queue and self.requests < self.max_requests and not self.rate_limited:
            url, source, depth = self.queue.popleft()
            result, body = self.fetch(url, source)
            status = result['status']
            if 'error' in result:
                assessment = 'request failed'
            elif status in (404, 410):
                assessment = 'not found'
            elif self.fingerprint(result, body) in self.baselines:
                assessment = 'possible wildcard / soft 404'
            elif status in (401, 403):
                assessment = 'access restricted; existence unconfirmed'
            elif 300 <= status < 400:
                assessment = 'redirect'
            elif 200 <= status < 300:
                assessment = 'responded; review required'
            else:
                assessment = 'HTTP error / other response'
            result['assessment'] = assessment
            if assessment == 'redirect' and result.get('location'):
                destination = self.resolve(result['location'], url)
                result['redirect_in_scope'] = destination is not None
                if destination:
                    self.enqueue(destination, url, 'redirect', depth)
            if status is not None and 200 <= status < 300 and 'error' not in result and assessment != 'possible wildcard / soft 404':
                self.discover(result, body, depth)
            self.results.append(result)
            print(clean(f'[{self.requests}/{self.max_requests}] {status or "ERR"} {url} — {assessment}'), flush=True)
            if status == 429:
                self.rate_limited = True
                print('Server rate limit reached; stopping with a partial report.', flush=True)
                break
        return {'target': self.target, 'checked_at': datetime.now(timezone.utc).isoformat(),
                'settings': {'max_requests': self.max_requests, 'depth': self.depth,
                             'timeout': self.timeout, 'delay': self.delay, 'verify_tls': not self.insecure},
                'requests': self.requests, 'pending_urls': len(self.queue),
                'stop_reason': 'rate limited' if self.rate_limited else ('request budget reached' if self.queue else 'queue exhausted'),
                'candidate_limit_reached': self.candidate_limit_reached,
                'results': self.results, 'forms': self.forms,
                'excluded_external_urls': sorted(self.excluded),
                'limitations': ['Path checks use the origin root, even when the starting URL has a subpath.',
                                'Static parsing only; JavaScript is not executed and forms are not submitted.',
                                'GET requests can still trigger application side effects.',
                                'Soft-404 detection is heuristic; responses are not confirmed vulnerabilities.',
                                'Response reads are capped at 256 KiB; no response bodies or form values are saved.']}


def save_report(report, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    host = re.sub(r'[^a-zA-Z0-9.-]', '_', urlsplit(report['target']).netloc)
    stem = 'web-surface-' + host + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    json_path = output_dir / (stem + '.json')
    text_path = output_dir / (stem + '.txt')
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['WEB SURFACE MAPPER', report['target'], report['checked_at'],
             f"Requests: {report['requests']} · Queued but unchecked: {report['pending_urls']}",
             'Stopped: ' + report['stop_reason'], '', 'RESPONSES']
    for row in report['results']:
        lines.append(f"{row['status'] or 'ERR'} {row['url']} — {row['assessment']}")
        for key in ('title', 'location', 'error'):
            if row.get(key):
                lines.append('  ' + key + ': ' + row[key])
    lines.extend(['', 'FORMS (not submitted)'])
    for form in report['forms']:
        lines.append(f"{form['method']} {form['action']} · page: {form['page']} · login candidate: {form['login_candidate']}")
        lines.append('  Fields: ' + ', '.join(f["name"] + ' (' + f['type'] + ')' for f in form['fields']))
    lines.extend(['', 'LIMITATIONS', *report['limitations']])
    text_path.write_text('\n'.join(clean(line) for line in lines) + '\n', encoding='utf-8')
    print(f"Finished: {report['requests']} requests · {len(report['forms'])} forms · {report['pending_urls']} URLs left unchecked", flush=True)
    print('JSON report: ' + str(json_path), flush=True)
    print('Text report: ' + str(text_path), flush=True)


def bounded_float(low, high):
    def parse(value):
        number = float(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f'Choose a value from {low} to {high}.')
        return number
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', nargs='?', help='Starting HTTP/HTTPS URL; prompts if omitted')
    parser.add_argument('--max-requests', type=int, choices=range(5, 501), default=60, metavar='5..500')
    parser.add_argument('--depth', type=int, choices=range(0, 6), default=2)
    parser.add_argument('--timeout', type=bounded_float(1, 30), default=8)
    parser.add_argument('--delay', type=bounded_float(0, 10), default=0.2, help='Minimum seconds between requests (default: 0.2)')
    parser.add_argument('--insecure', action='store_true', help='Allow untrusted TLS certificates for lab targets')
    parser.add_argument('--wordlist', type=Path, help='Replace built-in paths with up to 1000 UTF-8 paths, one per line')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent / 'reports')
    args = parser.parse_args(argv)
    try:
        target = args.url if args.url is not None else input('Enter a website URL, then tap Send: ').strip()
        paths = COMMON_PATHS
        if args.wordlist:
            with args.wordlist.expanduser().open(encoding='utf-8') as handle:
                paths = []
                for line in handle:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if len(line) > 4096 or len(paths) >= 1000:
                            raise ValueError('Wordlist limit: 1000 paths, at most 4096 characters each.')
                        paths.append(line)
        mapper = Mapper(target, args.max_requests, args.depth, args.timeout, args.delay, args.insecure, paths)
        report = mapper.run()
        save_report(report, args.output_dir.expanduser().absolute())
        return 0 if any(r['source'] != 'baseline' and r['status'] is not None and 'error' not in r for r in report['results']) else 1
    except (ValueError, UnicodeError, EOFError) as error:
        print('Input error: ' + clean(error), flush=True)
        return 2
    except OSError as error:
        print('File error: ' + clean(error), flush=True)
        return 1
    except KeyboardInterrupt:
        print('\nStopped.', flush=True)
        return 130


if __name__ == '__main__':
    sys.exit(main())
