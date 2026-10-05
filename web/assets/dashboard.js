/* Live telemetry and a touch control shade. No scans or tools start automatically. */
(() => {
  const local = ['127.0.0.1', 'localhost'].includes(location.hostname);
  const helper = 'http://127.0.0.1:8082';
  const content = document.getElementById('content');
  let dispose = null;
  let toastTimer;
  const toast = el('div', 'deck-toast'); toast.setAttribute('role', 'status'); toast.hidden = true;
  document.body.appendChild(toast);
  function message(text) {
    toast.textContent = text; toast.hidden = false; clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 4500);
  }
  async function device(path, body, signal) {
    if (!local) throw new Error('Open this feature on the device touchscreen.');
    const response = await fetch(helper + '/api/device/' + path, {
      method: body ? 'POST' : 'GET', signal,
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Device helper unavailable');
    return result;
  }
  const bytes = value => {
    if (value === null || value === undefined) return '—';
    const units = ['B', 'KiB', 'MiB', 'GiB']; let index = 0;
    while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
    return value.toFixed(index ? 1 : 0) + ' ' + units[index];
  };
  const uptime = seconds => Math.floor(seconds / 3600) + 'h ' + Math.floor(seconds % 3600 / 60) + 'm';
  function button(label, action, cls = 'deck-button') {
    const b = el('button', cls, label); b.type = 'button'; b.onclick = action; return b;
  }
  window.leaveDashboard = () => { if (dispose) dispose(); dispose = null; };

  window.showDashboard = function showDashboard() {
    leaveDashboard(); content.replaceChildren();
    document.getElementById('btn-back').style.display = 'flex';
    const abort = new AbortController(); let timer, taskTimer, active = true;
    const page = el('div', 'deck-page');
    const head = el('div', 'deck-heading');
    const title = el('div'); title.append(el('div', 'deck-eyebrow', 'SYSTEM OVERVIEW'), el('h2', null, 'Live dashboard'));
    const freshness = el('span', 'deck-fresh', 'Connecting…'); freshness.setAttribute('role', 'status');
    const actions = el('div', 'deck-actions'); actions.append(freshness, button('Controls', () => openControls()));
    head.append(title, actions); page.appendChild(head);
    const grid = el('div', 'deck-grid'); page.appendChild(grid);
    const traffic = el('section', 'deck-panel deck-traffic');
    const trafficHead = el('div', 'deck-row'); const networkTitle = el('h3', null, 'NETWORK TRAFFIC');
    const interfaceLabel = el('span', 'deck-subtle', 'Sampling…'); trafficHead.append(networkTitle, interfaceLabel);
    const rates = el('div', 'deck-rates'); const incoming = el('strong', 'deck-rx', '—'); const outgoing = el('strong', 'deck-tx', '—');
    const rx = el('div'), tx = el('div'); rx.append(el('span', null, '↓ RECEIVE'), incoming); tx.append(el('span', null, '↑ SEND'), outgoing); rates.append(rx, tx);
    const chart = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chart.setAttribute('viewBox', '0 0 480 100'); chart.setAttribute('preserveAspectRatio', 'none'); chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', 'Network traffic graph; waiting for samples'); chart.classList.add('deck-chart');
    for (const y of [15, 40, 65, 90]) {
      const line = document.createElementNS(chart.namespaceURI, 'path'); line.setAttribute('d', `M0 ${y} H480`); line.setAttribute('class', 'deck-gridline'); chart.appendChild(line);
    }
    const paths = ['deck-rx-line', 'deck-tx-line'].map(cls => {
      const line = document.createElementNS(chart.namespaceURI, 'path'); line.setAttribute('class', cls); chart.appendChild(line); return line;
    });
    const scale = el('span', 'deck-subtle', 'Building history'); const historyNote = el('div', 'deck-row'); historyNote.append(scale, el('span', 'deck-subtle', 'LAST 60 SECONDS → NOW'));
    traffic.append(trafficHead, rates, chart, historyNote); grid.appendChild(traffic);
    const health = el('section', 'deck-panel deck-health'); health.appendChild(el('h3', null, 'DEVICE HEALTH'));
    const stats = {};
    for (const [key, label] of [['cpu', 'CPU'], ['memory', 'Memory'], ['storage', 'Storage']]) {
      const row = el('div', 'deck-meter-row'); const value = el('strong', null, '—'); const track = el('div', 'deck-meter'); const fill = el('div'); track.appendChild(fill);
      const labels = el('div', 'deck-row'); labels.append(el('span', null, label), value); row.append(labels, track); health.appendChild(row);
      stats[key] = { value, fill };
    }
    const temp = el('span', 'deck-temperature', '— °C'); const up = el('span', 'deck-subtle', 'Uptime —'); const tempRow = el('div', 'deck-row'); tempRow.append(temp, up); health.appendChild(tempRow); grid.appendChild(health);
    const connection = el('section', 'deck-panel deck-connection'); const signal = el('strong', 'deck-signal', '—');
    const connectionInfo = el('div'); const name = el('h3', null, 'CONNECTION'); const address = el('div', 'deck-subtle', 'Reading connection…'); connectionInfo.append(name, address);
    connection.append(connectionInfo, signal); grid.appendChild(connection);
    const sessions = el('section', 'deck-panel deck-sessions'); const sessionHeading = el('h3', null, 'TRACKED SESSIONS'); const sessionList = el('div', 'deck-session-list', 'Checking…'); sessions.append(sessionHeading, sessionList); grid.appendChild(sessions);
    content.appendChild(page);
    let history = [], previousStamp = null, lastAt = null;
    function metric(key, used, total) {
      const value = total ? Math.max(0, Math.min(100, used * 100 / total)) : null;
      stats[key].value.textContent = value === null ? '—' : Math.round(value) + '%';
      stats[key].fill.style.width = (value || 0) + '%';
      stats[key].fill.classList.toggle('hot', value >= 85);
    }
    async function poll() {
      if (!active || document.hidden) { if (active) timer = setTimeout(poll, 2000); return; }
      try {
        const data = await device('status', null, abort.signal);
        if (!active) return;
        lastAt = new Date(); freshness.textContent = '● LIVE'; freshness.classList.add('online'); freshness.title = 'Updated ' + lastAt.toLocaleTimeString();
        metric('cpu', data.cpu_percent, data.cpu_percent === null ? 0 : 100);
        metric('memory', data.memory.used, data.memory.total); metric('storage', data.storage.used, data.storage.total);
        stats.memory.value.title = bytes(data.memory.used) + ' / ' + bytes(data.memory.total);
        stats.storage.value.title = bytes(data.storage.free) + ' free';
        temp.textContent = data.temperature_c === null ? 'Temperature —' : data.temperature_c.toFixed(1) + ' °C'; temp.classList.toggle('hot', data.temperature_c >= 75);
        up.textContent = 'Up ' + uptime(data.uptime_seconds);
        const net = data.network;
        if (interfaceLabel.textContent !== (net.interface || 'No route')) history = [];
        interfaceLabel.textContent = net.interface || 'No route';
        incoming.textContent = bytes(net.rx_bps) + '/s'; outgoing.textContent = bytes(net.tx_bps) + '/s';
        if (data.sampled_at !== previousStamp) {
          history.push({ t: data.sampled_at, rx: net.rx_bps, tx: net.tx_bps }); previousStamp = data.sampled_at;
        }
        history = history.filter(point => data.sampled_at - point.t <= 60);
        const maximum = Math.max(1024, ...history.flatMap(point => [point.rx || 0, point.tx || 0]));
        ['rx', 'tx'].forEach((key, index) => {
          let started = false, previousTime = null;
          const path = history.map(point => {
            if (point[key] === null) { started = false; return ''; }
            const x = 480 - (data.sampled_at - point.t) * 8;
            const y = 90 - point[key] / maximum * 80;
            const move = !started || (previousTime !== null && point.t - previousTime > 6);
            started = true; previousTime = point.t;
            return `${move ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
          }).join(' '); paths[index].setAttribute('d', path);
        });
        scale.textContent = 'Scale ' + bytes(maximum) + '/s';
        chart.setAttribute('aria-label', `Receive ${incoming.textContent}, send ${outgoing.textContent}; up to sixty seconds of real samples`);
        const wifi = data.wireless[0]; signal.textContent = wifi ? wifi.signal_dbm + ' dBm' : 'No WiFi link';
        signal.title = wifi ? wifi.interface + ' · ' + wifi.quality + '% signal quality' : 'No connected wireless interface';
      } catch (error) {
        if (!active || error.name === 'AbortError') return;
        freshness.classList.remove('online'); freshness.textContent = lastAt ? 'STALE · ' + lastAt.toLocaleTimeString() : 'UNAVAILABLE';
        address.textContent = local ? 'Device helper unavailable · retrying' : 'Live metrics are available on the touchscreen';
      } finally { if (active) timer = setTimeout(poll, 2000); }
    }
    async function tasks() {
      if (!active || document.hidden) { if (active) taskTimer = setTimeout(tasks, 6000); return; }
      const checks = [['Terminal', '/api/term/status'], ['Python script', '/api/payloads/status'], ['Recon', '/api/recon/state'], ['Capture', '/api/hs/state']];
      const extras = { showWardrive: ['Wardrive', 'wardrive'], showRogue: ['Rogue AP', 'rogue'], showProbe: ['Probe', 'probe'], showDeauth: ['Deauth', 'deauth'], showFlood: ['Flood', 'flood'], showPortal: ['Portal', 'portal'], showClone: ['Clone', 'clone'], showPentest: ['Pentest', 'apent'] };
      for (const entry of customApps()) if (extras[entry[4].name]) { const [label, path] = extras[entry[4].name]; checks.push([label, '/api/' + path + '/status']); }
      const results = await Promise.allSettled(checks.map(async ([label, path]) => {
        const response = await fetch(path, { signal: abort.signal });
        if (!response.ok) throw new Error('Unavailable');
        const data = await response.json();
        const running = typeof data.running === 'boolean' ? data.running : data.busy;
        if (typeof running !== 'boolean') throw new Error('Unknown session state');
        return { label, running, cracking: data.cracking === true };
      }));
      if (!active) return;
      const known = results.filter(r => r.status === 'fulfilled').map(r => r.value);
      const running = known.filter(r => r.running).map(r => r.label);
      if (known.some(r => r.cracking)) running.push('Hash cracking');
      sessionList.replaceChildren(...running.map(label => el('span', 'deck-session', label)));
      if (!running.length) sessionList.textContent = known.length === checks.length ? 'No tracked sessions running' : 'No active sessions reported · some status unavailable';
      try {
        const response = await fetch('/api/sysinfo', { signal: abort.signal });
        const info = await response.json();
        if (active) { name.textContent = info.ssid || info.hostname || 'CONNECTION'; address.textContent = 'IP address in Settings'; }
      } catch (_) { /* Metrics poll reports connection errors. */ }
      if (active) taskTimer = setTimeout(tasks, 6000);
    }
    dispose = () => { active = false; abort.abort(); clearTimeout(timer); clearTimeout(taskTimer); };
    poll(); tasks();
  };

  const shade = el('div', 'deck-shade'); shade.hidden = true;
  const panel = el('section', 'deck-controls'); panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-labelledby', 'deck-controls-title');
  const grip = el('div', 'deck-grip');
  const heading = el('div', 'deck-controls-heading'); const controlTitle = el('h2', null, 'Quick controls'); controlTitle.id = 'deck-controls-title';
  const closeButton = button('Done', () => closeControls()); heading.append(controlTitle, closeButton); panel.append(grip, heading);
  const controlStatus = el('div', 'deck-control-status', 'Reading device…'); controlStatus.setAttribute('role', 'status');
  const sliders = el('div', 'deck-sliders'); const controls = {};
  for (const [key, label, min] of [['brightness', 'Brightness', 10], ['volume', 'Volume', 0]]) {
    const wrap = el('div', 'deck-slider'); const row = el('div', 'deck-row'); const text = el('label', null, label); text.htmlFor = 'deck-' + key;
    const output = el('output', null, '—'); const input = el('input'); input.type = 'range'; input.min = min; input.max = 100; input.step = 1; input.id = text.htmlFor; input.disabled = true;
    input.oninput = () => { output.textContent = input.value + '%'; };
    input.onchange = () => setControl(key, Number(input.value));
    row.append(text, output); wrap.append(row, input); sliders.appendChild(wrap); controls[key] = { input, output, pending: false };
  }
  const shortcuts = el('div', 'deck-shortcuts');
  const homeButton = button('⌂ Home', () => { closeControls(false); TouchNavigation.home(); });
  const dashboardButton = button('◴ Dashboard', () => { closeControls(false); TouchNavigation.openDashboard(); });
  const wifiButton = button('✱ WiFi', () => { closeControls(false); showSettings(); });
  const keyboardButton = button('⌨ Keyboard', () => {
    const input = keyboardTarget();
    if (!input) { controlStatus.textContent = 'Open a text field to use the keyboard.'; return; }
    const wasShown = keyboardWasShown; closeControls(false); input.focus({ preventScroll: true });
    if (wasShown) KB.hide(); else KB.show();
  });
  const screenshotButton = button('▣ Screenshot', async () => {
    closeControls();
    await new Promise(resolve => setTimeout(resolve, 220));
    try { const result = await device('control', { action: 'screenshot' }); message('Saved to ' + result.result.path); }
    catch (error) { message(error.message); }
  });
  const muteButton = button('♫ Mute', () => setControl('mute', !muted));
  shortcuts.append(homeButton, dashboardButton, wifiButton, keyboardButton, screenshotButton, muteButton);
  let recording = null, recordingPending = false, recordingTimer = null, recordingRequest = 0;
  const recorder = el('div', 'deck-recorder');
  const recordButton = button('● Record screen', () => recordingAction(recording?.state === 'recording' ? 'record_stop' : 'record_start'));
  const sendButton = button('Send to Discord', () => recordingAction('record_send'));
  recordButton.disabled = sendButton.disabled = true;
  const recordInfo = el('div', 'deck-record-info', 'MP4 · up to 2 min · no audio');
  recordInfo.setAttribute('role', 'status');
  recorder.append(recordButton, sendButton, recordInfo);
  panel.append(sliders, shortcuts, recorder, controlStatus); shade.appendChild(panel); document.body.appendChild(shade);
  const recordBadge = button('● REC', () => openControls(), 'deck-record-badge');
  recordBadge.hidden = true; recordBadge.setAttribute('aria-label', 'Screen recording active; open controls to stop');
  document.querySelector('.topbar .spacer').after(recordBadge);

  function drawRecording(data) {
    recording = data;
    const running = data.state === 'recording', stopping = data.state === 'stopping';
    recordButton.textContent = running ? '■ Stop recording' : stopping ? 'Saving…' : '● Record screen';
    recordButton.disabled = recordingPending || stopping || data.uploading || !data.supported;
    sendButton.textContent = data.uploading ? 'Sending…' : data.last?.sent ? 'Sent to Discord ✓' : 'Send to Discord';
    sendButton.disabled = recordingPending || running || stopping || data.uploading || !data.discord_configured || !data.last || data.last.sent || data.last.size > 9 * 1024 * 1024;
    const elapsed = Math.floor(data.elapsed || 0);
    const timer = Math.floor(elapsed / 60) + ':' + String(elapsed % 60).padStart(2, '0');
    recordBadge.hidden = !running && !stopping;
    recordBadge.textContent = stopping ? '● SAVING' : '● REC ' + timer;
    if (running) recordInfo.textContent = 'Recording ' + timer + ' / 2:00 · no audio';
    else if (stopping) recordInfo.textContent = 'Finishing MP4…';
    else if (data.error || data.upload_error) recordInfo.textContent = data.error || data.upload_error;
    else if (data.last) recordInfo.textContent = data.last.filename + ' · ' + bytes(data.last.size) + (data.discord_configured ? '' : ' · Discord not configured');
    else recordInfo.textContent = data.supported ? 'MP4 · up to 2 min · no audio' + (data.discord_configured ? '' : ' · Discord not configured') : 'Screen recording unavailable on this device.';
    if (!data.uploading && controlStatus.textContent === 'Sending the finished clip to Discord…') {
      controlStatus.textContent = data.last?.sent ? 'Recording sent to Discord.' : data.upload_error || 'Upload finished.';
    }
  }
  function scheduleRecording() {
    clearTimeout(recordingTimer);
    if (local) recordingTimer = setTimeout(refreshRecording, recording?.state === 'recording' || recording?.state === 'stopping' || recording?.uploading ? 1000 : 5000);
  }
  async function refreshRecording() {
    if (!local) { recordInfo.textContent = 'Record from the device touchscreen.'; return; }
    const request = ++recordingRequest;
    try {
      const data = await device('recording');
      if (request === recordingRequest && !recordingPending) drawRecording(data);
    } catch (_) {
      if (request === recordingRequest) {
        recordButton.disabled = sendButton.disabled = true;
        recordInfo.textContent = 'Recorder unavailable. Reopen controls to retry.';
      }
    } finally { if (request === recordingRequest && !recordingPending) scheduleRecording(); }
  }
  async function recordingAction(action) {
    if (recordingPending) return;
    const filename = recording?.last?.filename;
    recordingPending = true; recordingRequest++; clearTimeout(recordingTimer);
    recordButton.disabled = sendButton.disabled = true;
    if (action === 'record_start' || action === 'record_stop') {
      closeControls();
      await new Promise(resolve => setTimeout(resolve, 220));
    }
    try {
      const response = await device('control', { action, ...(action === 'record_send' ? { value: filename } : {}) });
      recordingPending = false; drawRecording(response.result);
      if (action === 'record_send') controlStatus.textContent = 'Sending the finished clip to Discord…';
    } catch (error) {
      recordingPending = false;
      recordInfo.textContent = error.message; message(error.message);
    } finally { recordingPending = false; scheduleRecording(); }
  }
  refreshRecording();
  let previousFocus = null, keyboardWasShown = false, controlAbort = null, controlTimer, muted = false, mutePending = false;
  const toggle = button('⌄', () => openControls(), 'btn-gear deck-toggle'); toggle.setAttribute('aria-label', 'Open quick controls'); toggle.setAttribute('aria-expanded', 'false');
  panel.id = 'deck-controls'; toggle.setAttribute('aria-controls', panel.id);
  toggle.onpointerdown = event => event.preventDefault();
  document.getElementById('btn-settings').before(toggle);
  function keyboardTarget() {
    const valid = e => e && e.isConnected && e.matches('textarea, input:not([type]), input[type=text], input[type=password], input[type=search], input[type=number]');
    if (valid(previousFocus)) return previousFocus;
    return content.querySelector('textarea, input:not([type]), input[type=text], input[type=password], input[type=search], input[type=number]');
  }
  function drawControls(data) {
    for (const key of ['brightness', 'volume']) {
      const item = data.controls[key], ui = controls[key];
      ui.input.disabled = !item.supported || ui.pending;
      if (!ui.pending && document.activeElement !== ui.input) {
        ui.input.value = item.value ?? 0; ui.output.textContent = item.supported ? item.value + '%' : 'Unavailable';
      }
    }
    muted = data.controls.volume.muted;
    muteButton.textContent = muted ? '♫ Unmute' : '♫ Mute'; muteButton.setAttribute('aria-pressed', String(muted)); muteButton.disabled = !data.controls.volume.supported || mutePending;
    screenshotButton.disabled = !data.controls.screenshot;
  }
  async function refreshControls() {
    if (shade.hidden) return;
    const signal = controlAbort.signal;
    try {
      const data = await device('status', null, signal); if (shade.hidden || signal.aborted) return;
      drawControls(data);
      if (controlStatus.textContent === 'Reading device…') controlStatus.textContent = 'Swipe up or tap Done to return.';
    } catch (error) {
      if (signal.aborted) return;
      controlStatus.textContent = local ? 'Device controls unavailable. WiFi settings and navigation still work.' : error.message;
      for (const ui of Object.values(controls)) ui.input.disabled = true;
      muteButton.disabled = screenshotButton.disabled = true;
    } finally { if (!shade.hidden && !signal.aborted) controlTimer = setTimeout(refreshControls, 5000); }
  }
  async function setControl(action, value) {
    const ui = controls[action];
    if (ui?.pending || (action === 'mute' && mutePending)) return;
    if (ui) { ui.pending = true; ui.input.disabled = true; } else { mutePending = true; muteButton.disabled = true; }
    try {
      const response = await device('control', { action, value });
      controlStatus.textContent = action === 'mute' ? (response.result.muted ? 'Audio muted' : 'Audio unmuted') : (action === 'brightness' ? 'Brightness' : 'Volume') + ' set to ' + response.result.value + '%';
      if (ui) { ui.input.value = response.result.value; ui.output.textContent = response.result.value + '%'; }
      if (action === 'mute') { muted = response.result.muted; muteButton.textContent = muted ? '♫ Unmute' : '♫ Mute'; muteButton.setAttribute('aria-pressed', String(muted)); }
    } catch (error) { controlStatus.textContent = error.message; }
    finally {
      if (ui) { ui.pending = false; ui.input.disabled = false; } else { mutePending = false; muteButton.disabled = false; }
    }
  }
  function openControls() {
    if (!shade.hidden) return;
    previousFocus = document.activeElement; keyboardWasShown = KB.shown; KB.hide();
    shade.hidden = false; document.getElementById('app').inert = true;
    toggle.setAttribute('aria-expanded', 'true'); controlStatus.textContent = 'Reading device…';
    keyboardButton.disabled = !keyboardTarget();
    screenshotButton.disabled = muteButton.disabled = true;
    for (const ui of Object.values(controls)) ui.input.disabled = true;
    closeButton.focus(); controlAbort = new AbortController(); refreshControls();
    if (!recordingPending) refreshRecording();
  }
  function closeControls(restore = true) {
    if (shade.hidden) return;
    shade.hidden = true; document.getElementById('app').inert = false;
    controlAbort?.abort(); clearTimeout(controlTimer); toggle.setAttribute('aria-expanded', 'false');
    if (restore) {
      const focus = previousFocus?.isConnected ? previousFocus : toggle; focus.focus({ preventScroll: true });
      if (keyboardWasShown && keyboardTarget()) { keyboardTarget().focus({ preventScroll: true }); KB.show(); } else KB.hide();
    }
  }
  shade.onclick = event => { if (event.target === shade) closeControls(); };
  // Range sliders must not summon the text keyboard from the legacy input listener.
  document.addEventListener('focusin', event => { if (shade.contains(event.target)) event.stopImmediatePropagation(); }, true);
  document.addEventListener('keydown', event => {
    if (shade.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); closeControls(); }
    else if (event.key === 'Tab') {
      const nodes = [...panel.querySelectorAll('button:not(:disabled), input:not(:disabled)')];
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    event.stopImmediatePropagation();
  }, true);
  function swipe(element, direction, action) {
    let start = null;
    element.addEventListener('pointerdown', event => {
      if (event.target.closest('button,input')) return;
      start = { x: event.clientX, y: event.clientY, id: event.pointerId }; element.setPointerCapture(event.pointerId);
    });
    element.addEventListener('pointerup', event => {
      if (start && start.id === event.pointerId && (event.clientY - start.y) * direction > 45 && Math.abs(event.clientX - start.x) < 100) action();
      start = null;
    });
    element.addEventListener('pointercancel', () => { start = null; });
  }
  swipe(document.querySelector('.topbar'), 1, openControls);
  swipe(document.querySelector('.sysline'), 1, openControls);
  swipe(heading, -1, () => closeControls()); swipe(grip, -1, () => closeControls());
  window.TouchDeck = { openControls, closeControls };
})();
