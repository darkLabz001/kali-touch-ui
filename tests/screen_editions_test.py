"""Exercise screen editions with mocked tools, device controls and terminal I/O."""
from navigation_test import ROOT, fixtures
from playwright.sync_api import sync_playwright, expect


def main():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for edition,width,height in [('7inch',800,480),('4inch',800,480),('4inch',480,800),('35inch',480,320),('35inch',320,480)]:
   page=browser.new_page(viewport={'width':width,'height':height},has_touch=True)
   errors=[];writes=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.add_init_script('window.mockStreams=[];window.EventSource=class {constructor(){window.mockStreams.push(this)}close(){}};')
   def route(r):
    path=r.request.url.split('http://127.0.0.1:',1)[1].split('/',1)[1].split('?')[0]
    if path.startswith('api/'):
     result={}
     if r.request.method=='POST':writes.append((path,r.request.post_data_json))
     if path=='api/tools':result=fixtures()
     elif path=='api/term/start':result={'running':True,'ok':True}
     elif path=='api/device/status':result={'controls':{'brightness':{'supported':True,'value':100},'volume':{'supported':True,'value':40,'muted':False},'screenshot':True}}
     r.fulfill(json=result)
    elif path=='assets/edition.js':r.fulfill(content_type='application/javascript',body=f'document.documentElement.dataset.edition="{edition}";')
    else:r.fulfill(path=str(ROOT/'web'/('index.html' if not path else path)))
   page.route('http://127.0.0.1:*/**',route)
   page.goto('http://127.0.0.1:8080/?splash=handoff')
   expect(page.locator('.hub-card')).to_have_count(8)
   expect(page.locator('#boot-splash')).to_have_count(0)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   # Every destination can be reached by touch/scroll, including the last row.
   for category in ['dashboard','wireless','network','osint','web','passwords','entertainment','scripts']:
    page.locator(f'[data-category="{category}"]').tap()
    page.locator('#btn-back').tap()
    expect(page.locator('.hub-card')).to_have_count(8)
   page.screenshot(path=f'/tmp/edition-{edition}-{width}x{height}.png')
   page.get_by_role('button',name='Open quick controls').tap()
   expect(page.get_by_role('dialog')).to_be_visible()
   if height<=420:
    assert page.locator('.deck-control-status').bounding_box()['y']+page.locator('.deck-control-status').bounding_box()['height']<=height
   page.get_by_role('button',name='Done',exact=True).tap()
   page.locator('[data-category=wireless]').tap();page.get_by_role('button',name='WiFi apps',exact=True).tap();page.locator('[data-entry="terminal:wifite"]').tap()
   expect(page.locator('#kb')).to_be_visible()
   page.wait_for_timeout(180)
   page.evaluate('window.mockStreams.at(-1).onmessage({data:JSON.stringify("WiFite\\r\\nChoose interface: ")})')
   out=page.locator('#term-out').bounding_box();keyboard=page.locator('#kb').bounding_box();field=page.locator('#term-in').bounding_box()
   assert out['height']>=60,(edition,width,height,out)
   assert field['y']+field['height']<=keyboard['y']+1,(field,keyboard)
   assert keyboard['y']+keyboard['height']<=height+1
   assert page.evaluate("[...document.querySelectorAll('.kb-key')].every(e=>e.getBoundingClientRect().right<=innerWidth)")
   if height<=420:
    expect(page.locator('.kb-row')).to_have_count(4)
    page.locator('.kb-key[data-k=sym]').tap()
   page.locator('.kb-key[data-v="1"]').tap();page.get_by_role('button',name='Send Enter to terminal').tap()
   assert writes[-1]==('api/term/input',{'data':'1\r'}),writes
   page.screenshot(path=f'/tmp/terminal-{edition}-{width}x{height}.png')
   page.locator('#btn-back').tap();page.locator('#btn-back').tap()
   page.locator('[data-category=entertainment]').tap();page.locator('[data-entry="game:snake"]').tap()
   if width==480 and height==320:
    assert page.evaluate("[...document.querySelectorAll('.ent-page button,.ent-snake')].every(e=>e.getBoundingClientRect().bottom<=innerHeight)")
   assert not errors,errors
   print(f'PASS {edition} {width}x{height}: navigation, controls, terminal {out["height"]:.0f}px, keyboard typing, games')
   page.close()
  browser.close()

if __name__=='__main__':main()
