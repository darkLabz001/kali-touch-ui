"""User-visible OTA phases, failures, retry, and progress at both screen sizes."""
from navigation_test import ROOT, fixtures
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        for width, height in [(800, 480), (480, 800)]:
            page = browser.new_page(viewport={'width': width, 'height': height}, has_touch=True)
            errors, starts = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            status = dict(installed=True, up_to_date=False, local_short='aaaaaaa', remote='b'*40, remote_short='bbbbbbb', busy=False, status='idle', log='')
            def route(r):
                path = r.request.url.split('http://127.0.0.1:8080/', 1)[1].split('?')[0]
                if path.startswith('api/'):
                    result = {}
                    if path == 'api/tools': result = fixtures()
                    elif path == 'api/ota/status': result = dict(status)
                    elif path == 'api/ota/update':
                        starts.append(True)
                        status.update(busy=True, status='running', stage='checking', pct=0, message='Checking installation')
                        result = {'ok': True, 'msg': 'Update started', 'job_id': 'test'}
                    r.fulfill(json=result)
                else: r.fulfill(path=str(ROOT / 'web' / (path or 'index.html')))
            page.route('http://127.0.0.1:8080/**', route)
            page.goto('http://127.0.0.1:8080/')
            page.locator('#boot-splash').evaluate('(e)=>e.remove()')
            page.locator('#btn-settings').tap()
            card = page.locator('#ota-card')
            update = card.get_by_role('button', name='⬇ Update', exact=True)
            expect(update).to_be_enabled()
            update.tap(); page.get_by_role('button', name='Tap again to confirm', exact=True).tap()
            bar = card.get_by_role('progressbar')
            expect(bar).to_be_visible(); expect(bar).to_have_attribute('aria-valuenow', '0')
            status.update(stage='downloading', pct=36, phase_pct=47, message='Downloading update')
            expect(card.locator('.ota-meta')).to_contain_text('47% downloaded')
            expect(bar).to_have_attribute('aria-valuenow', '36')
            assert bar.bounding_box()['height'] >= 20
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            card.screenshot(path=f'/tmp/ota-progress-{width}x{height}.png')
            status.update(busy=False, status='failed', stage='failed', error='JavaScript check failed: nodejs missing. Previous version restored.', pct=80)
            expect(card.locator('.ota-meta')).to_contain_text('Previous version restored')
            expect(card.get_by_role('button', name='↻ Retry update', exact=True)).to_be_enabled()
            expect(bar).to_have_attribute('data-stage', 'failed')
            assert not errors, errors
            assert len(starts) == 1
            page.close()
        browser.close()
    print('PASS: visible progress, live percentage, persistent failure, retry, 7-inch and 4-inch layouts')


if __name__ == '__main__': main()
