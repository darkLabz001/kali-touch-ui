#!/usr/bin/env python3
"""Domain OSINT from public DNS, RDAP and certificate-transparency services.

Python standard library only. Run with a domain argument, or enter one when
prompted in Kali Touch UI. Reports are saved beside this script in reports/.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

DNS_TYPES = {'A': 1, 'AAAA': 28, 'MX': 15, 'NS': 2, 'TXT': 16, 'CAA': 257}
MAX_RESPONSE = 8 * 1024 * 1024


def domain_name(value):
    value = value.strip()
    if any(ord(c) < 33 for c in value):
        raise ValueError('Enter a domain such as example.org, without spaces.')
    if '://' in value:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            raise ValueError('Use a domain name or an HTTP/HTTPS URL without credentials.')
        value = parsed.hostname or ''
    try:
        value = value.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError:
        raise ValueError('Invalid international domain name.') from None
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError('Enter a domain name, not an IP address.')
    labels = value.split('.')
    if len(value) > 253 or len(labels) < 2 or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
            for label in labels) or labels[-1].isdigit():
        raise ValueError('Enter a valid domain such as example.org.')
    return value


def clean(value):
    return ''.join(c if c.isprintable() else ' ' for c in str(value))


def fetch_json(url, timeout):
    request = Request(url, headers={
        'Accept': 'application/json, application/rdap+json',
        'User-Agent': 'KaliTouch-DomainOSINT/1.0',
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Response exceeds 8 MiB; try a narrower domain.')
    return json.loads(raw)


def lookup(url, timeout, parser):
    try:
        return {'source': url, 'ok': True, **parser(fetch_json(url, timeout))}
    except HTTPError as error:
        message = {404: 'No public record found for this exact domain.',
                   429: 'Service rate limit reached; try again later.'}.get(
                       error.code, 'Service returned HTTP ' + str(error.code))
    except (URLError, OSError, ValueError, TypeError, KeyError) as error:
        message = str(error) or type(error).__name__
    return {'source': url, 'ok': False, 'error': clean(message)}


def parse_dns(data):
    if not isinstance(data, dict) or not isinstance(data.get('Status'), int):
        raise ValueError('Unexpected DNS response.')
    status = data['Status']
    if status not in (0, 3):
        raise ValueError('DNS lookup failed (rcode ' + str(status) + ').')
    return {'rcode': status, 'dnssec_validated': bool(data.get('AD')),
            'records': [r for r in data.get('Answer', []) if isinstance(r, dict)],
            'note': 'Domain does not exist (NXDOMAIN).' if status == 3 else ''}


def parse_rdap(data):
    if not isinstance(data, dict) or data.get('objectClassName') != 'domain':
        raise ValueError('Unexpected registration response.')
    registrars = []
    for entity in data.get('entities', []):
        if not isinstance(entity, dict) or 'registrar' not in entity.get('roles', []):
            continue
        card = entity.get('vcardArray', [])
        if isinstance(card, list) and len(card) > 1 and isinstance(card[1], list):
            registrars.extend(str(row[3]) for row in card[1]
                              if isinstance(row, list) and len(row) > 3 and row[0] == 'fn')
    return {'domain': data.get('ldhName'), 'registrars': registrars,
            'status': data.get('status', []),
            'events': [{'event': e.get('eventAction'), 'date': e.get('eventDate')}
                       for e in data.get('events', []) if isinstance(e, dict)],
            'nameservers': [n.get('ldhName') for n in data.get('nameservers', [])
                            if isinstance(n, dict) and n.get('ldhName')]}


def parse_certificates(data, domain):
    if not isinstance(data, list):
        raise ValueError('Unexpected certificate-transparency response.')
    names = set()
    for record in data:
        if not isinstance(record, dict):
            continue
        for name in str(record.get('name_value', '')).splitlines():
            wildcard = name.startswith('*.')
            try:
                host = domain_name(name[2:] if wildcard else name)
            except ValueError:
                continue
            if host == domain or host.endswith('.' + domain):
                names.add(('*.' if wildcard else '') + host)
    return {'certificate_entries': len(data), 'names': sorted(names),
            'note': 'Historical certificate names; not proof a host is currently live. Wildcards are retained.'}


def run(domain, timeout, limit, output_dir, no_ct=False):
    now = datetime.now(timezone.utc)
    report = {'domain': domain, 'checked_at': now.isoformat(), 'dns': {}}
    lines = []

    def say(text=''):
        text = clean(text)
        print(text, flush=True)
        lines.append(text)

    say('DOMAIN OSINT · ' + domain)
    say('Public sources: Google DNS, RDAP registries, crt.sh')
    say('These services receive the domain you look up.')
    say()
    say('[1/3] DNS records')

    def dns(kind):
        url = 'https://dns.google/resolve?' + urlencode({
            'name': domain, 'type': kind, 'edns_client_subnet': '0.0.0.0/0'})
        return kind, lookup(url, timeout, parse_dns)

    with ThreadPoolExecutor(max_workers=3) as pool:
        for kind, result in pool.map(dns, DNS_TYPES):
            report['dns'][kind] = result
            if not result['ok']:
                say('  ' + kind + ': unavailable — ' + result['error'])
                continue
            records = result['records']
            say('  ' + kind + ': ' + (result['note'] or (str(len(records)) + ' answer(s)')))
            for record in records[:limit]:
                rtype = next((k for k, v in DNS_TYPES.items() if v == record.get('type')), str(record.get('type')))
                say('    ' + rtype + ' ' + clean(record.get('data', ''))[:400])
            if len(records) > limit:
                say('    More answers saved in JSON report.')

    say()
    say('[2/3] Domain registration (RDAP)')
    url = 'https://rdap.org/domain/' + quote(domain, safe='')
    result = report['registration'] = lookup(url, timeout, parse_rdap)
    if result['ok']:
        say('  Registrar: ' + (', '.join(result['registrars']) or 'not published'))
        say('  Status: ' + ', '.join(map(str, result['status'])))
        for event in result['events'][:limit]:
            say('  ' + str(event['event']) + ': ' + str(event['date']))
        for name in result['nameservers'][:limit]:
            say('  NS: ' + name)
    else:
        say('  Unavailable — ' + result['error'])
        say('  RDAP expects the registered domain, e.g. example.org rather than www.example.org.')

    say()
    say('[3/3] Certificate-transparency names')
    if no_ct:
        report['certificates'] = {'ok': False, 'skipped': True, 'note': 'Skipped with --no-ct.'}
        say('  Skipped with --no-ct.')
    else:
        url = 'https://crt.sh/?' + urlencode({'q': '%.' + domain, 'output': 'json'})
        result = report['certificates'] = lookup(url, timeout, lambda data: parse_certificates(data, domain))
        if result['ok']:
            say('  ' + str(len(result['names'])) + ' unique certificate name(s)')
            for name in result['names'][:limit]:
                say('    ' + name)
            if len(result['names']) > limit:
                say('  Remaining names saved in JSON report.')
            say('  ' + result['note'])
        else:
            say('  Unavailable — ' + result['error'])

    sources = list(report['dns'].values()) + [report['registration'], report['certificates']]
    checked = [s for s in sources if not s.get('skipped')]
    successes = sum(bool(s['ok']) for s in checked)
    report['complete'] = successes == len(checked)
    report['sources_succeeded'] = successes
    say()
    say(f'Finished: {successes}/{len(checked)} lookups succeeded' + ('.' if report['complete'] else ' (partial report).'))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = domain + '-' + now.strftime('%Y%m%dT%H%M%S%fZ')
    json_path = output_dir / (stem + '.json')
    text_path = output_dir / (stem + '.txt')
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    say('JSON report: ' + str(json_path))
    say('Text report: ' + str(text_path))
    text_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return 0 if successes else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('domain', nargs='?', help='Domain or HTTPS URL; prompts if omitted')
    parser.add_argument('--timeout', type=int, choices=range(1, 31), default=10, metavar='1..30', help='Network socket timeout in seconds (default: 10)')
    parser.add_argument('--limit', type=int, choices=range(1, 51), default=15, metavar='1..50', help='Maximum records shown per section (default: 15)')
    parser.add_argument('--no-ct', action='store_true', help='Skip certificate-transparency lookup')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent / 'reports', help='Folder for JSON and text reports')
    args = parser.parse_args(argv)
    try:
        domain = domain_name(args.domain if args.domain is not None else input('Enter a domain (for example example.org), then tap Send: '))
        return run(domain, args.timeout, args.limit, args.output_dir.expanduser().absolute(), args.no_ct)
    except (ValueError, EOFError) as error:
        print('Input error:', clean(error), flush=True)
        return 2
    except OSError as error:
        print('Unable to save report:', clean(error), flush=True)
        return 1
    except KeyboardInterrupt:
        print('\nStopped.', flush=True)
        return 130


if __name__ == '__main__':
    sys.exit(main())
