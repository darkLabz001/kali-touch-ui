"""Verify every menu entry and Back path with mocked APIs; no tools are run."""
import ast
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    values = {}
    for node in ast.parse((ROOT / 'backend/server.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('TOOLS', 'INTERACTIVE', 'SECTIONS'):
            values[node.targets[0].id] = ast.literal_eval(node.value)
    return {'sections': values['SECTIONS'], 'tools': [{'section': s, 'label': label, 'root': root, 'params': []} for s, label, cmd, root in values['TOOLS']],
            'launchers': [{'id': i, 'group': group, 'label': label, 'icon': icon, 'bin': '/usr/bin/' + binary, 'exists': True, 'root': root, 'pkg': pkg}
                          for i, group, label, icon, binary, root, pkg in values['INTERACTIVE']]}


def main():
    data = fixtures()
    writes = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 800, 'height': 480}, has_touch=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('window.EventSource=class {constructor(url){this.url=url;} close(){} };')

        def route(request):
            path = request.request.url.split('http://touch.test', 1)[1].split('?')[0]
            if path.startswith('/api/'):
                if request.request.method == 'POST': writes.append((path, request.request.post_data_json))
                result = {}
                if path == '/api/tools': result = data
                elif path == '/api/payloads': result = {'directory': '/home/kali/payloads', 'scripts': [{'name': 'domain_osint.py', 'size': 9000}, {'name': 'hello.py', 'size': 200}]}
                elif path == '/api/payloads/status': result = {'running': False, 'name': None, 'output': ''}
                elif path == '/api/term/start': result = {'ok': True, 'running': True}
                request.fulfill(json=result)
            else:
                request.fulfill(path=str(ROOT / 'web' / ('index.html' if path == '/' else path.lstrip('/'))))

        page.route('http://touch.test/**', route)
        page.goto('http://touch.test/')
        expect(page.locator('.hub-card')).to_have_count(8)
        page.locator('#boot-splash').evaluate('(e)=>e.remove()')
        for width, height in ((800, 480), (1024, 600)):
            page.set_viewport_size({'width': width, 'height': height})
            assert page.evaluate('''(()=>{let c=document.getElementById('content');return c.scrollHeight<=c.clientHeight && document.documentElement.scrollWidth<=innerWidth})()''')
        page.set_viewport_size({'width': 800, 'height': 480})
        page.screenshot(path='/tmp/touchui-organized-home.png')
        entries = page.evaluate('TouchNavigation.catalogue().map(e=>({id:e.id, category:e.category, group:e.group}))')
        ids = [e['id'] for e in entries]
        assert len(ids) == len(set(ids)), 'Duplicate menu entries'
        for tool in data['tools']: assert 'quick:' + tool['section'] + ':' + tool['label'] in ids
        for tool in data['launchers']: assert 'terminal:' + tool['id'] in ids
        for name in ['showRecon', 'showHunter', 'showRadar']: assert 'app:' + name in ids
        assert next(e for e in entries if e['id'] == 'terminal:theharvester')['category'] == 'osint'
        assert next(e for e in entries if e['id'] == 'terminal:exiftool')['category'] == 'osint'
        assert next(e for e in entries if e['id'] == 'terminal:smbclient')['category'] == 'network'
        visible = []
        for category in ['wireless', 'network', 'osint', 'web', 'passwords', 'entertainment']:
            page.locator(f'[data-category="{category}"]').click()
            for group in page.locator('.hub-tab').all_text_contents():
                page.get_by_role('button', name=group, exact=True).click()
                visible.extend(page.locator('[data-entry]').evaluate_all('(items)=>items.map(e=>e.dataset.entry)'))
            page.locator('#btn-back').click()
            expect(page.locator('.hub-card')).to_have_count(8)
        assert set(visible) == set(ids), 'Some tools cannot be reached through visible groups'
        # Guided tool returns to its task group and selected tab.
        page.locator('[data-category="network"]').click()
        page.get_by_role('button', name='Scanning', exact=True).click()
        page.locator('[data-entry="quick:scan:Nmap Quick"]').click()
        expect(page.locator('.run-page')).to_be_visible()
        page.locator('#btn-back').click()
        expect(page.locator('.hub-tab.selected')).to_have_text('Scanning')
        page.get_by_role('button', name='Home', exact=True).click()
        # Domain OSINT shortcut returns to OSINT; library detail returns to library.
        page.locator('[data-category="osint"]').click()
        page.get_by_role('button', name='Domain & DNS', exact=True).click()
        page.locator('[data-entry="payload:domain_osint.py"]').click()
        expect(page.locator('.payload-page h2')).to_have_text('domain_osint.py')
        page.locator('#btn-back').click()
        expect(page.locator('.hub-page h2')).to_contain_text('OSINT')
        page.locator('#btn-back').click()
        page.locator('[data-category="scripts"]').click()
        page.get_by_text('hello.py', exact=True).click()
        page.locator('#btn-back').click()
        expect(page.locator('.payload-page h2')).to_have_text('Python Payloads')
        page.locator('#btn-back').click()
        expect(page.locator('.hub-card')).to_have_count(8)
        # WiFite opens the same command; leaving it never restarts it.
        page.locator('[data-category="wireless"]').click()
        page.get_by_role('button', name='WiFi apps', exact=True).click()
        page.locator('[data-entry="terminal:wifite"]').click()
        expect(page.locator('#kb')).to_be_visible()
        page.wait_for_timeout(200)
        assert writes[-1] == ('/api/term/start', {'cmd': 'sudo -n /usr/bin/wifite'})
        page.locator('#btn-settings').click()
        page.locator('#btn-back').click()
        expect(page.locator('.hub-page h2')).to_contain_text('Wireless')
        assert len([w for w in writes if w[0] == '/api/term/start']) == 1
        assert not [w for w in writes if w[0] in ('/api/run', '/api/payloads/run')]
        assert not errors, errors
        print(f'PASS: eight home groups fit, all {len(ids)} tools reachable once, classification, payload paths, Back navigation, terminal preserved')
        browser.close()


if __name__ == '__main__':
    main()
