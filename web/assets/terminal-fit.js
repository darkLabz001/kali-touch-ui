// Keep the keyboard available while terminal controls or output have focus.
(() => {
  const content = document.getElementById('content');
  const topbar = document.querySelector('.topbar');
  const title = document.createElement('div');
  title.className = 'terminal-title';
  topbar.querySelector('.brand').after(title);
  const toggle = document.createElement('button');
  toggle.className = 'btn-gear terminal-keyboard-toggle';
  toggle.textContent = '⌨';
  toggle.setAttribute('aria-label', 'Toggle terminal keyboard');
  toggle.title = 'Show / hide keyboard';
  topbar.querySelector('.spacer').after(toggle);
  toggle.addEventListener('pointerdown', event => event.preventDefault());
  toggle.onclick = () => {
    const input = document.getElementById('term-in');
    if (!input) return;
    if (KB.shown) KB.hide();
    else { input.focus({ preventScroll: true }); KB.show(); }
  };
  document.addEventListener('focusout', event => {
    if (event.target.id === 'term-in' && content.querySelector('.term-page')) {
      event.stopImmediatePropagation();
    }
  }, true);
  let activePage = null;
  const sync = () => {
    const page = content.querySelector('.term-page');
    if (page === activePage) return;
    const wasTerminal = Boolean(activePage);
    activePage = page;
    document.body.classList.toggle('terminal-active', Boolean(page));
    if (!page) {
      if (wasTerminal) KB.hide();
      return;
    }
    title.textContent = page.querySelector('h2')?.textContent || 'Terminal';
    title.title = title.textContent;
    const input = page.querySelector('#term-in');
    input.placeholder = 'Type a reply…';
    input.setAttribute('aria-label', 'Terminal input');
    const send = page.querySelector('.term-go');
    send.setAttribute('aria-label', 'Send Enter to terminal');
    send.addEventListener('pointerdown', event => event.preventDefault());
  };
  new MutationObserver(sync).observe(content, { childList: true });
  sync();
})();
