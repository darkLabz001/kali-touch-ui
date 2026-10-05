"""Browser regression test; uses mocked terminal I/O and never runs WiFite.
Run with a Python environment containing Playwright and a Chromium installation.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    sent = []
    starts = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 800, 'height': 480}, has_touch=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('''window.mockStreams=[]; window.EventSource=class {
          constructor(url){this.url=url;window.mockStreams.push(this)} close(){} };''')

        def route(request):
            path = request.request.url.split('http://touch.test', 1)[1]
            if path.startswith('/api/'):
                data = {}
                if path == '/api/tools':
                    data = {'sections': [], 'tools': [], 'launchers': [{'id': 'wifite', 'group': 'WiFi',
                        'label': 'WiFite — auto attack', 'icon': '✱', 'bin': '/usr/sbin/wifite',
                        'root': True, 'exists': True, 'pkg': 'wifite'}]}
                elif path == '/api/term/start':
                    starts.append(request.request.post_data_json)
                    data = {'ok': True, 'running': True}
                elif path == '/api/term/input':
                    sent.append(request.request.post_data_json['data'])
                    data = {'ok': True}
                request.fulfill(json=data)
            else:
                file = ROOT / 'web' / ('index.html' if path == '/' else path.lstrip('/'))
                request.fulfill(path=str(file))

        page.route('http://touch.test/**', route)
        page.goto('http://touch.test/')
        page.locator('.card').first.wait_for()
        page.locator('#boot-splash').evaluate('(e)=>e.remove()')
        page.get_by_text('Wireless', exact=True).click()
        page.get_by_text('WiFite — auto attack', exact=True).click()
        expect(page.locator('body')).to_have_class('terminal-active kbd-open')
        assert starts[-1]['cmd'] == 'sudo -n /usr/sbin/wifite'
        page.evaluate('''window.mockStreams.at(-1).onmessage({data: JSON.stringify(
          'WiFite terminal layout preview\\r\\nSelect an interface:\\r\\n  1. wlan1\\r\\n  2. wlan2\\r\\nEnter selection: ')})''')
        page.wait_for_timeout(250)
        for width, height in ((800, 480), (1024, 600)):
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_timeout(150)
            out = page.locator('#term-out').bounding_box()
            keyboard = page.locator('#kb').bounding_box()
            field = page.locator('#term-in').bounding_box()
            print(f'{width}x{height}: output height={out["height"]}, keyboard height={keyboard["height"]}')
            assert out['height'] >= 145
            assert out['y'] + out['height'] <= field['y']
            assert field['y'] + field['height'] <= keyboard['y'] + 1
            assert keyboard['y'] + keyboard['height'] <= height + 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.evaluate('''[...document.querySelectorAll('.kb-key')].every(e=>{
              const r=e.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight;
            })''')
        page.set_viewport_size({'width': 800, 'height': 480})
        page.locator('.kb-key[data-v="1"]').click()
        page.get_by_role('button', name='Send Enter to terminal').click()
        page.wait_for_timeout(150)
        assert sent[-1] == '1\r'
        expect(page.locator('#kb')).to_be_visible()
        page.locator('.kb-key[data-k="ent"]').click()
        page.wait_for_timeout(100)
        assert sent[-1] == '\r', sent
        page.get_by_role('button', name='^C', exact=True).click()
        page.wait_for_timeout(100)
        assert sent[-1] == '\x03'
        expect(page.locator('#kb')).to_be_visible()
        # Keep older output in view while new lines arrive.
        page.evaluate('tFeed("\\r\\n" + "older line\\r\\n".repeat(100)); document.getElementById("term-out").scrollTop=0')
        page.evaluate('window.mockStreams.at(-1).onmessage({data: JSON.stringify("new line\\r\\n")})')
        assert page.locator('#term-out').evaluate('(e)=>e.scrollTop') == 0
        page.get_by_role('button', name='Toggle terminal keyboard').click()
        expect(page.locator('#kb')).not_to_be_visible()
        page.get_by_role('button', name='Toggle terminal keyboard').click()
        expect(page.locator('#kb')).to_be_visible()
        page.evaluate('document.getElementById("term-out").scrollTop=0')
        page.screenshot(path='/tmp/wifite-terminal-layout.png')
        page.locator('#btn-back').click()
        expect(page.locator('body')).not_to_have_class('terminal-active')
        expect(page.locator('#kb')).not_to_be_visible()
        assert not errors, errors
        browser.close()
    print('PASS: WiFite launch routing, keyboard/output visibility, typing, blank Enter, Ctrl+C, scrolling, toggle, navigation')


if __name__ == '__main__':
    main()
