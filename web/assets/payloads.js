/* Scripts copied onto the SD card or uploaded from another browser. */
async function payloadApi(path, body) {
  const response = await fetch('/api/payloads' + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}

function payloadPage(title, detail = false) {
  if (typeof KB !== 'undefined') KB.hide();
  const content = document.querySelector('.content');
  content.innerHTML = '';
  content.scrollTop = 0;
  const page = el('div', 'payload-page');
  page.dataset.detail = detail ? 'yes' : 'no';
  const head = el('div', 'section-head');
  head.appendChild(el('h2', null, title));
  page.appendChild(head);
  content.appendChild(page);
  document.getElementById('btn-back').style.display = 'flex';
  return page;
}

document.getElementById('btn-back').addEventListener('click', event => {
  const page = document.querySelector('.payload-page');
  if (!page) return;
  event.stopImmediatePropagation();
  if (typeof KB !== 'undefined') KB.hide();
  if (page.dataset.detail === 'yes') showPayloads();
  else showCustomTools();
}, true);

async function showPayloads() {
  const page = payloadPage('Python Payloads');
  const tip = el('div', 'payload-note', 'Loading scripts…');
  const message = el('div', 'payload-message');
  message.setAttribute('role', 'status');
  const actions = el('div', 'run-row');
  const upload = el('button', 'set-btn', '＋ Add .py file');
  const refresh = el('button', 'set-btn', '↻ Refresh');
  const picker = el('input');
  picker.type = 'file'; picker.accept = '.py'; picker.hidden = true;
  actions.append(upload, refresh, picker);
  const list = el('div', 'tool-list');
  page.append(tip, actions, message, list);
  upload.onclick = () => picker.click();
  refresh.onclick = () => loadList();
  picker.onchange = async () => {
    const file = picker.files[0];
    if (!file) return;
    upload.disabled = true;
    try {
      if (!file.name.endsWith('.py') || file.size > 1024 * 1024) {
        throw new Error('Choose a .py file no larger than 1 MiB.');
      }
      const source = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
      await payloadApi('/upload', { name: file.name, source });
      message.textContent = 'Added ' + file.name;
      await loadList();
    } catch (error) { message.textContent = error.message; }
    finally { upload.disabled = false; picker.value = ''; }
  };
  async function loadList() {
    refresh.disabled = true;
    try {
      const data = await payloadApi('');
      if (!page.isConnected) return;
      tip.textContent = 'Copy .py scripts into ' + data.directory + ', or add a file below. Tap a script to run it.';
      list.replaceChildren();
      if (!data.scripts.length) list.appendChild(el('div', 'payload-note', 'No Python scripts yet.'));
      for (const script of data.scripts) {
        const button = el('button', 'tool-btn');
        button.appendChild(el('span', 'ch', 'Py'));
        const mid = el('span', 'tb-mid');
        mid.appendChild(el('span', null, script.name));
        mid.appendChild(el('span', 'sub', Math.max(1, Math.ceil(script.size / 1024)) + ' KB · Python 3'));
        button.appendChild(mid);
        button.onclick = () => showPayload(script.name);
        list.appendChild(button);
      }
    } catch (error) { message.textContent = error.message; }
    finally { refresh.disabled = false; }
  }
  await loadList();
}

function showPayload(name) {
  const page = payloadPage(name, true);
  const field = el('div', 'field');
  const label = el('label', null, 'Arguments (optional)');
  const args = el('input'); args.type = 'text'; args.id = 'payload-args';
  args.placeholder = 'Example: --count 5 "hello world"'; label.htmlFor = args.id;
  field.append(label, args);
  const row = el('div', 'run-row');
  const run = el('button', 'big-btn run', '▶ RUN');
  const stop = el('button', 'big-btn stop', '■ STOP');
  run.disabled = true; stop.disabled = true;
  row.append(run, stop);
  const status = el('div', 'payload-note', 'Checking status…');
  const message = el('div', 'payload-message'); message.setAttribute('role', 'status');
  const output = el('pre', 'console payload-output'); output.setAttribute('aria-label', 'Script output');
  const inputRow = el('div', 'term-input-row');
  const input = el('input'); input.type = 'text'; input.placeholder = 'Input for the running script';
  input.setAttribute('aria-label', 'Script input'); input.maxLength = 4000;
  const send = el('button', 'set-btn', 'Send'); send.disabled = true;
  inputRow.append(input, send);
  page.append(field, row, status, message, output, inputRow);
  let current = null;
  let busy = false;
  function render(value) {
    current = value;
    const mine = value.name === name;
    run.disabled = value.running || busy;
    stop.disabled = !mine || !value.running || value.stopping || busy;
    send.disabled = !mine || !value.running || value.stopping || busy;
    if (mine) {
      const following = output.scrollHeight - output.scrollTop - output.clientHeight < 30;
      output.textContent = value.output || 'Waiting for output…';
      if (following) output.scrollTop = output.scrollHeight;
      status.textContent = value.stopping ? 'Stopping…' : value.running ? 'Running · ' + name : 'Finished · exit code ' + value.exit_code;
    } else {
      status.textContent = value.running ? value.name + ' is running. Open that script to stop it.' : 'Ready · runs as the device user';
    }
  }
  async function action(path, body) {
    busy = true; run.disabled = stop.disabled = send.disabled = true;
    message.textContent = '';
    try { await payloadApi(path, body); }
    catch (error) { message.textContent = error.message; }
    finally {
      busy = false;
      try { const value = await payloadApi('/status'); if (page.isConnected) render(value); }
      catch (error) { message.textContent = error.message; }
    }
  }
  run.onclick = () => { if (typeof KB !== 'undefined') KB.hide(); action('/run', { name, arguments: args.value }); };
  stop.onclick = () => action('/stop', { run_id: current.run_id });
  send.onclick = async () => {
    const text = input.value;
    await action('/input', { run_id: current.run_id, text });
    if (!message.textContent) input.value = '';
  };
  input.onkeydown = event => { if (event.key === 'Enter' && !send.disabled) { event.preventDefault(); send.click(); } };
  async function poll() {
    if (!page.isConnected) return;
    try { const value = await payloadApi('/status'); if (page.isConnected && !busy) render(value); }
    catch (error) { if (page.isConnected) { message.textContent = error.message; run.disabled = stop.disabled = send.disabled = true; } }
    if (page.isConnected) setTimeout(poll, 750);
  }
  poll();
}
