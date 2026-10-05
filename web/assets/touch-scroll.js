// Resistive panels often expose mouse pointers rather than native touch gestures.
(() => {
  if (document.documentElement.dataset.edition !== '4inch') return;
  const content = document.getElementById('content');
  const excluded = 'input,textarea,select,[contenteditable="true"],input[type="range"],.kbd,.term-keys,canvas';
  let gesture = null, frame = null, clickBlock = null;
  const stopMomentum = () => { if (frame !== null) cancelAnimationFrame(frame); frame = null; document.body.classList.remove("touch-coasting"); };
  const scrollers = (target, axis) => {
    const found = [];
    for (let node = target; node && content.contains(node); node = node.parentElement) {
      const style = getComputedStyle(node);
      const overflow = axis === 'y' ? style.overflowY : style.overflowX;
      const extent = axis === 'y' ? node.scrollHeight - node.clientHeight : node.scrollWidth - node.clientWidth;
      if (/(auto|scroll)/.test(overflow) && extent > 1) found.push(node);
      if (node === content) break;
    }
    return found;
  };
  const move = (nodes, axis, delta) => {
    const key = axis === 'y' ? 'scrollTop' : 'scrollLeft';
    let remaining = delta, moved = 0;
    for (const node of nodes) {
      if (!node.isConnected) continue;
      const before = node[key]; node[key] += remaining;
      const used = node[key] - before; remaining -= used; moved += used;
      if (Math.abs(remaining) < 1) break;
    }
    return moved;
  };
  document.addEventListener('pointerdown', event => {
    stopMomentum(); clickBlock = null;
    if (event.pointerType !== 'mouse' || event.button !== 0 || !content.contains(event.target) || event.target.closest(excluded)) return;
    const rect=event.target.getBoundingClientRect();
    if ((event.target.scrollHeight>event.target.clientHeight && event.clientX>=rect.left+event.target.clientWidth) ||
        (event.target.scrollWidth>event.target.clientWidth && event.clientY>=rect.top+event.target.clientHeight)) return;
    // Keep normal taps and native touch scrolling; claim only a deliberate drag.
    gesture = {id:event.pointerId,target:event.target,x:event.clientX,y:event.clientY,lastX:event.clientX,lastY:event.clientY,time:event.timeStamp,velocity:0,axis:null,nodes:[]};
  }, true);
  document.addEventListener('pointermove', event => {
    const g = gesture; if (!g || event.pointerId !== g.id) return;
    const dx = event.clientX - g.x, dy = event.clientY - g.y;
    if (!g.axis) {
      if (Math.hypot(dx,dy) < 8) return;
      g.axis = Math.abs(dx) > Math.abs(dy)*1.2 ? 'x' : 'y';
      g.nodes = scrollers(g.target,g.axis);
      if (!g.nodes.length) { gesture = null; return; }
      document.body.classList.add('touch-dragging');
      getSelection()?.removeAllRanges();
    }
    event.preventDefault();
    const delta = g.axis === 'y' ? g.lastY-event.clientY : g.lastX-event.clientX;
    const dt = Math.max(1,event.timeStamp-g.time);
    const used = move(g.nodes,g.axis,delta);
    g.velocity = .5*g.velocity+.5*Math.max(-2,Math.min(2,used/dt));
    g.lastX=event.clientX;g.lastY=event.clientY;g.time=event.timeStamp;
  }, {capture:true,passive:false});
  const finish = (event, cancelled=false) => {
    const g = gesture; if (!g || g.id !== event.pointerId) return;
    gesture=null;document.body.classList.remove('touch-dragging');
    if (!g.axis) return;
    clickBlock={target:g.target,until:performance.now()+400};
    if (cancelled || event.timeStamp-g.time>100 || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    document.body.classList.add("touch-coasting");
    let velocity=g.velocity,last=performance.now();
    const coast=now=>{
      const dt=Math.min(32,now-last);last=now;
      const moved=move(g.nodes,g.axis,velocity*dt);
      velocity*=Math.exp(-dt/160);
      if (Math.abs(velocity)<.04 || Math.abs(moved)<.5) { frame=null;document.body.classList.remove("touch-coasting");return; }
      frame=requestAnimationFrame(coast);
    };
    frame=requestAnimationFrame(coast);
  };
  document.addEventListener('pointerup', event=>finish(event),true);
  document.addEventListener('pointercancel', event=>finish(event,true),true);
  document.addEventListener('click',event=>{
    if(clickBlock && performance.now()<clickBlock.until && content.contains(event.target) && (event.target===clickBlock.target || event.target.contains(clickBlock.target) || clickBlock.target.contains(event.target))) {
      event.preventDefault();event.stopImmediatePropagation();clickBlock=null;
    }
  },true);
  content.addEventListener('wheel',stopMomentum,{passive:true});
  window.addEventListener('blur',()=>{stopMomentum();gesture=null;document.body.classList.remove('touch-dragging');});

  const topbar=document.querySelector('.topbar');
  for(const [label,title,action] of [
    ['↔','Toggle terminal line wrapping',()=>document.body.classList.toggle('terminal-no-wrap')],
    ['⇣','Scroll terminal to latest output',()=>{stopMomentum();const out=document.getElementById('term-out');if(out)out.scrollTop=out.scrollHeight;}]
  ]) {
    const button=document.createElement('button');button.className='btn-gear terminal-scroll-control';button.textContent=label;button.title=title;button.setAttribute('aria-label',title);
    button.addEventListener('pointerdown',e=>e.preventDefault());button.onclick=action;
    topbar.querySelector('.spacer').after(button);
  }
})();
