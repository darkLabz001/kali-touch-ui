"""Mock wireless observations; verify associations and target preparation without radio writes."""
from navigation_test import ROOT, fixtures
from playwright.sync_api import sync_playwright, expect


def main():
    ap = {'bssid': 'AA:BB:CC:DD:EE:01', 'essid': '<Lab WiFi>', 'channel': '6', 'power': '-48', 'privacy': 'WPA2'}
    client = {'station': '12:34:56:78:90:AB', 'bssid': ap['bssid'].lower(), 'power': '-61', 'packets': '10'}
    loose = {'station': '12:34:56:78:90:CD', 'bssid': '(not associated)', 'power': '-70', 'probes': 'Lab'}
    data = {'aps': [ap], 'clients': [client, loose]}
    writes, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        for width, height in [(800, 480), (1024, 600), (480, 320)]:
            page = browser.new_page(viewport={'width': width, 'height': height}, has_touch=True)
            page.on('pageerror', lambda e: errors.append(str(e)))
            def route(r):
                path = r.request.url.split('http://127.0.0.1:8080/', 1)[1].split('?')[0]
                if path.startswith('api/'):
                    if r.request.method == 'POST': writes.append(path)
                    result = {}
                    if path == 'api/tools': result = fixtures()
                    elif path == 'api/recon/start': result = {'ok': False, 'msg': 'Connect a USB WiFi adapter.'}
                    elif path == 'api/recon/data': result = data
                    elif path == 'api/recon/state': result = {'running': True, 'iface': 'wlan1mon'}
                    elif path == 'api/recon/log': result = {'log': ''}
                    r.fulfill(json=result)
                else: r.fulfill(path=str(ROOT / 'web' / (path or 'index.html')))
            page.route('http://127.0.0.1:8080/**', route)
            page.goto('http://127.0.0.1:8080/')
            page.locator('#boot-splash').evaluate('(e)=>e.remove()')
            page.evaluate('showRecon()')
            expect(page.locator('.re-chart-network')).to_have_count(1)
            page.locator('.re-chart-network').tap()
            expect(page.locator('.re-chart-reset')).to_have_text('Show all networks')
            page.locator('.re-chart-reset').tap()
            page.get_by_role('button', name='Signal history', exact=True).tap()
            page.evaluate("""() => {
              const ap = reconLast.d.aps[0];
              reconSeries[ap.bssid] = Array.from({length:21}, (_,i)=>({time:Date.now()-60000+i*3000,value:-48+Math.sin(i/3)*4}));
              renderReconGraph();
            }""")
            page.locator('#re-graph').screenshot(path=f'/tmp/recon-signal-{width}x{height}.png')
            assert page.locator('#re-graph').get_attribute('aria-label').endswith('-48 dBm')
            page.get_by_role('button', name='Live channels', exact=True).tap()
            assert 'channel 6' in page.locator('#re-graph').get_attribute('aria-label')
            point = page.evaluate('document.getElementById("re-graph")._reconHits[0]')
            page.locator('#re-graph').tap(position={'x': point['x'], 'y': point['y']})
            expect(page.locator('#re-target')).to_contain_text('<Lab WiFi>')
            page.locator('.re-chart-reset').tap()
            page.evaluate("""() => {
              const base=reconLast.d.aps[0];
              reconLast.d.aps=Array.from({length:30},(_,i)=>({...base,bssid:'AA:BB:CC:DD:EE:'+String(i).padStart(2,'0'),essid:'Lab '+i,channel:String(1+i%11),power:String(-35-i)}));
              renderReconGraph();renderReconLegend();
            }""")
            expect(page.locator('.re-chart-network')).to_have_count(30)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('.re-top').screenshot(path=f'/tmp/recon-live-{width}x{height}.png')
            page.evaluate('(ap) => { reconLast.d.aps=[ap]; renderReconGraph();renderReconLegend(); }', ap)
            page.get_by_role('button', name='▶ SCAN ON', exact=True).tap()
            expect(page.locator('#recon-error')).to_have_text('Connect a USB WiFi adapter.')
            page.wait_for_timeout(3200)
            expect(page.locator('#recon-error')).to_have_text('Connect a USB WiFi adapter.')
            writes.clear()
            page.get_by_role('button', name='NETWORK MAP', exact=True).tap()
            expect(page.locator('.recon-branch')).to_have_count(1)
            expect(page.locator('.recon-leaves button')).to_have_count(1)
            expect(page.locator('.recon-loose button')).to_have_count(1)
            page.locator('.recon-leaves button').tap()
            expect(page.locator('#re-target')).to_contain_text(client['station'])
            page.wait_for_timeout(3200)
            expect(page.locator('.recon-leaves button')).to_have_attribute('aria-pressed', 'true')
            page.get_by_role('button', name='View access point', exact=True).tap()
            expect(page.locator('[data-recon-tab=aps]')).to_have_class('chip on')
            expect(page.locator('#re-target')).to_contain_text('<Lab WiFi>')
            page.get_by_role('button', name='NETWORK MAP', exact=True).tap()
            page.locator('.recon-loose button').tap()
            expect(page.locator('#re-target')).to_contain_text('not observed')
            expect(page.get_by_role('button', name='Open target controls', exact=True)).to_have_count(0)
            page.locator('.recon-leaves button').tap()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'/tmp/recon-map-{width}x{height}.png', full_page=True)
            page.get_by_role('button', name='Open target controls', exact=True).tap()
            expect(page.locator('#deauth-bssid')).to_have_value(ap['bssid'])
            expect(page.locator('#deauth-ch')).to_have_value('6')
            expect(page.locator('#deauth-client')).to_have_value(client['station'])
            assert page.evaluate('reconTimer === null && !reconPageOpen')
            assert not writes, writes
            page.locator('#btn-back').tap()
            expect(page.locator('.hub-card')).to_have_count(8)
            page.close()
        assert not errors, errors
        browser.close()
    print('PASS: associations, unassociated clients, selection refresh, literal names, prepared targets, no radio writes, 3 touch layouts')


if __name__ == '__main__': main()
