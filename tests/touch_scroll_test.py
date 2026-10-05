"""Exercise mouse-emulated touch dragging, nested scrolling, taps and terminal controls."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    errors=[]
    for width,height in [(480,800),(800,480)]:
        page=browser.new_page(viewport={'width':width,'height':height},has_touch=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script('window.mockStreams=[];window.EventSource=class {constructor(){window.mockStreams.push(this)} close(){}}')
        def route(r):
            path=r.request.url.split('http://touch.test/',1)[1].split('?')[0]
            if path.startswith('api/'):
                r.fulfill(json={'sections':[],'tools':[],'launchers':[]} if path=='api/tools' else {'ok':True,'running':True})
            else:r.fulfill(path=str(ROOT/'web'/(path or 'index.html')))
        page.route('http://touch.test/**',route)
        page.goto('http://touch.test/')
        page.locator('#boot-splash').evaluate('(e)=>e.remove()')
        page.evaluate('''() => {
            const c=document.getElementById('content');c.innerHTML='';
            const list=document.createElement('div');list.id='drag-list';list.style.cssText='height:200px;overflow:auto';
            for(let i=0;i<35;i++){const b=document.createElement('button');b.textContent='Network '+i;b.style.cssText='display:block;width:100%;height:44px';b.onclick=()=>window.tapCount=(window.tapCount||0)+1;list.append(b);}
            c.append(list);const filler=document.createElement('div');filler.style.height='1700px';c.append(filler);
        }''')
        box=page.locator('#drag-list').bounding_box()
        x=box['x']+box['width']/2;y=box['y']+160
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x,y-100,steps=10);page.mouse.up()
        page.wait_for_timeout(300)
        assert page.locator('#drag-list').evaluate('(e)=>e.scrollTop')>90
        assert page.evaluate('window.tapCount||0')==0
        # A plain tap still activates a row; reaching the list edge scrolls the page.
        page.locator('#drag-list').evaluate('(e)=>e.scrollTop=e.scrollHeight')
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x,y-90,steps=8);page.mouse.up()
        page.wait_for_timeout(250)
        assert page.locator('#content').evaluate('(e)=>e.scrollTop')>60
        page.locator('#content').evaluate('(e)=>e.scrollTop=0')
        page.locator('#drag-list button').last.click()
        assert page.evaluate('window.tapCount')==1
        # Native touchscreen events continue to use Chromium's own panning.
        page.locator('#content').evaluate('(e)=>e.scrollTop=0')
        page.locator('#drag-list').evaluate('(e)=>e.scrollTop=0')
        box=page.locator('#drag-list').bounding_box();x=box['x']+box['width']/2;y=box['y']+160
        cdp=page.context.new_cdp_session(page)
        cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        for i in range(1,11):
            cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y-i*10}]})
            page.wait_for_timeout(16)
        cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        page.wait_for_timeout(400)
        assert page.locator('#drag-list').evaluate('(e)=>e.scrollTop')>50
        assert page.evaluate('window.tapCount')==1
        page.evaluate('showTerminal()')
        expect(page.locator('body')).to_have_class('terminal-active kbd-open')
        page.evaluate('tFeed("\\r\\n"+"output line with a long explanation ".repeat(4)+"\\r\\n"+"history line\\r\\n".repeat(120))')
        out=page.locator('#term-out')
        assert out.evaluate('(e)=>getComputedStyle(e).whiteSpace')=='pre-wrap'
        assert out.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        page.get_by_role('button',name='Scroll terminal to latest output').click()
        before=out.evaluate('(e)=>e.scrollTop');box=out.bounding_box()
        x=box['x']+box['width']/2;y=box['y']+box['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x,y+80,steps=8);page.mouse.up()
        page.wait_for_timeout(900)
        assert out.evaluate('(e)=>e.scrollTop')<before-60
        position=out.evaluate('(e)=>e.scrollTop')
        page.evaluate('window.mockStreams.at(-1).onmessage({data:JSON.stringify("new output\\r\\n")})')
        assert abs(out.evaluate('(e)=>e.scrollTop')-position)<2
        page.get_by_role('button',name='Scroll terminal to latest output').click()
        assert out.evaluate('(e)=>e.scrollHeight-e.scrollTop-e.clientHeight')<2
        page.get_by_role('button',name='Toggle terminal line wrapping').click()
        assert out.evaluate('(e)=>getComputedStyle(e).whiteSpace')=='pre'
        page.get_by_role('button',name='Toggle terminal line wrapping').click()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=f'/tmp/4inch-scroll-{width}x{height}.png')
        page.close()
    assert not errors,errors
    browser.close()
print('PASS: drag momentum, nested edge handoff, no accidental activation, normal taps, wrapped terminal, history scrolling, latest output, two layouts')
