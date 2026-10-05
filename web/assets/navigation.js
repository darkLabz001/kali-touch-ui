/* Group all launch styles by task while preserving each tool's existing runner. */
(() => {
  const categories = [
    { id: 'dashboard', title: 'Dashboard', icon: '◴', description: 'Live traffic, device health & sessions', groups: [] },
    { id: 'wireless', title: 'Wireless', icon: '✱', description: 'WiFi, Bluetooth & field tools', groups: ['WiFi apps', 'WiFi commands', 'Bluetooth'] },
    { id: 'network', title: 'Network', icon: '◉', description: 'Scanning, packet capture & SMB', groups: ['Scanning', 'Network utilities', 'Windows & SMB', 'Other tools'] },
    { id: 'osint', title: 'OSINT', icon: '◎', description: 'Domain research, DNS & metadata', groups: ['Domain & DNS', 'File metadata'] },
    { id: 'web', title: 'Web', icon: '◍', description: 'Web tools & portals', groups: ['Web tools', 'Portals'] },
    { id: 'passwords', title: 'Passwords', icon: '▣', description: 'Login testing, hashes & wordlists', groups: ['Login testing', 'Hashes & wordlists'] },
    { id: 'entertainment', title: 'Entertainment', icon: '♫', description: 'Offline games & social apps', groups: ['Games', 'Social'] },
    { id: 'scripts', title: 'My Scripts', icon: 'Py', description: 'Add and run your Python payloads', groups: [] },
  ];
  const content = document.getElementById('content');
  const definitions = customApps();
  const originals = {};
  const cleanupNames = [...new Set(definitions.map(d => d[4].name.replace(/^show/, "leave")))];
  let current = { kind: 'home', hub: null, back: 'home' };
  let payloadNames = [];
  let libraryRequest = null;
  const positions = new Map();
  const activeGroups = new Map();

  function cleanup() {
    if (state.evtSource) { state.evtSource.close(); state.evtSource = null; }
    if (termSrc) { termSrc.close(); termSrc = null; }
    for (const name of cleanupNames) {
      if (typeof window[name] === 'function') window[name]();
    }
    if (typeof window.leaveDashboard === 'function') window.leaveDashboard();
    if (typeof window.leaveEntertainment === 'function') window.leaveEntertainment();
    if (typeof KB !== 'undefined') KB.hide();
    state.running = false;
  }

  function remember() {
    if (current.kind === 'category') positions.set(current.hub, content.scrollTop);
  }

  function prepare() {
    remember(); cleanup();
    state.section = null; state.tool = null; state.settings = false; state.terminal = false;
    content.replaceChildren(); content.scrollTop = 0;
  }

  function quickGroup(tool) {
    if (tool.section === 'wireless') return ['wireless', 'WiFi commands'];
    if (tool.section === 'bt') return ['wireless', 'Bluetooth'];
    if (tool.section === 'scan' || tool.label === 'Ping Sweep') return ['network', 'Scanning'];
    if (tool.section === 'smb') return ['network', 'Windows & SMB'];
    if (tool.section === 'recon') return ['osint', 'Domain & DNS'];
    if (tool.section === 'web') return ['web', 'Web tools'];
    if (tool.section === 'auth' || (tool.section === 'crack' && tool.label.startsWith('Hydra'))) return ['passwords', 'Login testing'];
    if (tool.section === 'crack') return ['passwords', 'Hashes & wordlists'];
    return ['network', tool.section === 'util' ? 'Network utilities' : 'Other tools'];
  }

  function launcherGroup(tool) {
    if (tool.id === 'theharvester') return ['osint', 'Domain & DNS'];
    if (tool.id === 'exiftool') return ['osint', 'File metadata'];
    if (['netexec', 'evil-winrm', 'smbclient', 'responder'].includes(tool.id)) return ['network', 'Windows & SMB'];
    if (tool.id === 'nmap') return ['network', 'Scanning'];
    if (tool.group === 'WiFi') return ['wireless', ['wifite', 'airgeddon', 'kismet'].includes(tool.id) ? 'WiFi apps' : 'WiFi commands'];
    if (tool.group === 'BLE') return ['wireless', 'Bluetooth'];
    if (tool.group === 'Web') return ['web', 'Web tools'];
    if (tool.group === 'Auth') return ['passwords', 'Login testing'];
    if (tool.group === 'Crack') return ['passwords', 'Hashes & wordlists'];
    return ['network', 'Network utilities'];
  }

  function catalogue() {
    if (!state.data) return [];
    const entries = [];
    for (const tool of state.data.tools) {
      const [category, group] = quickGroup(tool);
      entries.push({ id: 'quick:' + tool.section + ':' + tool.label, category, group,
        title: tool.label, description: 'Guided run · enter options first', icon: tool.root ? '⚑' : '⚒',
        action: () => showRun(tool), mode: 'guided' });
    }
    for (const tool of state.data.launchers) {
      const [category, group] = launcherGroup(tool);
      entries.push({ id: 'terminal:' + tool.id, category, group, title: tool.label,
        description: tool.exists ? 'Interactive terminal' : 'Not installed · tap to install',
        icon: tool.icon, launcher: tool, mode: tool.exists ? 'terminal' : 'install' });
    }
    const wireless = ['showRecon', 'showHunter', 'showRadar', 'showWardrive', 'showRogue', 'showProbe', 'showDeauth', 'showFlood', 'showPentest'];
    for (const [icon, title, description, color, fn] of definitions) {
      if (fn.name === 'showPayloads') continue; // My Scripts is a first-level destination.
      const isWireless = wireless.includes(fn.name);
      const isPortal = ['showPortal', 'showClone'].includes(fn.name);
      entries.push({ id: 'app:' + fn.name, category: isWireless ? 'wireless' : isPortal ? 'web' : 'network',
        group: isWireless ? 'WiFi apps' : isPortal ? 'Portals' : 'Other tools',
        title, description, icon, color, action: () => window[fn.name](), mode: 'open' });
    }
    if (payloadNames.includes('domain_osint.py')) entries.push({
      id: 'payload:domain_osint.py', category: 'osint', group: 'Domain & DNS',
      title: 'Domain OSINT', description: 'DNS, registration & certificate reports', icon: 'Py',
      action: () => showPayload('domain_osint.py'), mode: 'script',
    });
    for (const [id, title, description, icon, action] of [
      ['snake', 'Snake', 'Chase the dots · swipe or use the arrow pad', '▰', () => showSnake()],
      ['memory', 'Memory Match', 'Find eight pairs · beat your move count', '▦', () => showMemoryGame()],
    ]) entries.push({ id: 'game:' + id, category: 'entertainment', group: 'Games', title, description, icon, action, mode: 'play' });
    for (const [id, title, description, icon] of [
      ['discord', 'Discord', 'Servers, communities & chat', '◉'],
      ['reddit', 'Reddit', 'Communities & discussions', '◎'],
      ['youtube', 'YouTube', 'Videos & music', '▶'],
    ]) entries.push({ id: 'social:' + id, category: 'entertainment', group: 'Social', title,
      description: description + ' · online', icon, action: () => showSocial(id, title), mode: 'open' });
    return entries.sort((a, b) => {
      const priority = entry => entry.id === 'terminal:wifite' ? -2 : entry.id.startsWith('app:') || entry.id.startsWith('payload:') ? -1 : 0;
      return priority(a) - priority(b) || a.title.localeCompare(b.title);
    });
  }

  function home() {
    prepare(); current = { kind: 'home', hub: null, back: 'home' };
    document.getElementById('btn-back').style.display = 'none';
    const grid = el('div', 'hub-home');
    const entries = catalogue();
    for (const category of categories) {
      const card = el('button', 'card hub-card');
      card.dataset.category = category.id;
      card.append(el('span', 'ico', category.icon), el('span', 't', category.title),
        el('span', 'hub-description', category.description));
      const count = category.id === 'dashboard' ? 'Live device overview' : category.id === 'entertainment' ? '2 games · 3 social apps' : category.id === 'scripts' ? (payloadNames.length ? payloadNames.length + ' scripts' : 'Your script library') : entries.filter(e => e.category === category.id).length + ' tools';
      card.appendChild(el('span', 'hub-count', count));
      card.onclick = () => category.id === 'dashboard' ? openDashboard() : category.id === 'scripts' ? showPayloads() : openCategory(category.id);
      grid.appendChild(card);
    }
    content.appendChild(grid);
    refreshLibrary();
  }

  function entryButton(entry) {
    if (entry.launcher) {
      const button = launchBtn(entry.launcher);
      button.dataset.entry = entry.id;
      // Keep installation and launching behavior in the established launcher.
      if (entry.launcher.exists) button.querySelector('.sub').textContent = entry.description;
      return button;
    }
    const button = el('button', 'tool-btn');
    button.dataset.entry = entry.id;
    const icon = el('span', 'ch', entry.icon);
    if (entry.color) icon.style.color = entry.color;
    const mid = el('span', 'tb-mid');
    mid.append(el('span', null, entry.title), el('span', 'sub', entry.description));
    button.append(icon, mid, el('span', 'root-tag', entry.mode));
    button.onclick = entry.action;
    return button;
  }

  function openDashboard() {
    prepare(); current = { kind: 'dashboard', hub: null, back: 'home' };
    showDashboard();
  }

  function openCategory(id) {
    if (id === 'dashboard') { openDashboard(); return; }
    const category = categories.find(c => c.id === id);
    if (!category || id === 'scripts') { showPayloads(); return; }
    prepare(); current = { kind: 'category', hub: id, back: 'home' };
    document.getElementById('btn-back').style.display = 'flex';
    const page = el('div', 'hub-page');
    const head = el('div', 'section-head');
    head.append(el('h2', null, category.icon + ' ' + category.title));
    const homeButton = el('button', 'hub-home-button', 'Home');
    homeButton.onclick = home; head.appendChild(homeButton);
    const entries = catalogue().filter(e => e.category === id);
    const groups = category.groups.filter(group => entries.some(e => e.group === group));
    const tabs = el('div', 'hub-tabs'); tabs.setAttribute('aria-label', category.title + ' groups');
    const list = el('div', 'tool-list');
    const draw = group => {
      activeGroups.set(id, group);
      list.replaceChildren(...entries.filter(e => e.group === group).map(entryButton));
      for (const button of tabs.children) {
        button.classList.toggle('selected', button.dataset.group === group);
        button.setAttribute('aria-pressed', String(button.dataset.group === group));
      }
      content.scrollTop = 0;
    };
    for (const group of groups) {
      const button = el('button', 'hub-tab', group);
      button.dataset.group = group; button.onclick = () => draw(group); tabs.appendChild(button);
    }
    page.append(head, tabs, list); content.appendChild(page);
    if (groups.length) draw(groups.includes(activeGroups.get(id)) ? activeGroups.get(id) : groups[0]);
    else list.appendChild(el('div', 'payload-note', 'No tools in this group yet.'));
    content.scrollTop = positions.get(id) || 0;
    if (id === "osint") refreshLibrary();
  }

  function wrap(name, kind = 'tool') {
    const fn = window[name];
    if (typeof fn !== 'function' || originals[name]) return;
    originals[name] = fn;
    window[name] = function (...args) {
      const hub = current.hub;
      const back = kind === 'payload' && current.kind === 'scripts' ? 'scripts' : hub || 'home';
      remember(); cleanup(); current = { kind, hub, back };
      content.scrollTop = 0;
      return fn(...args);
    };
  }

  for (const name of ['showRun', 'showTerminal', 'showSettings', 'showSection', 'showSnake', 'showMemoryGame', 'showSocial']) wrap(name);
  for (const definition of definitions) if (definition[4].name !== 'showPayloads') wrap(definition[4].name);
  wrap('showPayloads', 'scripts'); wrap('showPayload', 'payload');
  window.showHome = home;
  window.showCustomTools = () => showPayloads();
  // Retain the old function name for integrations; all tools now live in task groups.
  window.showLaunchers = home;

  function back() {
    const target = current.back;
    if (target === 'scripts') showPayloads();
    else if (target === 'home') home();
    else openCategory(target);
  }
  // Handle Back before the older page-specific listeners on the button.
  document.addEventListener('click', event => {
    if (!event.target.closest('#btn-back')) return;
    event.preventDefault(); event.stopImmediatePropagation(); back();
  }, true);

  window.TouchNavigation = { categories, catalogue, openCategory, openDashboard, home, back };
  if (state.data) home();
  function refreshLibrary() {
    if (libraryRequest) return;
    libraryRequest = fetch('/api/payloads').then(r => r.ok ? r.json() : { scripts: [] }).then(data => {
      const names = (data.scripts || []).map(s => s.name).sort();
      if (JSON.stringify(names) === JSON.stringify(payloadNames)) return;
      payloadNames = names;
      if (current.kind === 'home' && state.data) home();
      else if (current.kind === 'category' && current.hub === 'osint') openCategory('osint');
    }).catch(() => {}).finally(() => { libraryRequest = null; });
  }
})();
