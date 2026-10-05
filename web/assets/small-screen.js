// Compact keyboards keep usable terminal output on 320-pixel-high displays.
(() => {
  const compact = matchMedia('(max-height: 420px) and (max-width: 740px)');
  const original = kbRender;
  window.kbRender = function () {
    if (!compact.matches) { original(); return; }
    const keyboard = document.getElementById('kb');
    keyboard.classList.toggle('open', KB.shown); document.body.classList.toggle('kbd-open', KB.shown);
    if (!KB.shown) return;
    const letters = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
    const symbols = KB.shift ? ['!@#$%^&*()', '_+={}[]|\\', ':;\'"<>?~`'] : ['1234567890', '-/.:_@?!=+', '()[]{};,\\"'];
    const grid = keyboard.querySelector('.kb-grid'); grid.replaceChildren();
    for (const chars of KB.sym ? symbols : letters) {
      const row = el('div', 'kb-row');
      for (const ch of chars) { const key = el('button', 'kb-key', ch); key.dataset.k = 'ch'; key.dataset.v = ch; row.appendChild(key); }
      grid.appendChild(row);
    }
    const row = el('div', 'kb-row');
    for (const [kind, label] of [['shift','⇧'],['sym',KB.sym ? 'ABC':'123'],['sp','space'],['bs','⌫'],['ent','↵'],['close','✕']]) {
      const key = el('button', 'kb-key ' + (kind === 'sp' ? 'sp' : 'fn'), label); key.dataset.k = kind; row.appendChild(key);
    }
    grid.appendChild(row); keyboard.querySelector('.kb-acc').textContent = '';
  };
  compact.addEventListener('change', () => { if (KB.shown) kbRender(); });
})();
