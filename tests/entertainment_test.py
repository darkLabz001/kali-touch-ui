"""Exercise real game behavior and Social routing without opening external sites."""
from navigation_test import ROOT, fixtures
from playwright.sync_api import sync_playwright, expect


def main():
    writes, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 800, 'height': 480}, has_touch=True)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.add_init_script('window.EventSource=class {close(){}}; Math.random=()=>0;')
        def route(r):
            path = r.request.url.split('http://127.0.0.1:8080')[1].split('?')[0]
            if path.startswith('/api/'):
                if r.request.method == 'POST': writes.append((path, r.request.post_data_json))
                result = fixtures() if path == '/api/tools' else {'ok': True}
                r.fulfill(json=result)
            else:
                r.fulfill(path=str(ROOT / 'web' / ('index.html' if path == '/' else path.lstrip('/'))))
        page.route('http://127.0.0.1:8080/**', route)
        def social_route(r):
            writes.append(('/api/entertainment/open', r.request.post_data_json))
            r.fulfill(json={'ok': True})
        page.route('http://127.0.0.1:8082/**', social_route)
        page.goto('http://127.0.0.1:8080/')
        expect(page.locator('.hub-card')).to_have_count(8)
        page.locator('#boot-splash').evaluate('(e)=>e.remove()')
        page.clock.install()
        page.locator('[data-category=entertainment]').tap()
        expect(page.locator('[data-entry]')).to_have_count(2)
        page.screenshot(path='/tmp/entertainment-menu.png')
        page.locator('[data-entry="game:snake"]').tap()
        for width, height in ((800, 480), (1024, 600)):
            page.set_viewport_size({'width': width, 'height': height})
            assert page.evaluate('''[...document.querySelectorAll('.ent-page button, .ent-snake')].every(e=>{
                const r=e.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight;})''')
        page.set_viewport_size({'width': 800, 'height': 480})
        page.get_by_role('button', name='Start', exact=True).tap()
        page.clock.run_for(320)
        page.get_by_role('button', name='Pause', exact=True).tap()
        board = page.locator('canvas').evaluate('(e)=>e.toDataURL()')
        page.clock.run_for(3000)
        assert page.locator('canvas').evaluate('(e)=>e.toDataURL()') == board, 'Pause must freeze the game'
        page.get_by_role('button', name='Resume', exact=True).tap()
        page.clock.run_for(3000)
        expect(page.get_by_role('status')).to_contain_text('Game over')
        page.get_by_role('button', name='New game').tap()
        # Food is at 0,0 under the deterministic random seed. Turn via touch controls.
        page.get_by_role('button', name='Up', exact=True).tap()
        page.get_by_role('button', name='Start', exact=True).tap()
        page.clock.run_for(800)
        page.get_by_role('button', name='Left', exact=True).tap()
        page.clock.run_for(640)
        page.get_by_role('button', name='Pause', exact=True).tap()
        expect(page.locator('.ent-score')).to_have_text('Score 10 · Best 10')
        page.screenshot(path='/tmp/entertainment-snake.png')
        canvas = page.locator('canvas').element_handle()
        page.get_by_role('button', name='Resume', exact=True).tap()
        old = canvas.evaluate('(e)=>e.toDataURL()')
        page.locator('#btn-back').tap()
        page.clock.run_for(3200)
        assert canvas.evaluate('(e)=>e.toDataURL()') == old, 'Leaving must stop the timer'
        expect(page.locator('.hub-tab.selected')).to_have_text('Games')
        page.locator('[data-entry="game:snake"]').tap()
        expect(page.locator('.ent-score')).to_have_text('Score 0 · Best 10')
        page.locator('#btn-back').tap()
        page.locator('[data-entry="game:memory"]').tap()
        symbols = list('ABCDEFGHABCDEFGH')
        for i in range(15, 0, -1): symbols[i], symbols[0] = symbols[0], symbols[i]
        pairs = [[i for i, s in enumerate(symbols) if s == symbol] for symbol in 'ABCDEFGH']
        a, b = pairs[0][0], pairs[1][0]
        page.locator(f'[data-card="{a}"]').tap(); page.locator(f'[data-card="{b}"]').tap()
        expect(page.get_by_role('status')).to_have_text('Try another pair')
        page.clock.run_for(750)
        expect(page.locator(f'[data-card="{a}"]')).to_have_text('?')
        for pair in pairs:
            for index in pair: page.locator(f'[data-card="{index}"]').tap()
        expect(page.get_by_role('status')).to_have_text('All pairs found in 9 moves!')
        expect(page.locator('.ent-memory-card:disabled')).to_have_count(16)
        page.screenshot(path='/tmp/entertainment-memory.png')
        page.get_by_role('button', name='New game').tap()
        expect(page.locator('.ent-memory-card:disabled')).to_have_count(0)
        expect(page.locator('.ent-score')).to_have_text('Pairs 0/8 · Moves 0')
        page.locator('#btn-back').tap()
        page.get_by_role('button', name='Social', exact=True).tap()
        for site, title in [('discord', 'Discord'), ('reddit', 'Reddit'), ('youtube', 'YouTube')]:
            page.locator(f'[data-entry="social:{site}"]').tap()
            assert not writes or writes[-1][1]['site'] != site, 'Opening a card must not open the browser'
            page.get_by_role('button', name='Open ' + title, exact=True).tap()
            expect(page.get_by_role('status')).to_contain_text('Browser opened')
            assert writes[-1] == ('/api/entertainment/open', {'site': site})
            page.locator('#btn-back').tap()
            expect(page.locator('.hub-tab.selected')).to_have_text('Social')
        assert len(writes) == 3 and not errors, (writes, errors)
        browser.close()
    print('PASS: touch fit, Snake movement/food/collision/pause/best/cleanup, full Memory game/reset, Social explicit launch and Back')


if __name__ == '__main__':
    main()
