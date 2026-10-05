import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

spec = importlib.util.spec_from_file_location('domain_osint', Path(__file__).resolve().parents[1] / 'payloads/domain_osint.py')
osint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(osint)


class DomainOsintTests(unittest.TestCase):
    def test_domain_normalization_and_rejection(self):
        self.assertEqual(osint.domain_name('https://EXAMPLE.org/path?q=1'), 'example.org')
        self.assertEqual(osint.domain_name('BÜCHER.de.'), 'xn--bcher-kva.de')
        for value in ('127.0.0.1', '::1', '../etc/passwd', 'example..org', 'localhost',
                      'example.org;id', 'https://user:pass@example.org', 'ftp://example.org',
                      'a' * 64 + '.org', 'example.org\x1b[31m'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                osint.domain_name(value)

    def test_certificate_scope_deduplication_and_wildcards(self):
        records = [{'name_value': 'EXAMPLE.org\n*.example.org\nmail.example.org\nnotexample.org\nexample.org.evil.test'},
                   {'name_value': 'mail.example.org\nother.org\n*.deep.example.org'}]
        result = osint.parse_certificates(records, 'example.org')
        self.assertEqual(result['names'], ['*.deep.example.org', '*.example.org', 'example.org', 'mail.example.org'])
        with self.assertRaises(ValueError):
            osint.parse_certificates({'error': 'unavailable'}, 'example.org')

    def test_dns_negative_and_errors_are_distinct(self):
        result = osint.parse_dns({'Status': 3})
        self.assertEqual(result['records'], [])
        self.assertIn('NXDOMAIN', result['note'])
        self.assertEqual(osint.parse_dns({'Status': 0})['note'], '')
        with self.assertRaises(ValueError):
            osint.parse_dns({'Status': 2})
        with self.assertRaises(ValueError):
            osint.parse_dns([])

    def test_registrar_extraction(self):
        result = osint.parse_rdap({'objectClassName': 'domain', 'ldhName': 'EXAMPLE.ORG',
            'entities': [{'roles': ['registrar'], 'vcardArray': ['vcard', [['fn', {}, 'text', 'Example Registrar']]]}],
            'events': [{'eventAction': 'registration', 'eventDate': '2000-01-01T00:00:00Z'}],
            'nameservers': [{'ldhName': 'ns.example.org'}]})
        self.assertEqual(result['registrars'], ['Example Registrar'])
        self.assertEqual(result['nameservers'], ['ns.example.org'])
        self.assertEqual(result['events'][0]['event'], 'registration')

    def test_partial_report_survives_service_failure(self):
        def fake(url, timeout):
            if 'dns.google' in url:
                return {'Status': 0, 'Answer': [{'name': 'example.org.', 'type': 1, 'data': '192.0.2.1'}]}
            raise URLError('test service unavailable')
        with tempfile.TemporaryDirectory() as tmp, patch.object(osint, 'fetch_json', side_effect=fake), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(osint.run('example.org', 2, 2, Path(tmp)), 0)
            report = json.loads(next(Path(tmp).glob('*.json')).read_text())
            self.assertFalse(report['complete'])
            self.assertEqual(report['sources_succeeded'], 6)
            self.assertFalse(report['certificates']['ok'])
            self.assertIn('partial report', next(Path(tmp).glob('*.txt')).read_text())

    def test_interactive_input_and_total_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch('builtins.input', return_value='example.org'), patch.object(osint, 'fetch_json', side_effect=TimeoutError('offline')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(osint.main(['--no-ct', '--output-dir', tmp]), 1)
            report = json.loads(next(Path(tmp).glob('*.json')).read_text())
            self.assertEqual(report['sources_succeeded'], 0)
            self.assertTrue(report['certificates']['skipped'])

    def test_response_size_and_terminal_control_characters(self):
        with patch.object(osint, 'urlopen') as mocked:
            mocked.return_value.__enter__.return_value.read.return_value = b'x' * (osint.MAX_RESPONSE + 1)
            with self.assertRaises(ValueError):
                osint.fetch_json('https://example.org', 1)
        self.assertNotIn('\x1b', osint.clean('bad\x1b[31mvalue'))


if __name__ == '__main__':
    unittest.main()
