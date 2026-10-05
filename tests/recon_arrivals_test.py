"""Verify fresh signal samples, arrival baseline/deduplication, and touch layouts."""
from navigation_test import ROOT, fixtures
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    errors = []
    for width, height in [(800,480),(480,800)]:
        page = browser.new_page(viewport={'width':width,'height':height}, has_touch=True)
        page.on('pageerror', lambda e: errors.append(str(e)))
        def route(r):
            path=r.request.url.split('http://127.0.0.1:8080/',1)[1].split('?')[0]
            if path.startswith('api/'):
                data = fixtures() if path=='api/tools' else {'running':False} if path=='api/recon/state' else {'aps':[],'clients':[]} if path=='api/recon/data' else {'log':''}
                r.fulfill(json=data)
            else: r.fulfill(path=str(ROOT/'web'/(path or 'index.html')))
        page.route('http://127.0.0.1:8080/**',route)
        page.goto('http://127.0.0.1:8080/')
        page.locator('#boot-splash').evaluate('(e)=>e.remove()')
        page.evaluate('showRecon()')
        page.wait_for_timeout(150)
        page.evaluate('''() => {
            clearInterval(reconTimer); reconTimer=null;
            const now=Date.now();
            const ap={bssid:'AA:BB:CC:DD:EE:01',essid:'Baseline',channel:'6',power:'-45',last:new Date(now).toISOString()};
            reconLast={st:{running:true},d:{aps:[ap],clients:[]},lg:{log:''}};
            reconSample();
            if(reconArrivals.length) throw Error('Baseline announced');
            reconLast.d.aps.push({...ap,bssid:'AA:BB:CC:DD:EE:02',essid:'<New WiFi>',channel:'11'});
            reconLast.d.clients.push({station:'12:34:56:78:90:AB',bssid:ap.bssid});
            reconSample(); reconSample();
            if(reconArrivals.length!==2) throw Error('Duplicate or missing arrivals');
            if(reconWaterfall[0].aps.length!==2) throw Error('Missing fresh samples');
            reconLast.d.aps.forEach(ap=>ap.last=new Date(now-60000).toISOString());
            reconSample();
            if(reconWaterfall[0].aps.length) throw Error('Stale observations drawn live');
        }''')
        expect(page.locator('.re-arrival')).to_have_count(2)
        expect(page.locator('#re-arrival-feed')).to_contain_text('<New WiFi>')
        page.get_by_role('button',name='Waterfall',exact=True).tap()
        assert 'WiFi signal waterfall' in page.locator('#re-graph').get_attribute('aria-label')
        page.get_by_role('button',name='5 GHz',exact=True).tap()
        assert page.evaluate('reconGraphView')=='waterfall'
        page.get_by_role('button',name='2.4 GHz',exact=True).tap()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=f'/tmp/recon-waterfall-{width}x{height}.png',full_page=True)
        page.locator('.re-arrival').filter(has_text='<New WiFi>').tap()
        expect(page.locator('#re-target')).to_contain_text('<New WiFi>')
        page.evaluate('''() => {
            reconLast.st.running=false; reconSample();
            reconLast.st.running=true; reconSample();
            if(reconArrivals.length || reconWaterfall.length!==1) throw Error('New session retained arrivals/history');
            leaveRecon();
        }''')
        page.close()
    assert not errors,errors
    browser.close()
print('PASS: baseline, AP/client arrival deduplication, freshness, session reset, band selection, touch layouts')
