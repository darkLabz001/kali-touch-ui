// Keep the animation while loading; don't replay it after the system splash.
(() => {
  const splash = document.getElementById('boot-splash');
  if (!splash) return;
  const handoff = new URLSearchParams(location.search).get('splash') === 'handoff';
  let seen = false;
  try { seen = sessionStorage.getItem('kali-touch-splash-seen') === '1'; } catch (_) {}
  const started = performance.now();
  const minimum = handoff || seen ? 0 : 1500;
  let ready = false, done = false, skip = false, timer;
  if (handoff || seen) splash.classList.add('boot-handoff');
  const status = document.getElementById('ds-status');
  status.textContent = 'Opening local tools…';
  const fill = document.getElementById('ds-fill');
  if (fill) fill.style.width = '35%';
  function reveal() {
    if (!ready || done) return;
    const left = minimum - (performance.now() - started);
    if (!skip && left > 0) { clearTimeout(timer); timer = setTimeout(reveal, left); return; }
    done = true; splash.classList.add('fade');
    try { sessionStorage.setItem('kali-touch-splash-seen', '1'); } catch (_) {}
    setTimeout(() => splash.remove(), 200);
  }
  window.addEventListener('touchui:ready', () => {
    ready = true; status.textContent = 'Ready'; if (fill) fill.style.width = '100%'; reveal();
  });
  window.addEventListener('touchui:loading-error', () => {
    status.textContent = 'Waiting for local tools… retrying';
  });
  splash.addEventListener('pointerdown', () => { skip = true; reveal(); });
})();
