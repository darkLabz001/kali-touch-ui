"""Mock every device write; exercise dashboard, gestures and existing keyboard."""
import time
from navigation_test import ROOT, fixtures
from playwright.sync_api import sync_playwright, expect


def main():
    writes, errors, status_calls = [], [], []
    brightness, volume, muted = 100, 40, False
    fail_status = False
    recording = {'supported': True, 'state': 'idle', 'elapsed': 0, 'max_seconds': 120,
                 'last': None, 'discord_configured': True, 'uploading': False, 'error': '', 'upload_error': ''}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':800,'height':480},has_touch=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script('window.EventSource=class {close(){}};')
        def route(r):
            nonlocal brightness, volume, muted
            path=r.request.url.split('http://127.0.0.1:',1)[1].split('/',1)[1].split('?')[0]
            if path.startswith('api/'):
                result={}
                if r.request.method=='POST': writes.append((path,r.request.post_data_json))
                if path=='api/tools': result=fixtures()
                elif path=='api/sysinfo': result={'ssid':'Test network','ip':'192.0.2.1','temp':'55.2'}
                elif path=='api/network': result={'info':{'hostname':'test-device','ip':'192.0.2.1'}}
                elif path=='api/wifi/scan': result={'error':'test scan unavailable'}
                elif path=='api/device/recording': result=dict(recording)
                elif path.endswith(('/status','/state')): result={'running':False}
                if path=='api/term/status': result={'running':True}
                if path=='api/device/status':
                    status_calls.append(time.monotonic())
                    if fail_status: r.fulfill(status=503,json={'error':'unavailable'}); return
                    result={'sampled_at':time.time(),'cpu_percent':32,'temperature_c':55.2,'uptime_seconds':7200,
                      'memory':{'total':4*1024**3,'used':1024**3},'storage':{'total':64*1024**3,'used':10*1024**3,'free':54*1024**3},
                      'network':{'interface':'wlan0','rx_bps':180000+len(status_calls)*1000,'tx_bps':20000},
                      'wireless':[{'interface':'wlan0','signal_dbm':-61,'quality':72}],
                      'controls':{'brightness':{'supported':True,'value':brightness,'minimum':10},'volume':{'supported':True,'value':volume,'muted':muted},'screenshot':True}}
                if path=='api/device/control':
                    body=r.request.post_data_json; action=body['action']; value=body.get('value')
                    if action=='brightness': brightness=value
                    if action=='volume': volume=value
                    if action=='mute': muted=value
                    result={'ok':True,'result':{'value':value,'muted':muted,'path':'/home/kali/Pictures/KaliTouch/test.png'}}
                    if action=='record_start':
                        recording.update(state='recording',elapsed=3)
                    elif action=='record_stop':
                        recording.update(state='ready',elapsed=0,last={'filename':'recording-20260923-063000-1234abcd.mp4','duration':3,'size':20000,'sent':False})
                    elif action=='record_send':
                        assert value==recording['last']['filename']
                        recording['last']['sent']=True
                    if action.startswith('record_'): result={'ok':True,'result':dict(recording)}
                r.fulfill(json=result)
            else:r.fulfill(path=str(ROOT/'web'/('index.html' if not path else path)))
        page.route('http://127.0.0.1:*/**',route)
        page.goto('http://127.0.0.1:8080/')
        expect(page.locator('.hub-card')).to_have_count(8)
        page.locator('#boot-splash').evaluate('(e)=>e.remove()')
        expect(page.locator('#sl-net')).to_have_text('Test network')
        expect(page.locator('body')).not_to_contain_text('192.0.2.1')
        for w,h in ((800,480),(1024,600)):
            page.set_viewport_size({'width':w,'height':h})
            assert page.evaluate('content.scrollHeight<=content.clientHeight')
        page.set_viewport_size({'width':800,'height':480})
        page.locator('[data-category=dashboard]').tap()
        expect(page.locator('.deck-fresh')).to_have_text('● LIVE')
        expect(page.locator('.deck-session')).to_have_text('Terminal')
        expect(page.locator('.deck-signal')).to_have_text('-61 dBm')
        expect(page.locator('.deck-connection')).to_contain_text('IP address in Settings')
        expect(page.locator('body')).not_to_contain_text('192.0.2.1')
        page.wait_for_timeout(2100)
        assert page.locator('.deck-rx-line').get_attribute('d').count('L')>=1
        for w,h in ((800,480),(1024,600)):
            page.set_viewport_size({'width':w,'height':h})
            assert page.evaluate('content.scrollHeight<=content.clientHeight && document.documentElement.scrollWidth<=innerWidth')
        page.set_viewport_size({'width':800,'height':480}); page.screenshot(path='/tmp/touchui-dashboard.png')
        assert not writes,'Dashboard must not start anything'
        # Pull down from an unused part of the top bar, then use real range events.
        page.mouse.move(330,20);page.mouse.down();page.mouse.move(330,110,steps=10);page.mouse.up()
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.locator('#deck-brightness')).to_be_enabled()
        assert page.evaluate("[...document.querySelectorAll('.deck-controls button,.deck-controls input')].every(e=>e.getBoundingClientRect().bottom<=innerHeight)")
        page.locator('#deck-brightness').focus(); page.locator('#deck-brightness').press('ArrowLeft')
        expect(page.locator('#kb')).not_to_be_visible()
        expect(page.locator('.deck-control-status')).to_have_text('Brightness set to 99%')
        page.locator('#deck-volume').fill('35'); page.locator('#deck-volume').dispatch_event('change')
        expect(page.locator('.deck-control-status')).to_have_text('Volume set to 35%')
        page.get_by_role('button',name='♫ Mute',exact=True).tap()
        expect(page.get_by_role('button',name='♫ Unmute',exact=True)).to_have_attribute('aria-pressed','true')
        page.screenshot(path='/tmp/touchui-quick-controls.png')
        # Range keys must not launch the legacy touch keyboard or leak to games.
        page.keyboard.press('Escape'); expect(page.get_by_role('dialog')).not_to_be_visible()
        page.get_by_role('button',name='Open quick controls').tap()
        page.get_by_role('button',name='▣ Screenshot').tap()
        expect(page.locator('.deck-toast')).to_contain_text('Saved to')
        expect(page.get_by_role('dialog')).not_to_be_visible()
        assert writes[-1][1]=={'action':'screenshot'}
        page.get_by_role('button',name='Open quick controls').tap()
        expect(page.get_by_role('button',name='Send to Discord',exact=True)).to_be_disabled()
        page.get_by_role('button',name='● Record screen',exact=True).tap()
        expect(page.get_by_role('dialog')).not_to_be_visible()
        expect(page.locator('.deck-record-badge')).to_be_visible()
        assert writes[-1][1]=={'action':'record_start'}
        page.locator('.deck-record-badge').tap()
        expect(page.get_by_role('button',name='Send to Discord',exact=True)).to_be_disabled()
        page.get_by_role('button',name='■ Stop recording',exact=True).tap()
        expect(page.locator('.deck-record-badge')).not_to_be_visible()
        page.get_by_role('button',name='Open quick controls').tap()
        expect(page.locator('.deck-record-info')).to_contain_text('.mp4')
        assert not [w for w in writes if w[1].get('action')=='record_send']
        page.get_by_role('button',name='Send to Discord',exact=True).tap()
        expect(page.get_by_role('button',name='Sent to Discord ✓',exact=True)).to_be_disabled()
        page.get_by_role('button',name='Done',exact=True).tap()
        fail_status=True; page.wait_for_timeout(2100)
        expect(page.locator('.deck-fresh')).to_contain_text('STALE')
        fail_status=False
        page.locator('#btn-back').tap(); before=len(status_calls); page.wait_for_timeout(2100)
        assert len(status_calls)==before,'Dashboard polling continues after leaving'
        page.locator('#btn-settings').tap()
        expect(page.locator('.info-body')).to_contain_text('IP address')
        expect(page.locator('.info-body')).to_contain_text('192.0.2.1')
        expect(page.locator('#sl-net')).not_to_contain_text('192.0.2.1')
        page.locator('#btn-back').tap()
        expect(page.locator('body')).not_to_contain_text('192.0.2.1')
        # Keep the terminal and its input alive across opening and closing controls.
        page.locator('[data-category=wireless]').tap()
        page.get_by_role('button',name='WiFi apps',exact=True).tap()
        page.locator('[data-entry="terminal:wifite"]').tap()
        expect(page.locator('#kb')).to_be_visible()
        page.locator('#term-in').fill('draft reply')
        page.get_by_role('button',name='Open quick controls').tap()
        expect(page.locator('#kb')).not_to_be_visible()
        page.get_by_role('button',name='Done',exact=True).tap()
        expect(page.locator('#kb')).to_be_visible(); expect(page.locator('#term-in')).to_have_value('draft reply')
        page.get_by_role('button',name='Open quick controls').tap()
        page.get_by_role('button',name='⌨ Keyboard',exact=True).tap()
        expect(page.locator('#kb')).not_to_be_visible()
        assert len([w for w in writes if w[0]=='api/term/start'])==1
        assert not errors,errors
        browser.close()
    print('PASS: real-sample rendering, stale state, 800x480/1024x600 fit, swipe, bounded controls, screenshot, cleanup, preserved terminal input and keyboard')

if __name__=='__main__': main()
