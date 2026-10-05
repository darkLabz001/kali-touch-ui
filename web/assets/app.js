const state = { data: null, section: null, tool: null, running: false, evtSource: null, wordlists: [], terminal: false, termSend: null };

const icons = {
  radar: "◉", search: "◎", globe: "◍", key: "❋", wifi: "✱",
  lock: "▣", shield: "◆", tool: "⚒", root: "⚑", settings: "⚙", bt: "◉",
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function mkStatCell(lab, val, cls) {
  const b = el("div", "re-stat");
  b.append(el("span", "re-stat-lab", lab),
    el("span", "re-stat-val" + (cls ? " " + cls : ""), val));
  return b;
}

function initTelemetry() {
  const clk = document.getElementById("sl-clock");
  const net = document.getElementById("sl-net");
  const tmp = document.getElementById("sl-tmp");
  let miss = 0, lastNet = null, lastTmp = null;
  setInterval(() => { if (clk) clk.textContent = new Date().toTimeString().slice(0, 5); }, 1000);
  (async function poll() {
    try {
      const j = await fetch("/api/sysinfo?t=" + Date.now()).then(r => r.json());
      const i = j.info || j;
      if (i.ssid) { miss = 0; lastNet = i.ssid; }
      else if (++miss > 3) { lastNet = "no-wifi"; }
      if (i.temp) lastTmp = i.temp + "°C";
      if (net && lastNet) net.textContent = lastNet;
      if (tmp && lastTmp) tmp.textContent = lastTmp;
    } catch (e) {}
    setTimeout(poll, 5000);
  })();
}

async function api(path, method = "GET", body) {
  const opt = { method, headers: {} };
  if (body) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  return r.json();
}

let touchUiLoading = false;
async function load() {
  if (touchUiLoading) return;
  touchUiLoading = true;
  try {
    const response = await fetch('/api/tools', { signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error('Tools unavailable');
    state.data = await response.json();
    showHome();
    window.dispatchEvent(new Event('touchui:ready'));
    api('/api/wordlists').then(data => { state.wordlists = data.wordlists || []; }).catch(() => {});
  } catch (error) {
    window.dispatchEvent(new Event('touchui:loading-error'));
    setTimeout(load, 1500);
  } finally { touchUiLoading = false; }
}

function showHome() {
  state.section = null; state.tool = null; state.settings = false; state.terminal = false;
  document.querySelector(".btn-back").style.display = "none";
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const grid = el("div", "grid");
  const mkc = (eyebrow, ico, t, stat, cls, fn) => {
    const card = el("div", "card" + (cls ? " " + cls : ""));
    const top = el("div", "card-eyebrow");
    top.appendChild(el("span", "dot", ""));
    top.appendChild(el("span", null, eyebrow));
    card.appendChild(top);
    card.appendChild(el("div", "ico", ico));
    card.appendChild(el("div", "t", t));
    const st = el("div", "card-stat");
    st.appendChild(el("span", "card-stat-dots", "· · ·"));
    st.appendChild(el("span", null, stat));
    card.appendChild(st);
    card.onclick = fn;
    return card;
  };
  const ready = state.data.launchers.filter(x => x.exists).length;
  grid.appendChild(mkc("self-built", "◈", "Custom Tools", "12 apps", "acc-cy", () => showCustomTools()));
  grid.appendChild(mkc("launcher", "⚒", "Click-Run Tools", ready + "/" + state.data.launchers.length + " ready", "acc-gr", () => showLaunchers()));
  state.data.sections.forEach(([id, title, ico]) => {
    const n = state.data.tools.filter(t => t.section === id).length;
    grid.appendChild(mkc("module", icons[ico] || "•", title, n + " tools", "", () => showSection(id, title)));
  });
  c.appendChild(grid);
}

function showSection(id, title) {
  state.section = id; state.tool = null; state.settings = false; state.terminal = false;
  const c = document.querySelector(".content");
  document.querySelector(".btn-back").style.display = "flex";
  c.innerHTML = "";
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, title));
  head.appendChild(el("div", "hint", window.innerWidth + "×" + window.innerHeight));
  c.appendChild(head);
  const list = el("div", "tool-list");
  state.data.tools.filter(t => t.section === id).forEach(t => {
    const b = el("div", "tool-btn");
    b.appendChild(el("div", "ch", t.root ? "⚑" : "⚒"));
    b.appendChild(el("div", null, t.label));
    if (t.root) b.appendChild(el("div", "root-tag", "root"));
    b.onclick = () => showRun(t);
    list.appendChild(b);
  });
  c.appendChild(list);
}

/* ================= Click-Run tools ================= */

const LGROUP = ["WiFi", "BLE", "Net", "Web", "Auth", "Crack"];
let termInit = null;

function launchBtn(l) {
  const b = el("div", "tool-btn");
  if (!l.exists) b.classList.add("ismiss");
  b.appendChild(el("div", "ch", l.icon));
  const mid = el("div", "tb-mid");
  mid.appendChild(el("div", null, l.label));
  const sub = el("div", "sub" + (l.exists ? "" : " miss"));
  sub.textContent = l.exists ? l.bin : "missing — tap to install (" + l.pkg + ")";
  mid.appendChild(sub);
  b.appendChild(mid);
  if (l.root) b.appendChild(el("div", "root-tag", "root"));
  b.onclick = () => {
    if (!l.exists) { installLaunch(l, sub); return; }
    termInit = { title: l.label, cmd: (l.root ? "sudo -n " : "") + l.bin };
    showTerminal(termInit.title, termInit.cmd);
  };
  return b;
}

function customApps() {
  return [
    ["Py", "Python Payloads", "add your own .py scripts · run and view output", "#7ee0ff", showPayloads],
    ["◉", "Recon — PineAP", "live AP scan · signal graph · deauth", "#39ff14", showRecon],
    ["✕", "Handshake Hunter", "capture handshakes · crack with hashcat", "#00d9ff", showHunter],
    ["◎", "WiFi Radar", "live radar sweep of scanned APs", "#ffc93d", showRadar],
    ["◈", "Wardrive", "phone-GPS drive · QR page · WiGLE CSV", "#ff7ab8", showWardrive],
    ["⚑", "Rogue AP", "evil twin · captive portal · cred capture", "#ffb300", showRogue],
    ["◉", "Probe Tracker", "who's prospecting which SSIDs · feeds flood", "#39ff14", showProbe],
    ["⚡", "Deauth Blaster", "targeted (or everyone) deauth", "#ff5c39", showDeauth],
    ["◐", "Beacon Flood", "fake SSIDs · borrow probed names", "#d0a8ff", showFlood],
    ["✪", "Portal Kit", "phishing portal themes · clone-a-login", "#4fd1ff", showPortal],
    ["❒", "Login Clone", "clone a login page onto the portal", "#7bffb0", showClone],
    ["⛧", "Auto-Pentest", "capture→deauth→crack→decrypt one-press", "#ff5577", showPentest],
  ];
}

function showCustomTools() {
  state.section = null; state.tool = null; state.settings = false; state.terminal = false; state.running = false;
  const c = document.querySelector(".content");
  document.querySelector(".btn-back").style.display = "flex";
  c.innerHTML = "";
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "◈ Custom Tools"));
  head.appendChild(el("div", "hint", "12 apps · self-built"));
  c.appendChild(head);
  const list = el("div", "tool-list");
  const apps = customApps();
  apps.forEach(([ico, title, sub, col, fn]) => {
    const b = el("div", "tool-btn");
    const ch = el("div", "ch", ico);
    ch.style.color = col;
    ch.style.borderColor = col;
    b.appendChild(ch);
    const mid = el("div", "tb-mid");
    mid.appendChild(el("div", null, title));
    mid.appendChild(el("div", "sub", sub));
    b.appendChild(mid);
    b.appendChild(el("div", "root-tag", "go"));
    b.onclick = () => fn();
    list.appendChild(b);
  });
  c.appendChild(list);
}

function showLaunchers() {
  state.section = null; state.tool = null; state.settings = false; state.terminal = false;
  const c = document.querySelector(".content");
  document.querySelector(".btn-back").style.display = "flex";
  c.innerHTML = "";
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "⚒ Click-Run Tools"));
  head.appendChild(el("div", "hint", "tap a tool to launch it"));
  c.appendChild(head);
  const list = el("div", "tool-list");
  const order = {};
  LGROUP.forEach((g, i) => order[g] = i);
  const launchers = state.data.launchers.slice().sort((a, b) => {
    return (order[a.group] ?? 9) - (order[b.group] ?? 9) || (a.label.localeCompare(b.label));
  });
  launchers.forEach(l => list.appendChild(launchBtn(l)));
  c.appendChild(list);
}

function installLaunch(l, sub) {
  sub.classList.add("miss");
  sub.textContent = "installing " + l.pkg + "…";
  api("/api/launch/install", "POST", { id: l.id }).then(async r => {
    if (!r.ok && r.error) {
      sub.textContent = "install error: " + r.error;
      return;
    }
    const poll = async () => {
      try {
        const st = await api("/api/launch/status");
        if (st.busy) { setTimeout(poll, 2500); return; }
        load();
      } catch (e) { setTimeout(poll, 2500); }
    };
    poll();
  }).catch(() => { sub.textContent = "install failed to start"; });
}

/* ================= Settings ================= */

let wifiNets = [];

function showSettings() {
  state.settings = true; state.tool = null; state.section = null; state.terminal = false;
  document.querySelector(".btn-back").style.display = "flex";
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "settings-page");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "⚙ Settings"));
  page.appendChild(head);

  const wifiCard = el("div", "set-card");
  wifiCard.appendChild(el("div", "set-title", "WiFi"));
  const statusRow = el("div", "wifi-status");
  wifiCard.appendChild(statusRow);
  const scanBtn = el("button", "set-btn", "📶 Scan networks");
  wifiCard.appendChild(scanBtn);
  const netList = el("div", "net-list");
  wifiCard.appendChild(netList);
  page.appendChild(wifiCard);

  const infoCard = el("div", "set-card");
  infoCard.appendChild(el("div", "set-title", "Device info"));
  const infoBody = el("div", "info-body");
  infoCard.appendChild(infoBody);
  page.appendChild(infoCard);

  const otaCard = el("div", "set-card");
  otaCard.appendChild(el("div", "set-title", "⚡ OTA Update"));
  otaCard.id = "ota-card";
  const otaMeta = el("div", "ota-meta", "checking…");
  const otaBtns = el("div", "ota-btns");
  const otaCheck = el("button", "set-btn", "⟳ Check");
  const otaUpd = el("button", "set-btn warn", "⬇ Update");
  otaUpd.disabled = true;
  otaBtns.appendChild(otaCheck);
  otaBtns.appendChild(otaUpd);
  const otaLog = el("div", "ota-log");
  otaLog.style.display = "none";
  const otaBar = el("div", "ota-bar");
  const otaFill = el("div", "ota-fill");
  otaBar.appendChild(otaFill);
  otaCard.appendChild(otaMeta);
  otaCard.appendChild(otaBtns);
  otaCard.appendChild(otaBar);
  otaCard.appendChild(otaLog);
  page.appendChild(otaCard);

  const aptCard = el("div", "set-card");
  aptCard.appendChild(el("div", "set-title", "⬆ System Upgrade"));
  const aptMeta = el("div", "ota-meta");
  const aptBtn = el("button", "set-btn warn", "⬆ Upgrade packages");
  aptBtn.disabled = true;
  const aptBar = el("div", "ota-bar");
  const aptFill = el("div", "ota-fill");
  aptBar.appendChild(aptFill);
  const aptLog = el("div", "ota-log");
  aptLog.style.display = "none";
  aptCard.appendChild(aptMeta);
  aptCard.appendChild(aptBtn);
  aptCard.appendChild(aptBar);
  aptCard.appendChild(aptLog);
  page.appendChild(aptCard);
  c.appendChild(page);

  scanBtn.onclick = () => doWifiScan(scanBtn, netList, statusRow);
  otaCheck.onclick = () => { otaMeta.textContent = "Checking GitHub…"; refreshOta(otaMeta, otaLog, otaUpd, otaCheck, otaBar, otaFill, true); };
  otaUpd.onclick = () => otaRun(otaMeta, otaLog, otaUpd, otaCheck, otaBar, otaFill);
  aptBtn.onclick = () => aptRun(aptMeta, aptBtn, aptLog, aptBar, aptFill);
  refreshOta(otaMeta, otaLog, otaUpd, otaCheck, otaBar, otaFill);
  aptStatus(aptMeta, aptBtn, aptLog, aptBar, aptFill);

  api("/api/network").then(net => {
    renderNetworkInfo(infoBody, net.info);
  }).catch(() => { infoBody.textContent = "Device info unavailable"; });
  api("/api/wifi/scan").then(scan => {
    if (!scan.error) {
      wifiNets = scan.networks;
      renderNetList(netList, scan.networks, statusRow);
    } else {
      statusRow.textContent = "scan: " + scan.error;
    }
  }).catch(() => {
    statusRow.textContent = "backend unreachable";
  });
}

function setProgressBar(bar, fill, pct) {
  bar.style.display = "block";
  bar.setAttribute("role", "progressbar"); bar.setAttribute("aria-valuemin", "0"); bar.setAttribute("aria-valuemax", "100");
  if (pct == null) {
    bar.removeAttribute("aria-valuenow");
    fill.classList.add("indet");
    fill.style.width = "";
  } else {
    bar.setAttribute("aria-valuenow", String(Math.max(0, Math.min(100, Number(pct)))));
    fill.classList.remove("indet");
    fill.style.width = Math.max(2, Math.min(100, Number(pct))) + "%";
  }
}
function hideProgressBar(bar, fill) {
  bar.style.display = "none";
  fill.classList.remove("indet");
  fill.style.width = "";
}

function refreshOta(meta, logBox, updBtn, chkBtn, bar, fill, force = false) {
  if (!meta.isConnected || bar.dataset.polling === "1") return;
  bar.dataset.polling = "1";
  api("/api/ota/status" + (force ? "?check=1" : "")).then(s => {
    delete bar.dataset.polling;
    if (!meta.isConnected) return;
    const labels = {checking:"Checking installation",downloading:"Downloading",applying:"Applying files",verifying:"Verifying code",configuring:"Preparing services",restarting:"Restarting device UI",done:"Update complete",failed:"Update failed"};
    const stage = labels[s.stage] || "Working";
    bar.dataset.stage = s.stage || "idle";
    meta.dataset.stage = s.stage || "idle";
    if (s.log) showOtaLog(logBox, s.log);
    if (s.busy) {
      bar.dataset.updating = "1"; bar.dataset.retries = "0";
      meta.textContent = stage + (s.phase_pct != null ? " · " + s.phase_pct + "% downloaded" : "") + " — " + (s.message || "Please wait…");
      setProgressBar(bar, fill, s.pct); bar.setAttribute("aria-valuetext", meta.textContent);
      updBtn.disabled = chkBtn.disabled = true;
      clearTimeout(bar._otaTimer);
      bar._otaTimer = setTimeout(() => refreshOta(meta, logBox, updBtn, chkBtn, bar, fill), 1000);
      return;
    }
    delete bar.dataset.updating;
    chkBtn.disabled = false;
    if (s.status === "failed") {
      meta.textContent = "Update failed — " + (s.error || s.message || "Tap Retry.");
      updBtn.textContent = "↻ Retry update"; updBtn.disabled = false;
      setProgressBar(bar, fill, s.pct || 0); bar.setAttribute("aria-valuetext", meta.textContent);
      return;
    }
    if (s.status === "complete") {
      meta.textContent = (s.message || "Update installed successfully.") + " · " + s.local_short;
      setProgressBar(bar, fill, 100); bar.setAttribute("aria-valuetext", meta.textContent);
      updBtn.disabled = s.up_to_date; updBtn.textContent = "⬇ Update";
      if (bar.dataset.started === "1") { delete bar.dataset.started; setTimeout(() => location.reload(), 1500); }
      return;
    }
    hideProgressBar(bar, fill);
    if (!s.installed) { meta.textContent = "OTA unavailable: installation is not a Git checkout."; updBtn.disabled = true; return; }
    meta.textContent = "Installed " + s.local_short + " · GitHub " + (s.remote_short || "unreachable") + " · " + (!s.remote ? "Check failed — try again" : s.up_to_date ? "Up to date" : "Update available");
    updBtn.disabled = s.up_to_date || !s.remote;
  }).catch(() => {
    delete bar.dataset.polling;
    if (!meta.isConnected) return;
    if (bar.dataset.updating === "1") {
      const retries = Number(bar.dataset.retries || 0) + 1; bar.dataset.retries = String(retries);
      if (retries < 45) {
        meta.textContent = "Waiting for the device to reconnect…";
        bar._otaTimer = setTimeout(() => refreshOta(meta, logBox, updBtn, chkBtn, bar, fill), 1500);
        return;
      }
      delete bar.dataset.updating;
      meta.textContent = "Could not confirm completion. Tap Check when the device reconnects.";
    } else meta.textContent = "Device unreachable — tap Check to retry.";
    chkBtn.disabled = false; updBtn.disabled = true;
  });
}

function showOtaLog(logBox, txt) {
  logBox.style.display = "block";
  logBox.innerHTML = "";
  (txt || "").split("\n").filter(Boolean).slice(-30).forEach(l => {
    const d = el("div", "ota-line", l);
    if (/fail|rollback|error/i.test(l)) d.classList.add("err");
    logBox.appendChild(d);
  });
}

function armConfirm(btn, label, action) {
  if (btn.dataset.armed === "1") {
    delete btn.dataset.armed;
    btn.classList.remove("confirming");
    btn.textContent = label;
    action();
    return;
  }
  btn.dataset.armed = "1";
  btn.classList.add("confirming");
  btn.textContent = "Tap again to confirm";
  setTimeout(() => {
    if (btn.dataset.armed === "1") {
      delete btn.dataset.armed;
      btn.classList.remove("confirming");
      btn.textContent = label;
    }
  }, 3500);
}

function otaRun(meta, logBox, updBtn, chkBtn, bar, fill) {
  if (updBtn.dataset.armed !== "1") {
    armConfirm(updBtn, "⬇ Update", () => otaRun(meta, logBox, updBtn, chkBtn, bar, fill));
    return;
  }
  delete updBtn.dataset.armed; updBtn.classList.remove("confirming");
  updBtn.textContent = "⬇ Update"; updBtn.disabled = chkBtn.disabled = true;
  meta.textContent = "Starting update…"; bar.dataset.stage = "checking";
  setProgressBar(bar, fill, 0);
  api("/api/ota/update", "POST").then(r => {
    if (!r.ok) {
      meta.textContent = "Update could not start — " + (r.msg || r.error || "Try again.");
      bar.dataset.stage = "failed"; updBtn.disabled = chkBtn.disabled = false;
      return;
    }
    bar.dataset.started = bar.dataset.updating = "1";
    refreshOta(meta, logBox, updBtn, chkBtn, bar, fill);
  }).catch(() => {
    meta.textContent = "Could not start update: device unreachable.";
    bar.dataset.stage = "failed"; updBtn.disabled = chkBtn.disabled = false;
  });
}

function aptStatus(meta, btn, logBox, bar, fill) {
  api("/api/apt/status").then(s => {
    if (s.busy) {
      meta.textContent = "upgrading · " + (s.stage || "working");
      setProgressBar(bar, fill, s.pct);
      showOtaLog(logBox, s.log);
      btn.disabled = true;
      setTimeout(() => aptStatus(meta, btn, logBox, bar, fill), 2500);
    } else {
      hideProgressBar(bar, fill);
      btn.disabled = false;
      const n = (s.log || "").split("\n").filter(Boolean).length;
      meta.textContent = n ? "idle · last upgrade " + n + " log lines" : "idle";
    }
  }).catch(() => {
    meta.textContent = "backend unreachable";
  });
}

function aptRun(meta, btn, logBox, bar, fill) {
  if (btn.dataset.armed !== "1") {
    armConfirm(btn, "⬆ Upgrade packages", () => aptRun(meta, btn, logBox, bar, fill));
    return;
  }
  delete btn.dataset.armed;
  btn.classList.remove("confirming");
  btn.textContent = "⬆ Upgrade packages";
  btn.disabled = true;
  meta.textContent = "starting…";
  setProgressBar(bar, fill, null);
  api("/api/apt/upgrade", "POST").then(r => {
    if (!r.ok && r.error) {
      meta.textContent = r.error;
      hideProgressBar(bar, fill);
      btn.disabled = false;
      return;
    }
    meta.textContent = "upgrading · working";
    setTimeout(() => aptStatus(meta, btn, logBox, bar, fill), 2000);
  }).catch(e => {
    meta.textContent = "start failed: " + e;
    hideProgressBar(bar, fill);
    btn.disabled = false;
  });
}

function renderNetworkInfo(body, info) {
  body.innerHTML = "";
  const rows = [
    ["Hostname", info.hostname],
    ["OS", info.os],
    ["IP address", info.ip || "—"],
    ["Kernel", info.kernel],
    ["Arch", info.arch],
    ["Uptime", info.uptime || "—"],
    ["WiFi iface", info.wifi_iface],
  ];
  rows.forEach(([k, v]) => {
    const r = el("div", "info-row");
    r.appendChild(el("div", "info-k", k));
    r.appendChild(el("div", "info-v", v));
    body.appendChild(r);
  });
  const actions = el("div", "sys-actions");
  const reboot = el("button", "set-btn warn", "⟳ Reboot");
  const shutdown = el("button", "set-btn danger", "⏻ Shutdown");
  reboot.onclick = () => { if (confirm("Reboot device?")) api("/api/reboot", "POST"); };
  shutdown.onclick = () => { if (confirm("Shut down device?")) api("/api/shutdown", "POST"); };
  actions.appendChild(reboot);
  actions.appendChild(shutdown);
  body.appendChild(actions);
}

async function doWifiScan(btn, netList, statusRow) {
  btn.disabled = true;
  btn.textContent = "scanning…";
  statusRow.textContent = "Scanning…";
  try {
    const scan = await api("/api/wifi/scan");
    if (scan.error) {
      statusRow.textContent = "scan: " + scan.error;
    } else {
      wifiNets = scan.networks;
      statusRow.textContent = wifiNets.length + " networks found";
      renderNetList(netList, wifiNets, statusRow);
    }
  } catch (e) {
    statusRow.textContent = "scan failed";
  }
  btn.disabled = false;
  btn.textContent = "📶 Rescan";
  btn.classList.add("scanned");
}

function renderNetList(netList, nets, statusRow) {
  netList.innerHTML = "";
  netList.classList.toggle("empty", nets.length === 0);
  if (nets.length === 0) {
    netList.appendChild(el("div", "net-empty", "no networks found"));
    return;
  }
  nets.forEach(n => {
    const item = el("div", "net-item");
    const left = el("div", "net-main");
    const name = el("div", "net-name", n.essid || "(hidden)");
    left.appendChild(name);
    const meta = el("div", "net-meta", [n.enc, n.channel ? "ch " + n.channel : "", n.signal ? n.signal + " dBm" : ""].filter(Boolean).join(" · "));
    left.appendChild(meta);
    item.appendChild(left);
    const sig = el("div", "net-sig");
    sig.style.setProperty("--q", n.quality);
    sig.appendChild(el("div", null, n.essid ? "▮".repeat(3) : "?"));
    item.appendChild(sig);
    item.onclick = () => connectPrompt(n, statusRow);
    netList.appendChild(item);
  });
}

function connectPrompt(net, statusRow) {
  if (!net.essid) {
    statusRow.textContent = "hidden network — no SSID to connect to";
    return;
  }
  const wrap = el("div", "connect-box");
  const f = el("div", "field");
  f.appendChild(el("label", null, "Password for " + net.essid + (net.enc === "Open" ? " (open network — leave blank)" : "")));
  const inp = el("input");
  inp.type = "text";
  inp.setAttribute("autocomplete", "off");
  inp.setAttribute("spellcheck", "false");
  f.appendChild(inp);
  wrap.appendChild(f);
  const row = el("div", "run-row");
  const conn = el("button", "big-btn run", "Connect");
  const back = el("button", "big-btn stop", "Cancel");
  row.appendChild(conn);
  row.appendChild(back);
  wrap.appendChild(row);
  const holder = document.querySelector(".settings-page .net-list");
  holder.innerHTML = "";
  holder.appendChild(wrap);
  conn.onclick = async () => {
    statusRow.textContent = "connecting to " + net.essid + "…";
    const res = await api("/api/wifi/connect", "POST", { ssid: net.essid, password: inp.value });
    if (res.ok) statusRow.textContent = "✓ connected: " + (res.ip || net.essid);
    else statusRow.textContent = "✗ " + (res.error || "connect failed");
  };
  back.onclick = () => renderNetList(holder, wifiNets, statusRow);
  setTimeout(() => inp.focus(), 100);
}

const LABELS = {
  target: "Target (host / IP / URL)",
  bssid: "BSSID",
  user: "Username",
  pass: "Password",
  wordlist: "Wordlist",
  hashmode: "Hash mode (john = auto / hashcat)", 
};
const PLACEHOLDERS = {
  target: "ex: 192.168.1.1",
  bssid: "AA:BB:CC:DD:EE:FF",
  user: "admin",
  pass: "password",
  hashmode: "0 (MD5) · 1000 (NTLM) · 22000 (WPA)",
};

function showRun(tool) {
  state.tool = tool; state.settings = false; state.terminal = false;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  document.querySelector(".btn-back").style.display = "flex";
  const page = el("div", "run-page");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, tool.label));
  if (tool.root) head.appendChild(el("div", "hint", "⚠ requires root"));
  page.appendChild(head);

  const runBtn = el("button", "big-btn run", "▶ RUN");
  const stopBtn = el("button", "big-btn stop", "■ STOP");
  const row = el("div", "run-row");
  stopBtn.disabled = true;
  runBtn.onclick = () => startRun(tool, runBtn, stopBtn);
  stopBtn.onclick = () => stopRun(stopBtn);

  if (tool.need && tool.pkg) {
    const banner = el("div", "missing-banner");
    const btitle = el("div", "missing-title", "⚠ " + tool.label + " is not installed");
    const binfo = el("div", "missing-sub", "binary “" + tool.bin + "” missing");
    const ibtn = el("button", "big-btn inst", "⬇ Install " + tool.pkg);
    ibtn.onclick = () => installTool(tool, btitle, ibtn, binfo, runBtn, banner);
    banner.appendChild(btitle);
    banner.appendChild(binfo);
    banner.appendChild(ibtn);
    page.appendChild(banner);
    runBtn.disabled = true;
  }

  tool.params.forEach(p => {
    const f = el("div", "field");
    f.dataset.param = p;
    if (p === "wordlist") {
      f.appendChild(el("label", null, LABELS[p]));
      const sel = el("select");
      const auto = el("option", null, "Auto — best available (rockyou / SecLists)");
      auto.value = "";
      sel.appendChild(auto);
      state.wordlists.forEach(w => {
        const o = el("option", null, w.name + "  (" + w.path + ")");
        o.value = w.path;
        sel.appendChild(o);
      });
      f.appendChild(sel);
    } else {
      f.appendChild(el("label", null, LABELS[p] || p));
      const inp = el("input");
      inp.setAttribute("autocomplete", "off");
      inp.setAttribute("spellcheck", "false");
      inp.placeholder = PLACEHOLDERS[p] || "";
      if (p === "pass") inp.type = "text";
      f.appendChild(inp);
    }
    page.appendChild(f);
  });

  row.appendChild(stopBtn);
  page.appendChild(row);

  if (tool.params.includes("target")) {
    const extra = el("div", "run-extra");
    const torLbl = el("label", "tor-toggle");
    const torChk = el("input");
    torChk.type = "checkbox";
    torChk.id = "run-tor";
    const torTxt = el("span", null, " route via Tor (proxychains)");
    torLbl.append(torChk, torTxt);
    extra.appendChild(torLbl);
    page.appendChild(extra);
  }

  const console = el("pre", "console");
  page.appendChild(console);
  c.appendChild(page);
}

function startRun(tool, runBtn, stopBtn) {
  const page = document.querySelector(".run-page");
  const console = page.querySelector(".console");
  const params = {};
  tool.params.forEach(p => {
    const f = page.querySelector('.field[data-param="' + p + '"]');
    const control = f ? (f.querySelector("select") || f.querySelector("input")) : null;
    params[p] = control ? control.value : "";
  });
  params.section = tool.section;
  params.label = tool.label;
  const torChk = document.getElementById("run-tor");
  params.tor = !!(torChk && torChk.checked);
  console.textContent = "";
  state.running = true;
  api("/api/run", "POST", params);
  runBtn.disabled = true;
  stopBtn.disabled = false;
  openStream(console);
}

function stopRun(stopBtn) {
  api("/api/stop", "POST");
  stopBtn.disabled = true;
  if (state.evtSource) state.evtSource.close();
  state.running = false;
}

function installTool(tool, title, btn, sub, runBtn, banner) {
  if (btn.dataset.armed !== "1") {
    armConfirm(btn, "⬇ Install " + tool.pkg, () => installTool(tool, title, btn, sub, runBtn, banner));
    return;
  }
  delete btn.dataset.armed;
  btn.classList.remove("confirming");
  title.textContent = "installing " + tool.pkg + " …";
  sub.textContent = "";
  btn.textContent = "…";
  btn.disabled = true;
  const console = document.querySelector(".run-page .console");
  api("/api/install", "POST", { pkg: tool.pkg }).then(() => {
    const t = setInterval(() => {
      api("/api/apt/status").then(s => {
        if (s.busy) {
          const p = s.pct != null ? s.pct + "%" : (s.stage || "…");
          btn.textContent = "installing " + tool.pkg + " · " + p;
          const lines = (s.log || "").split("\n").filter(Boolean);
          if (typeof console !== "undefined" && console) console.textContent = lines.slice(-24).join("\n");
        } else {
          clearInterval(t);
          api("/api/tools").then(d => {
            const fresh = (d.tools || []).find(x => x.section === tool.section && x.label === tool.label)
                      || { need: true, pkg: tool.pkg };
            tool.need = fresh.need;
            tool.pkg = fresh.pkg;
            tool.bin = fresh.bin;
            if (fresh.need) {
              title.textContent = "⚠ still missing — install failed (see console)";
              btn.textContent = "⬇ Retry " + tool.pkg;
              btn.disabled = false;
              const lines = (s.log || "").split("\n").filter(Boolean);
              if (console) console.textContent = lines.slice(-24).join("\n");
            } else {
              banner.style.display = "none";
              console.textContent = "✓ " + tool.pkg + " installed — ready to run.";
              runBtn.disabled = false;
            }
          }).catch(() => {
            banner.style.display = "none";
            runBtn.disabled = false;
          });
        }
      }).catch(() => {});
    }, 2500);
  }).catch(e => {
    title.textContent = "install failed: " + e;
    btn.textContent = "⬇ Retry " + tool.pkg;
    btn.disabled = false;
  });
}

function openStream(console) {
  if (state.evtSource) state.evtSource.close();
  const es = new EventSource("/sse");
  state.evtSource = es;
  es.onmessage = (e) => {
    const line = e.data.replace(/\r?\n$/, "");
    if (line === "") return;
    const span = el("span");
    span.textContent = line + "\n";
    if (/\[EXIT [^0]\]/.test(line)) span.className = "ex";
    else if (/\[EXIT 0\]/.test(line)) span.className = "done";
    console.appendChild(span);
    console.scrollTop = console.scrollHeight;
  };
  es.onerror = () => {};
}

/* ================= Terminal ================= */

const TCOL = ["#3a3f4a", "#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2", "#abb2bf"];
const TCOL_BRIGHT = ["#5c6370", "#ff5f56", "#48d597", "#f2c94c", "#66b8ff", "#d17fff", "#5ce1e6", "#ffffff"];
const termUI = { out: null, cur: null, buf: [], color: "#d6e2f0", bold: false, carry: "" };

function tEsc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function tRender() {
  const el = termUI.cur;
  if (!el) return;
  let h = "", color = "", bold = false, open = false;
  for (const seg of termUI.buf) {
    if (seg.color !== color || seg.bold !== bold) {
      if (open) h += "</span>";
      color = seg.color; bold = seg.bold; open = true;
      const st = [];
      if (color !== "#d6e2f0") st.push("color:" + color);
      if (bold) st.push("font-weight:700");
      h += st.length ? '<span style="' + st.join(";") + '">' : "<span>";
    }
    h += tEsc(seg.ch);
  }
  if (open) h += "</span>";
  el.innerHTML = h || "&nbsp;";
}

function tSgr(code) {
  const parts = code ? code.split(";").map(Number) : [0];
  for (const p of parts) {
    if (p === 0) { termUI.color = "#d6e2f0"; termUI.bold = false; }
    else if (p === 1) termUI.bold = true;
    else if (p === 22 || p === 23 || p === 24) termUI.bold = false;
    else if (p >= 30 && p <= 37) termUI.color = TCOL[p - 30];
    else if (p >= 90 && p <= 97) termUI.color = TCOL_BRIGHT[p - 90];
    else if (p === 39 || p === 49) termUI.color = "#d6e2f0";
  }
}

function tFeed(text) {
  if (!termUI.out) return;
  text = termUI.carry + text;
  const m = /(\x1b(\[[0-9;]*)?)$/.exec(text);
  if (m && m[1].length > 0) {
    termUI.carry = m[1];
    text = text.slice(0, m.index);
  } else {
    termUI.carry = "";
  }
  let i = 0, n = text.length;
  while (i < n) {
    const ch = text[i];
    if (ch === "\x1b") {
      if (text[i + 1] === "[") {
        let j = i + 2, code = "";
        while (j < n && !/[@-~]/.test(text[j])) { code += text[j]; j++; }
        if (j < n) {
          const fin = text[j];
          if (fin === "m") {
            tSgr(code);
          } else if ((fin === "J" && code === "2") || fin === "H" || (fin === "H" && (code === "" || code === "1;1" || code === ";"))) {
            termUI.out.innerHTML = "";
            const l = document.createElement("div");
            l.className = "term-line";
            termUI.out.appendChild(l);
            termUI.cur = l; termUI.buf = [];
          }
        }
        i = j + 1;
      } else {
        i += 2;
      }
      continue;
    }
    if (ch === "\x07") { i++; continue; }
    if (ch === "\n") {
      tRender();
      const l = document.createElement("div");
      l.className = "term-line";
      termUI.out.appendChild(l);
      termUI.cur = l;
      termUI.buf = [];
      i++;
      continue;
    }
    if (ch === "\r") {
      i++;
      if (text[i] !== "\n") {
        termUI.buf = [];
        tRender();
      }
      continue;
    }
    if (ch === "\t") {
      for (let k = 0; k < 4; k++) termUI.buf.push({ ch: " ", color: termUI.color, bold: termUI.bold });
      tRender();
      i++;
      continue;
    }
    if (ch === "\b") {
      termUI.buf.pop();
      tRender();
      i++;
      continue;
    }
    termUI.buf.push({ ch: ch, color: termUI.color, bold: termUI.bold });
    tRender();
    i++;
  }
  while (termUI.out.children.length > 1500) termUI.out.removeChild(termUI.out.firstChild);
}

let termSrc = null;

function termConnect(cmd) {
  if (termSrc) { termSrc.close(); termSrc = null; }
  const out = document.getElementById("term-out");
  const hint = document.getElementById("term-hint");
  const rst = document.getElementById("term-restart");
  if (!out) return;
  out.innerHTML = "";
  termUI.out = out; termUI.cur = null; termUI.buf = []; termUI.color = "#d6e2f0"; termUI.bold = false; termUI.carry = "";
  const l = document.createElement("div");
  l.className = "term-line";
  out.appendChild(l);
  termUI.cur = l;
  if (hint) hint.textContent = "starting…";
  api("/api/term/start", "POST", cmd ? { cmd: cmd } : {}).then(r => {
    if (hint) hint.textContent = r && r.running ? "running session" : "started";
  }).catch(() => { if (hint) hint.textContent = "backend unreachable"; });
  const es = new EventSource("/sse/term");
  termSrc = es;
  es.onmessage = (e) => {
    let text = e.data;
    try { text = JSON.parse(text); } catch (err) {}
    if (typeof text !== "string") text = String(text);
    if (text.indexOf("[SESSION EXITED") !== -1) {
      if (hint) hint.textContent = "session exited";
      if (rst) rst.style.display = "inline-block";
    } else if (rst) {
      rst.style.display = "none";
    }
    const followOutput = out.scrollHeight - out.scrollTop - out.clientHeight < 32;
    tFeed(text);
    if (followOutput) out.scrollTop = out.scrollHeight;
  };
  es.onerror = () => {};
}

function showTerminal(title, cmd) {
  state.terminal = true; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "term-page");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "≫ " + (title || "Terminal")));
  const hint = el("div", "hint", "…");
  hint.id = "term-hint";
  head.appendChild(hint);
  page.appendChild(head);

  const out = el("div", "term-out");
  out.id = "term-out";
  page.appendChild(out);

  const keys = el("div", "term-keys");
  [["ESC", "\x1b"], ["^C", "\x03"], ["^D", "\x04"], ["TAB", "\t"], ["↑", "\x1b[A"], ["↓", "\x1b[B"], ["←", "\x1b[D"], ["→", "\x1b[C"]].forEach(([lab, code]) => {
    const b = el("button", "tk", lab);
    onKeyHold(b, () => api("/api/term/input", "POST", { data: code }).catch(() => {}));
    keys.appendChild(b);
  });
  const rst = el("button", "tk rst", "↻ restart");
  rst.id = "term-restart";
  rst.onclick = () => termConnect(cmd || (termInit && termInit.cmd));
  keys.appendChild(rst);
  page.appendChild(keys);

  const irow = el("div", "term-input-row");
  const inp = el("input");
  inp.id = "term-in";
  inp.setAttribute("autocomplete", "off");
  inp.setAttribute("spellcheck", "false");
  inp.placeholder = "type a command…";
  const go = el("button", "big-btn run term-go", "↵");
  irow.append(inp, go);
  page.appendChild(irow);
  c.appendChild(page);

  const send = () => {
    const v = inp.value;
    inp.value = "";
    api("/api/term/input", "POST", { data: v + "\r" }).catch(() => {});
  };
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); send(); }
  });
  go.onclick = send;
  state.termSend = send;
  setTimeout(() => inp.focus(), 150);
  termConnect(cmd || (termInit && termInit.cmd));
}

function onKeyHold(btn, repeat, delay = 350, interval = 60) {
  let timer = null;
  btn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    btn.classList.add("hold");
    repeat();
    timer = setTimeout(function tick() {
      repeat();
      timer = setTimeout(tick, interval);
    }, delay);
  });
  const stop = () => {
    btn.classList.remove("hold");
    if (timer) { clearTimeout(timer); timer = null; }
  };
  btn.addEventListener("pointerup", stop);
  btn.addEventListener("pointercancel", stop);
  btn.addEventListener("pointerleave", stop);
}

document.getElementById("btn-settings").onclick = () => { showSettings(); };
document.getElementById("btn-term").onclick = () => { termInit = null; showTerminal(); };

document.querySelector(".btn-back").onclick = () => {
  if (state.evtSource) { state.evtSource.close(); state.evtSource = null; }
  if (termSrc) { termSrc.close(); termSrc = null; }
  state.running = false;
  leaveRecon();
  leaveHunter();
  leaveRadar();
  leaveWardrive();
  leaveRogue();
  leaveProbe();
  leaveDeauth();
  leaveFlood();
  leavePortal();
  leaveClone();
  leavePentest();
  if (state.terminal || state.settings) showHome();
  else if (state.tool) showSection(state.section, sectionTitle(state.section));
  else showHome();
};

function sectionTitle(id) {
  const s = state.data.sections.find(x => x[0] === id);
  return s ? s[1] : id;
}

/* ================= on-screen keyboard ================= */

const KB_ALPHA = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
  ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
  ["z", "x", "c", "v", "b", "n", "m"],
];
const KB_SYM = [
  ["`", "~", "!", "@", "#", "$", "%", "^", "&", "*"],
  ["(", ")", "_", "+", "-", "=", "[", "]", "{", "}"],
  ["|", ";", ":", "'", '"', ",", ".", "/", "?"],
];
const KB_SYM2 = [
  ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
  ["_", "+", "-", "=", "{", "}", "[", "]", "|", "\\"],
  [":", ";", "'", '"', "<", ">", "?", "/", "~", "`"],
];

const KB = { shown: false, shift: false, sym: false };

function kbInsert(text) {
  const inp = document.activeElement;
  if (!inp || !/^(INPUT|TEXTAREA)$/.test(inp.tagName)) return;
  const s = (inp.selectionStart != null) ? inp.selectionStart : inp.value.length;
  const e = (inp.selectionEnd != null) ? inp.selectionEnd : s;
  inp.value = inp.value.slice(0, s) + text + inp.value.slice(e);
  const pos = s + text.length;
  try { inp.setSelectionRange(pos, pos); } catch (err) {}
  inp.focus();
  inp.dispatchEvent(new Event("input", { bubbles: true }));
}

function kbBackspace() {
  const inp = document.activeElement;
  if (!inp || !/^(INPUT|TEXTAREA)$/.test(inp.tagName)) return;
  const s = (inp.selectionStart != null) ? inp.selectionStart : inp.value.length;
  const e = (inp.selectionEnd != null) ? inp.selectionEnd : s;
  if (s === e && s > 0) {
    inp.value = inp.value.slice(0, s - 1) + inp.value.slice(e);
    try { inp.setSelectionRange(s - 1, s - 1); } catch (err) {}
  } else if (s !== e) {
    inp.value = inp.value.slice(0, s) + inp.value.slice(e);
    try { inp.setSelectionRange(s, s); } catch (err) {}
  }
  inp.focus();
  inp.dispatchEvent(new Event("input", { bubbles: true }));
}

function kbRender() {
  const kb = document.getElementById("kb");
  if (!kb) return;
  kb.classList.toggle("open", KB.shown);
  document.body.classList.toggle("kbd-open", KB.shown);
  if (!KB.shown) return;
  const grid = kb.querySelector(".kb-grid");
  grid.innerHTML = "";
  const rows = KB.sym ? (KB.shift ? KB_SYM2 : KB_SYM) : KB_ALPHA;
  rows.forEach(chars => {
    const row = el("div", "kb-row");
    chars.forEach(ch => {
      const k = el("button", "kb-key", ch);
      k.dataset.k = "ch";
      k.dataset.v = ch;
      row.appendChild(k);
    });
    grid.appendChild(row);
  });
  if (KB.sym) {
    const row = el("div", "kb-row");
    const fn = el("button", "kb-key fn", "shift");
    fn.dataset.k = "shift";
    const abc = el("button", "kb-key fn", "ABC");
    abc.dataset.k = "sym";
    const sp = el("button", "kb-key sp", "space");
    sp.dataset.k = "sp";
    const bs = el("button", "kb-key fn", "⌫");
    bs.dataset.k = "bs";
    const ent = el("button", "kb-key fn", "↵");
    ent.dataset.k = "ent";
    const close = el("button", "kb-key fn", "✕");
    close.dataset.k = "close";
    row.append(fn, abc, sp, bs, ent, close);
    grid.appendChild(row);
  } else {
    const row = el("div", "kb-row");
    const fn = el("button", "kb-key fn", "shift");
    fn.dataset.k = "shift";
    const symbtn = el("button", "kb-key fn", "?123");
    symbtn.dataset.k = "sym";
    const sp = el("button", "kb-key sp", "space");
    sp.dataset.k = "sp";
    const bs = el("button", "kb-key fn", "⌫");
    bs.dataset.k = "bs";
    const ent = el("button", "kb-key fn", "↵");
    ent.dataset.k = "ent";
    const close = el("button", "kb-key fn", "✕");
    close.dataset.k = "close";
    row.append(fn, symbtn, sp, bs, ent, close);
    grid.appendChild(row);
  }
  const acc = kb.querySelector(".kb-acc");
  acc.textContent = KB.sym ? (KB.shift ? "symbols ⇧" : "symbols") : (KB.shift ? "SHIFT" : "");
}

function kbOnClick(e) {
  const key = e.target.closest(".kb-key");
  if (!key) return;
  e.preventDefault();
  const k = key.dataset.k;
  if (k === "ch") {
    let ch = key.dataset.v;
    if (!KB.sym && /[a-zA-Z]/.test(ch) && KB.shift) ch = ch.toUpperCase();
    if (KB.shift && !KB.sym) KB.shift = false;
    kbInsert(ch);
  } else if (k === "shift") {
    KB.shift = !KB.shift;
  } else if (k === "bs") {
    kbBackspace();
  } else if (k === "sp") {
    kbInsert(" ");
  } else if (k === "ent") {
    const a = document.activeElement;
    if (a && a.id === "term-in" && typeof state.termSend === "function") {
      state.termSend();
      return;
    }
    a && a.blur();
    KB.hide();
    return;
  } else if (k === "sym") {
    KB.sym = !KB.sym;
    KB.shift = false;
  } else if (k === "close") {
    document.activeElement && document.activeElement.blur();
    KB.hide();
    return;
  }
  if (KB.shown) kbRender();
}

KB.show = function () {
  KB.shown = true;
  kbRender();
};

KB.hide = function () {
  KB.shown = false;
  kbRender();
};

(function kbInit() {
  const kb = el("div", "kbd");
  kb.id = "kb";
  kb.appendChild(el("div", "kb-acc"));
  kb.appendChild(el("div", "kb-grid"));
  kb.addEventListener("pointerdown", (e) => e.preventDefault());
  kb.addEventListener("click", kbOnClick);
  document.body.appendChild(kb);

  document.addEventListener("focusin", (e) => {
    if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) KB.show();
  });
  document.addEventListener("focusout", (e) => {
    if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) {
      setTimeout(() => {
        const a = document.activeElement;
        if (!a || !/^(INPUT|TEXTAREA)$/.test(a.tagName)) KB.hide();
      }, 120);
    }
  });
})();

load();

/* ================= Recon — PineAP style ================= */

let reconPageOpen = false;
let reconTimer = null;
let reconFilter = { band: "all", sec: "all" };
let reconTab = "aps";
let reconOpen = null;
let reconClient = null;
let reconError = "";
let reconGraphView = "channels";
let reconGraphBand = "2.4";
let reconDirty = false;
let reconSeries = {};
let reconTrend = {};
let reconWaterfall = [];
let reconSeen = new Set();
let reconArrivals = [];
let reconArrivalBaseline = false;
let reconWasRunning = false;
let reconWaterfallBand = "both";
let reconAnimation = null;
const RECON_COLORS = ["#39ff14", "#00d9ff", "#ffb000", "#ff3bd3", "#ffe000", "#4cf0c0"];

const reconColors = new Map();
function reconColor(bssid) {
  if (!reconColors.has(bssid)) reconColors.set(bssid, RECON_COLORS[reconColors.size % RECON_COLORS.length]);
  return reconColors.get(bssid);
}

function reconSignal(ap) {
  const value = Number(ap.power);
  return Number.isFinite(value) && value <= -1 && value >= -110 ? value : null;
}

function reconChartNetworks() {
  const aps = reconLast.d.aps.filter(reconMatch).filter(ap => reconSignal(ap) !== null);
  if (reconOpen) return aps.filter(ap => ap.bssid === reconOpen);
  return aps.sort((a, b) => reconSignal(b) - reconSignal(a)).slice(0, 3);
}

function reconObserve(now = Date.now()) {
  if (!reconLast.st.running) { reconWasRunning = false; return; }
  if (!reconWasRunning) {
    reconSeen.clear(); reconArrivals = []; reconWaterfall = []; reconArrivalBaseline = false;
  }
  reconWasRunning = true;
  const devices = [
    ...reconLast.d.aps.map(ap => ({key: "ap:" + ap.bssid.toUpperCase(), kind: "Access point", name: ap.essid || ap.bssid, ap})),
    ...reconLast.d.clients.map(client => ({key: "client:" + client.station.toUpperCase(), kind: "Client", name: client.station, client}))
  ];
  for (const device of devices) {
    if (reconSeen.size >= 10000 && !reconSeen.has(device.key)) continue;
    if (!reconSeen.has(device.key) && reconArrivalBaseline) reconArrivals.unshift({...device, time: now});
    reconSeen.add(device.key);
  }
  reconArrivalBaseline = true;
  reconArrivals = reconArrivals.slice(0,30);
  const aps = reconLast.d.aps.filter(ap => {
    const seen = Date.parse((ap.last || "").replace(" ", "T"));
    return Number.isFinite(seen) && now - seen <= 15000 && now - seen >= -5000 && reconSignal(ap) !== null;
  }).map(ap => ({channel: Number(ap.channel), power: reconSignal(ap), band: scanBand(ap)}));
  const cells = {};
  for (const ap of aps) { const key=ap.band+":"+ap.channel; cells[key]=Math.max(cells[key] ?? -110,ap.power); }
  reconWaterfall.unshift({time: now, aps, cells});
  reconWaterfall = reconWaterfall.filter(row => now - row.time <= 180000).slice(0,180);
  renderReconArrivals();
}

function renderReconArrivals() {
  const feed = document.getElementById("re-arrival-feed"); if (!feed) return;
  feed.classList.toggle("arrival-pulse", !!reconArrivals[0] && Date.now() - reconArrivals[0].time < 4000);
  const signature=reconArrivals.slice(0,8).map(e=>e.key+":"+e.time).join("|");
  if(feed.dataset.signature===signature)return;
  feed.dataset.signature=signature;
  feed.replaceChildren();
  for (const event of reconArrivals.slice(0,8)) {
    const b = el("button", "re-arrival");
    b.append(el("strong", "", event.kind + " · " + event.name), el("span", "", new Date(event.time).toLocaleTimeString()));
    b.onclick = () => {
      if (event.ap) reconSelect(event.ap);
      else { reconClient = event.client.station; reconOpen = null; reconTab = "clients"; reconDo(reconLast.st,reconLast.d,reconLast.lg); }
    };
    feed.append(b);
  }
  if (!reconArrivals.length) feed.append(el("span", "ra-sub", "Watching for new devices after the initial scan baseline."));
  feed.classList.toggle("arrival-pulse", !!reconArrivals[0] && Date.now() - reconArrivals[0].time < 4000);
}

const WATERFALL_CHANNELS = {
  "2.4": Array.from({length:14},(_,i)=>i+1),
  "5": [36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165,169,173,177]
};
const WATERFALL_PALETTE = [[9,13,36],[39,24,104],[36,76,190],[0,190,220],[74,235,164],[255,217,82],[255,112,53]];
function waterfallColor(power, alpha=1) {
  const position=Math.max(0,Math.min(1,(power+100)/70))*(WATERFALL_PALETTE.length-1);
  const i=Math.min(WATERFALL_PALETTE.length-2,Math.floor(position)),mix=position-i;
  const rgb=WATERFALL_PALETTE[i].map((v,k)=>Math.round(v+(WATERFALL_PALETTE[i+1][k]-v)*mix));
  return `rgba(${rgb.join(",")},${alpha})`;
}

function renderReconWaterfall() {
  const cv=document.getElementById("re-graph");if(!cv)return;
  const w=cv.clientWidth||450,h=cv.clientHeight||320,dpr=Math.min(devicePixelRatio||1,2);
  if(cv.width!==Math.round(w*dpr))cv.width=Math.round(w*dpr);
  if(cv.height!==Math.round(h*dpr))cv.height=Math.round(h*dpr);
  const ctx=cv.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle="#050913";ctx.fillRect(0,0,w,h);
  const bands=reconWaterfallBand==="both" ? ["2.4","5"] : [reconWaterfallBand];
  const now=reconLast.st.running ? Date.now() : (reconWaterfall[0]?.time||Date.now());
  const footer=30,panelHeight=(h-footer)/bands.length;
  bands.forEach((band,index)=>{
    const L=35,R=12,top=index*panelHeight,T=top+42,pw=w-L-R,ph=panelHeight-64;
    const channels=WATERFALL_CHANNELS[band],cw=pw/channels.length;
    ctx.fillStyle="#a6bad5";ctx.font="bold 12px sans-serif";ctx.textAlign="left";
    ctx.fillText(band+" GHz",L,top+17);
    ctx.font="10px sans-serif";ctx.fillStyle=reconLast.st.running ? "#57edc1" : "#8393ad";
    ctx.textAlign="right";ctx.fillText(reconLast.st.running ? "● LIVE" : "○ PAUSED",w-R,top+17);
    const background=ctx.createLinearGradient(0,T,0,T+ph);
    background.addColorStop(0,"#101b38");background.addColorStop(1,"#080e20");
    ctx.fillStyle=background;ctx.fillRect(L,T,pw,ph);
    ctx.save();ctx.beginPath();ctx.rect(L,T,pw,ph);ctx.clip();
    let observed=false;
    for(let r=0;r<reconWaterfall.length;r++) {
      const row=reconWaterfall[r],age=now-row.time;if(age>60000 || age<0)continue;
      // Paint only the measured sampling interval; outages remain empty.
      const older=reconWaterfall[r+1];
      const duration=Math.min(1500,Math.max(250,older ? row.time-older.time : 1000));
      const y=T+age/60000*ph,rh=Math.max(1,duration/60000*ph);
      channels.forEach((ch,i)=>{
        const power=row.cells[band+":"+ch];if(power===undefined)return;
        observed=true;
        ctx.fillStyle=waterfallColor(power);ctx.fillRect(L+i*cw,y,cw,rh);
        // A faint cell boundary keeps channel bins readable without invented RF spread.
        ctx.fillStyle="#05091333";ctx.fillRect(L+i*cw,y,Math.min(1,cw/8),rh);
      });
    }
    ctx.strokeStyle="#b1ccff12";ctx.lineWidth=1;
    for(const age of [0,15,30,45,60]) {const y=T+age/60*ph;ctx.beginPath();ctx.moveTo(L,y);ctx.lineTo(w-R,y);ctx.stroke();}
    ctx.restore();
    const latest=reconWaterfall[0];
    channels.forEach((ch,i)=>{
      const power=latest && now-latest.time<2000 ? latest.cells[band+":"+ch] : undefined;
      ctx.fillStyle="#111b30";ctx.fillRect(L+i*cw,top+27,cw-1,9);
      if(power!==undefined) {ctx.fillStyle=waterfallColor(power);ctx.fillRect(L+i*cw,top+27,cw-1,9);}
    });
    const beam=ctx.createLinearGradient(L,T,w-R,T);beam.addColorStop(0,"#36d8f022");beam.addColorStop(.5,"#74eaffaa");beam.addColorStop(1,"#36d8f022");
    ctx.fillStyle=beam;ctx.fillRect(L,T,pw,1);
    ctx.font="9px sans-serif";ctx.textAlign="right";ctx.fillStyle="#7186a4";
    for(const [age,label] of [[0,"NOW"],[30,"−30"],[60,"−60s"]])ctx.fillText(label,L-5,T+Math.min(ph-2,age/60*ph+5));
    ctx.textAlign="center";ctx.fillStyle="#9eb3cf";
    channels.forEach((ch,i)=>{if(channels.length<=14 ? i%2===0 || i===13 : i%4===0 || i===27)ctx.fillText(String(ch),L+(i+.5)*cw,T+ph+14);});
    if(!observed) {ctx.fillStyle="#8393ad";ctx.font="11px sans-serif";ctx.fillText("Waiting for "+band+" GHz observations",L+pw/2,T+ph/2);}
  });
  const x=35,y=h-16,sw=w-47;
  const scale=ctx.createLinearGradient(x,0,x+sw,0);
  WATERFALL_PALETTE.forEach((rgb,i)=>scale.addColorStop(i/(WATERFALL_PALETTE.length-1),`rgb(${rgb.join(",")})`));
  ctx.fillStyle=scale;ctx.fillRect(x,y,sw,4);
  ctx.font="9px sans-serif";ctx.fillStyle="#8ca3bf";ctx.textAlign="left";ctx.fillText("−100 dBm",x,y+13);
  ctx.textAlign="center";ctx.fillText("SIGNAL STRENGTH",x+sw/2,y+13);
  ctx.textAlign="right";ctx.fillText("−30 dBm",x+sw,y+13);
  cv.setAttribute("aria-label","WiFi signal waterfall, "+(reconWaterfallBand==="both" ? "2.4 and 5" : reconWaterfallBand)+" GHz, last 60 seconds, newest observations at top; brighter means stronger signal.");
}

function reconSample() {
  const now = Date.now();
  reconObserve(now);
  const cur = new Map(reconLast.d.aps.map(ap => [ap.bssid, reconSignal(ap)]));
  for (const key of cur.keys()) if (!reconSeries[key]) reconSeries[key] = [];
  for (const key of Object.keys(reconSeries)) {
    const series = reconSeries[key];
    series.push({time: now, value: cur.get(key) ?? null});
    while (series.length && series[0].time < now - 60000) series.shift();
    if (!series.some(p => p.value !== null)) { delete reconSeries[key]; continue; }
    const last = series.at(-1)?.value, previous = series.at(-2)?.value;
    reconTrend[key] = last === null || previous == null ? "flat" : last - previous > 1.5 ? "up" : last - previous < -1.5 ? "down" : "flat";
  }
  renderReconGraph(); renderReconLegend(); renderReconChstrip();
}

function renderReconGraph() {
  document.querySelectorAll('[data-graph-view]').forEach(b => b.classList.toggle('on', b.dataset.graphView === reconGraphView));
  document.querySelectorAll("[data-graph-band]").forEach(b => { b.hidden = b.dataset.graphBand === "both" && reconGraphView !== "waterfall"; b.classList.toggle("on", reconGraphView !== "history" && b.dataset.graphBand === (reconGraphView === "waterfall" ? reconWaterfallBand : reconGraphBand)); });
  const graph=document.getElementById("re-graph");if(graph)graph.style.height=reconGraphView==="waterfall" ? (innerHeight>600 ? "360px" : "300px") : "190px";
  if (reconGraphView === "waterfall") { renderReconWaterfall(); return; }
  if (reconGraphView === "history") { renderReconHistory(); return; }
  const cv = document.getElementById("re-graph"); if (!cv) return;
  const w = cv.clientWidth || 450, h = cv.clientHeight || 190, dpr = Math.min(window.devicePixelRatio || 1,2);
  cv.width = Math.round(w*dpr); cv.height = Math.round(h*dpr);
  const ctx = cv.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle = '#071512'; ctx.fillRect(0,0,w,h);
  const L=48,R=16,T=30,B=30,pw=w-L-R,ph=h-T-B;
  const min = reconGraphBand === '2.4' ? 1 : 32, max = reconGraphBand === '2.4' ? 14 : 177;
  const X = ch => L+pw*(ch-min)/(max-min), Y = v => T+ph*(-20-Math.max(-100,Math.min(-20,v)))/80;
  ctx.font='11px sans-serif'; ctx.textBaseline='middle';
  for(const v of [-20,-40,-60,-80,-100]) {
    ctx.strokeStyle='#234239';ctx.beginPath();ctx.moveTo(L,Y(v));ctx.lineTo(w-R,Y(v));ctx.stroke();
    ctx.fillStyle='#9cb9ad';ctx.textAlign='right';ctx.fillText(String(v),L-8,Y(v));
  }
  ctx.textAlign='left';ctx.fillStyle='#b8d6ca';ctx.fillText('Signal · dBm',L,13);
  ctx.textAlign='right';ctx.fillText((reconLast.st.running?'LIVE':'STOPPED')+' · '+reconGraphBand+' GHz channels',w-R,13);
  const channels = reconGraphBand === '2.4' ? [1,3,6,9,11,14] : [36,64,100,132,149,165];
  ctx.textAlign='center'; for(const ch of channels) ctx.fillText(String(ch),X(ch),h-12);
  const aps = reconLast.d.aps.filter(reconMatch).filter(ap=>scanBand(ap)===reconGraphBand && reconSignal(ap)!==null);
  cv._reconHits=[];
  ctx.save();ctx.beginPath();ctx.rect(L,T,pw,ph);ctx.clip();
  for(const ap of aps.slice().sort((a,b)=>reconSignal(a)-reconSignal(b))) {
    const x=X(Number(ap.channel)),y=Y(reconSignal(ap)),color=reconColor(ap.bssid);
    ctx.globalAlpha=reconOpen && reconOpen !== ap.bssid ? 0.25 : 1;
    ctx.strokeStyle=color;ctx.lineWidth=reconOpen===ap.bssid?3:1.5;
    ctx.beginPath();ctx.moveTo(x,T+ph);ctx.lineTo(x,y);ctx.stroke();
    ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,reconOpen===ap.bssid?6:4,0,Math.PI*2);ctx.fill();
    cv._reconHits.push({x,y,ap});
  }
  ctx.restore();ctx.globalAlpha=1;
  if(!aps.length) {ctx.fillStyle='#b8d6ca';ctx.textAlign='center';ctx.fillText('No '+reconGraphBand+' GHz observations yet',w/2,T+ph/2);}
  cv.setAttribute('aria-label',aps.length?aps.map(ap=>(ap.essid||ap.bssid)+': channel '+ap.channel+', '+ap.power+' dBm').join('; '):'No network observations');
}

function renderReconHistory() {
  const cv = document.getElementById("re-graph");
  if (!cv) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2), w = cv.clientWidth || 450, h = cv.clientHeight || 190;
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#071512"; ctx.fillRect(0, 0, w, h);
  const L = 48, R = 16, T = 30, B = 30, pw = w - L - R, ph = h - T - B;
  const now = Date.now(), X = t => L + pw * (t - now + 60000) / 60000;
  const Y = v => T + ph * (-20 - Math.max(-100, Math.min(-20, v))) / 80;
  ctx.font = "11px sans-serif"; ctx.textBaseline = "middle";
  for (const v of [-20, -40, -60, -80, -100]) {
    ctx.strokeStyle = "#234239"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(L, Y(v)); ctx.lineTo(w-R, Y(v)); ctx.stroke();
    ctx.fillStyle = "#9cb9ad"; ctx.textAlign = "right"; ctx.fillText(String(v), L-8, Y(v));
  }
  ctx.textAlign = "left"; ctx.fillStyle = "#b8d6ca"; ctx.fillText("Signal · dBm", L, 13);
  ctx.textAlign = "right"; ctx.fillText(reconLast.st.running ? "LIVE · last 60 seconds" : "Scan stopped", w-R, 13);
  for (const [age, label] of [[60,"60s ago"],[30,"30s ago"],[0,"Now"]]) {
    ctx.textAlign = age === 60 ? "left" : age === 0 ? "right" : "center";
    ctx.fillText(label, L + pw*(60-age)/60, h-12);
  }
  const networks = reconChartNetworks();
  ctx.save(); ctx.beginPath(); ctx.rect(L,T,pw,ph); ctx.clip();
  for (const ap of networks) {
    const samples = reconSeries[ap.bssid] || [], color = reconColor(ap.bssid);
    ctx.strokeStyle = color; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.beginPath();
    let previous = null;
    for (const sample of samples) {
      if (sample.value === null) { previous = null; continue; }
      if (!previous || sample.time - previous.time > 6000) ctx.moveTo(X(sample.time),Y(sample.value));
      else ctx.lineTo(X(sample.time),Y(sample.value));
      previous = sample;
    }
    ctx.stroke();
    const last = samples.at(-1);
    if (last && last.value !== null) { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(Math.min(w-R-3,X(last.time)),Y(last.value),3,0,Math.PI*2); ctx.fill(); }
  }
  ctx.restore();
  if (!networks.length) {
    ctx.fillStyle = "#b8d6ca"; ctx.textAlign = "center";
    ctx.fillText(reconLast.st.running ? "Waiting for signal observations…" : "Start a scan to see network signals", w/2, T+ph/2);
  }
  cv.setAttribute("aria-label", networks.length ? networks.map(ap => (ap.essid || ap.bssid)+": "+ap.power+" dBm").join("; ") : "No signal observations");
}

function renderReconLegend() {
  const leg = document.getElementById("re-legend"); if (!leg) return;
  leg.replaceChildren();
  if (reconGraphView === "waterfall") { leg.append(el("div", "ra-sub", "Channel × time · newest at top · observed WiFi signal")); return; }
  const reset = el("button", "re-chart-reset", reconOpen ? "Show all networks" : reconGraphView === "history" ? "Strongest 3 · tap a network to isolate" : "Live networks · channel and signal · tap to select");
  reset.onclick = () => reconSelect(null); leg.append(reset);
  const networks = reconGraphView === "history" ? reconChartNetworks() : reconLast.d.aps.filter(reconMatch).filter(ap => scanBand(ap) === reconGraphBand).sort((a,b)=>Number(b.power)-Number(a.power));
  for (const ap of networks) {
    const item = el("button", "re-chart-network"); item.style.borderLeftColor = reconColor(ap.bssid);
    item.append(el("strong", "", ap.essid || "Hidden · " + ap.bssid), el("span", "", ap.power + " dBm · CH " + ap.channel + " · " + reconLast.d.clients.filter(c => (c.bssid || "").toUpperCase() === ap.bssid.toUpperCase()).length + " clients"));
    item.title = ap.bssid; item.onclick = () => reconSelect(ap); leg.append(item);
  }
}

function renderReconChstrip() {
  const strip = document.getElementById("re-chstrip"); if (!strip) return;
  strip.replaceChildren();
  const counts = new Map();
  for (const ap of reconLast.d.aps.filter(reconMatch)) {
    const ch = Number(ap.channel); if (ch > 0) counts.set(ch,(counts.get(ch)||0)+1);
  }
  strip.append(el("span", "ra-sub", "Networks per channel"));
  for (const [ch,count] of [...counts].sort((a,b)=>a[0]-b[0])) strip.append(el("span", "re-channel-count", "CH " + ch + " · " + count));
  if (!counts.size) strip.append(el("span", "ra-sub", "No channel observations"));
}

function leaveRecon() {
  if (reconAnimation) { clearInterval(reconAnimation); reconAnimation = null; }
  if (reconTimer) { clearInterval(reconTimer); reconTimer = null; }
  reconPageOpen = false;
  reconOpen = null;
  reconClient = null;
  reconError = "";
  reconSeries = {};
  reconTrend = {};
}

function scanBand(ap) {
  const ch = parseInt(ap.channel, 10);
  if (Number.isNaN(ch)) return "2.4";
  return ch <= 14 ? "2.4" : "5";
}

function scanSec(ap) {
  const p = ap.privacy || ap.cipher || ap.auth || "";
  if (/OPN/i.test(p)) return "open";
  return "wpa";
}

function reconMatch(ap) {
  if (reconFilter.band !== "all" && scanBand(ap) !== reconFilter.band) return false;
  if (reconFilter.sec !== "all" && scanSec(ap) !== reconFilter.sec) return false;
  return true;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function reconSelect(ap, client = null) {
  reconOpen = ap ? ap.bssid : null;
  reconClient = client ? client.station : null;
  reconDo(reconLast.st, reconLast.d, reconLast.lg);
}

function reconTargetActions(ap, client = null) {
  const box = el("div", "ra-detail recon-target");
  box.append(el("strong", null, client ? client.station : (ap.essid || "Hidden network")),
    el("div", "ra-sub", client ? "Observed AP: " + (ap ? ap.bssid : "not observed") + " · Probes: " + (client.probes || "none") : ap.bssid + " · CH " + ap.channel));
  const actions = el("div", "ra-btnrow");
  const copy = el("button", "mini-btn", "Copy address");
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(client ? client.station : ap.bssid); copy.textContent = "Copied"; }
    catch (_) { copy.textContent = "Copy unavailable"; }
  };
  actions.append(copy);
  if (ap) {
    const prepare = el("button", "mini-btn", "Open target controls");
    prepare.onclick = () => {
      leaveRecon(); showDeauth();
      document.getElementById("deauth-bssid").value = ap.bssid;
      document.getElementById("deauth-ch").value = ap.channel;
      document.getElementById("deauth-client").value = client ? client.station : "";
    };
    actions.append(prepare);
    if (client) {
      const parent = el("button", "mini-btn", "View access point");
      parent.onclick = () => { reconTab = "aps"; reconSelect(ap); };
      actions.append(parent);
    }
  }
  box.append(actions);
  return box;
}

function reconMap(d) {
  const map = el("div", "recon-map");
  map.append(el("div", "ra-sub", "Observed associations · not physical locations · tap a node"));
  const aps = d.aps.filter(reconMatch).slice().sort((a, b) => Number(b.power) - Number(a.power));
  const known = new Set(d.aps.map(a => a.bssid.toUpperCase()));
  const node = (label, key, selected, action) => {
    const b = el("button", "recon-node" + (selected ? " selected" : ""), label);
    b.dataset.node = key; b.onclick = action; b.setAttribute("aria-pressed", String(selected));
    return b;
  };
  for (const ap of aps.slice(0, 40)) {
    const clients = d.clients.filter(c => (c.bssid || "").toUpperCase() === ap.bssid.toUpperCase());
    const branch = el("div", "recon-branch");
    branch.append(node((ap.essid || "Hidden network") + " · CH " + ap.channel + " · " + ap.power + " dBm · " + clients.length + " clients",
      ap.bssid, reconOpen === ap.bssid && !reconClient, () => reconSelect(ap)));
    const leaves = el("div", "recon-leaves");
    for (const client of clients.slice(0, 12)) leaves.append(node(client.station + " · " + client.power + " dBm", client.station,
      reconClient === client.station, () => reconSelect(ap, client)));
    if (!clients.length) leaves.append(el("div", "ra-sub", "No clients observed"));
    if (clients.length > 12) leaves.append(el("div", "ra-sub", "+" + (clients.length - 12) + " more in Clients"));
    branch.append(leaves); map.append(branch);
  }
  if (aps.length > 40) map.append(el("div", "ra-sub", "Showing 40 of " + aps.length + " access points; use filters or the list."));
  const unmatched = d.clients.filter(c => !known.has((c.bssid || "").toUpperCase()));
  if (unmatched.length) {
    map.append(el("div", "ra-sub", "Unassociated / access point not observed"));
    const loose = el("div", "recon-loose");
    for (const c of unmatched.slice(0, 40)) loose.append(node(c.station, c.station, reconClient === c.station, () => reconSelect(null, c)));
    if (unmatched.length > 40) loose.append(el("div", "ra-sub", "+" + (unmatched.length - 40) + " more in Clients"));
    map.append(loose);
  }
  if (!aps.length && !unmatched.length) map.append(el("div", "re-empty", "No observations yet. Start a scan to populate the map."));
  return map;
}

function reconRows(st, d) {
  const t = reconTab;
  const no = el("div", "re-empty", "no data yet");
  if (t === "map") return [reconMap(d)];
  if (t === "aps") {
    const aps = d.aps.filter(reconMatch)
      .sort((a, b) => (parseInt(b.power, 10) || -100) - (parseInt(a.power, 10) || -100));
    if (!aps.length) return [no];
    const out = [];
    for (const ap of aps) {
      const nclients = d.clients.filter(c => c.bssid && c.bssid.toUpperCase() === ap.bssid.toUpperCase()).length;
      const row = el("div", "ra-row" + (reconOpen === ap.bssid ? " open" : ""));
      const t1 = el("div", "ra-main");
      const s = el("span", "ra-sig");
      s.textContent = (ap.power || "??") + " dBm";
      const tr = reconTrend[ap.bssid] || "flat";
      const arr = el("span", "ra-tr", tr === "up" ? "▲" : tr === "down" ? "▼" : "—");
      arr.style.color = tr === "up" ? "#39ff14" : tr === "down" ? "#ff4d4d" : "#3f6b5a";
      const essid = el("span", "ra-essid", ap.essid ? ap.essid : "████ (hidden)");
      const ch = el("span", "ra-ch", "CH " + ap.channel);
      const sec = el("span", "ra-sec", ap.privacy || "?");
      const cl = el("span", "ra-cl", "◈ " + nclients);
      s.style.background = signalColor(ap.power);
      t1.append(s, arr, essid, ch, sec, cl);
      const t2 = el("div", "ra-sub", ap.bssid + "  ·  " + (ap.speed || "-") + " Mb/s  ·  beacons " + (ap.beacons || "0"));
      row.append(t1, t2);
      row.onclick = () => reconSelect(reconOpen === ap.bssid ? null : ap);
      out.push(row);
      if (reconOpen === ap.bssid) out.push(reconDetail(ap, d));
    }
    return out;
  }
  const cs = d.clients.slice().sort((a, b) => (parseInt(b.power, 10) || -100) - (parseInt(a.power, 10) || -100));
  if (!cs.length) return [no];
  return cs.map(c => {
    const row = el("div", "ra-row");
    const t1 = el("div", "ra-main");
    const s = el("span", "ra-sig", (c.power || "??") + " dBm");
    s.style.background = signalColor(c.power);
    const mac = el("span", "ra-essid", c.station);
    const pk = el("span", "ra-ch", "pkts " + c.packets);
    t1.append(s, mac, pk);
    const t2 = el("div", "ra-sub", "AP " + (c.bssid || "-") + "  ·  " + (c.probes ? "probes: " + c.probes : ""));
    row.append(t1, t2);
    row.onclick = () => reconSelect(d.aps.find(a => a.bssid.toUpperCase() === (c.bssid || "").toUpperCase()), c);
    return row;
  });
}

function reconDetail(ap, d) {
  const det = el("div", "ra-detail");
  const where = el("div", "ra-sub", "encryption: " + (ap.cipher || "-") + " / " + (ap.auth || "-") +
    "  ·  channel " + ap.channel + "  ·  lan " + (ap.lanip || "-") + "  ·  iv " + (ap.iv || "0"));
  det.appendChild(where);
  const cli = d.clients.filter(c => c.bssid && c.bssid.toUpperCase() === ap.bssid.toUpperCase());
  const lab = el("div", "ra-sub", "clients attached (" + cli.length + ")");
  det.appendChild(lab);
  for (const c of cli.slice(0, 6)) {
    const r = el("div", "ra-main");
    const mk = el("span", "ra-sig", (c.power || "??") + " dBm");
    mk.style.background = signalColor(c.power);
    r.append(mk, el("span", "ra-essid", c.station));
    const kick = el("button", "mini-btn", "DEAUTH");
    kick.onclick = (ev) => { ev.stopPropagation(); reconDeauth(ap.bssid, c.station); };
    r.appendChild(kick);
    det.appendChild(r);
  }
  const bb = el("div", "ra-btnrow");
  const da = el("button", "mini-btn warn", "▄ DEAUTH AP");
  da.onclick = (ev) => { ev.stopPropagation(); reconDeauth(ap.bssid); };
  bb.appendChild(da);
  det.appendChild(bb);
  return det;
}

async function reconDeauth(bssid, client) {
  try {
    await fetch("/api/recon/deauth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(client ? { bssid, client } : { bssid }),
    });
  } catch (e) {}
}

function signalColor(p) {
  const v = parseInt(p, 10);
  if (Number.isNaN(v)) return "#1f2937";
  if (v >= -60) return "#065f46";
  if (v >= -75) return "#78350f";
  return "#7f1d1d";
}

function reconDo(st, d, lg, drawChart = true) {
  const hint = document.getElementById("recon-hint");
  const stats = document.getElementById("re-stats");
  const table = document.getElementById("re-table");
  const log = document.getElementById("re-log");
  if (!stats || !table) return;
  const ifc = st.iface ? st.iface : "—";
  stats.innerHTML = "";
  const pkts = d.aps.reduce((s, a) => s + (parseInt(a.beacons, 10) || 0) + (parseInt(a.iv, 10) || 0), 0);
  let best = -200, bestN = null;
  for (const a of d.aps) {
    const p = parseInt(a.power, 10) || -200;
    if (p > best) { best = p; bestN = a.essid || a.bssid; }
  }
  const chSet = {};
  d.aps.forEach(a => { const c = a.channel; if (c) chSet[c] = 1; });
  stats.append(
    mkStatCell("IFACE", st.running ? "▣ " + ifc : "○ none"),
    mkStatCell("APs", d.aps.length),
    mkStatCell("CLIENTS", d.clients.length),
    mkStatCell("PKTS", pkts.toLocaleString()),
    mkStatCell("TOP", best > -200 ? (parseInt(best, 10) + " dBm") : "—"),
    mkStatCell("CH", Object.keys(chSet).length + " bands"),
  );
  const eye = st.running ? "scanning " + ifc + " · hop abg" : "press ▶ SCAN ON";
  hint.textContent = eye;
  const scanError = document.getElementById("recon-error");
  if (scanError) { scanError.textContent = reconError; scanError.hidden = !reconError; }
  document.querySelectorAll(".re-tabs [data-recon-tab]").forEach(b => b.classList.toggle("on", b.dataset.reconTab === reconTab));
  const focused = document.activeElement?.dataset.node;
  const rows = reconRows(st, d);
  table.innerHTML = "";
  for (const r of rows) table.appendChild(r);
  const target = document.getElementById("re-target");
  if (target) {
    target.replaceChildren();
    const client = d.clients.find(c => c.station === reconClient);
    const ap = d.aps.find(a => a.bssid.toUpperCase() === (client ? client.bssid || "" : reconOpen || "").toUpperCase());
    if (client || ap) target.append(reconTargetActions(ap, client));
    else if (reconOpen || reconClient) target.append(el("div", "ra-sub", "Selected device is no longer in the scan."));
  }
  if (focused) [...table.querySelectorAll("[data-node]")].find(b => b.dataset.node === focused)?.focus({preventScroll: true});
  if (drawChart) { renderReconGraph(); renderReconLegend(); renderReconChstrip(); }
  if (log) { log.textContent = lg.log.trim().split("\n").slice(-24).join("\n"); log.scrollTop = 1e9; }
  if (reconDirty) { reconDirty = false; }
}

function showRecon() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null;
  state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  reconPageOpen = true;
  reconOpen = null;
  reconClient = null;
  reconError = "";
  reconSeries = {};
  reconTrend = {};
  reconWaterfall = []; reconSeen.clear(); reconArrivals = []; reconArrivalBaseline = false; reconWasRunning = false;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  const title = el("h2", null, "◉ RECON");
  head.appendChild(title);
  const pine = el("div", "re-pine", "PineAP · real-time platform");
  head.appendChild(pine);
  const hint = el("div", "hint", "");
  hint.id = "recon-hint";
  head.appendChild(hint);
  page.appendChild(head);

  const gwrap = el("div", "re-top");
  const legend = el("div", "re-legend");
  legend.id = "re-legend";
  const graphControls = el("div", "re-tabs");
  for (const [view,label] of [["channels","Live channels"],["waterfall","Waterfall"],["history","Signal history"]]) {
    const b=el("button","chip",label);b.dataset.graphView=view;
    b.onclick=()=>{reconGraphView=view;renderReconGraph();renderReconLegend();};graphControls.append(b);
  }
  for(const band of ["both","2.4","5"]) {
    const b=el("button","chip",band==="both" ? "Both bands" : band+" GHz"); b.dataset.graphBand=band;
    b.onclick=()=>{if(reconGraphView==="waterfall")reconWaterfallBand=band;else {reconGraphBand=band;reconGraphView="channels";}renderReconGraph();renderReconLegend();};graphControls.append(b);
  }
  gwrap.append(graphControls);
  const gcanvas = document.createElement("canvas");
  gcanvas.className = "re-graph";
  gcanvas.id = "re-graph";
  gcanvas.onclick = ev => {
    if(reconGraphView!=="channels")return;
    const box=gcanvas.getBoundingClientRect(),x=ev.clientX-box.left,y=ev.clientY-box.top;
    const hit=(gcanvas._reconHits||[]).slice().sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0];
    if(hit && Math.hypot(hit.x-x,hit.y-y)<24)reconSelect(hit.ap);
  };
  gwrap.append(gcanvas, legend);
  page.appendChild(gwrap);
  const chcanvas = document.createElement("div");
  chcanvas.className = "re-chstrip";
  chcanvas.id = "re-chstrip";
  page.appendChild(chcanvas);

  const stats = el("div", "re-stats");
  stats.id = "re-stats";
  page.appendChild(stats);
  const arrivals = el("details", "re-arrivals"); arrivals.open = true;
  arrivals.append(el("summary", "", "Device arrivals"), el("div", "ra-sub", "Newly observed in this scan · first observations form the baseline"));
  const feed = el("div", ""); feed.id = "re-arrival-feed"; feed.setAttribute("role", "status"); feed.setAttribute("aria-live", "polite");
  arrivals.append(feed); page.append(arrivals);


  const bar = el("div", "re-bar");
  const on = el("button", "big-btn run", "▶ SCAN ON");
  on.onclick = async () => {
    on.classList.add("busy"); on.textContent = "starting…";
    try {
      const r = await fetch("/api/recon/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const j = await r.json();
      if (j.ok) reconWasRunning = false;
      reconError = j.ok ? "" : (j.msg || "Scan could not start.");
      hint.textContent = j.ok ? "scanning " + j.msg : "✗ " + reconError;
    } catch (e) { reconError = "Could not contact the scanner. Try again."; }
    reconDo(reconLast.st, reconLast.d, reconLast.lg);
    on.classList.remove("busy"); on.textContent = "▶ SCAN ON";
  };
  bar.appendChild(on);
  const off = el("button", "big-btn stop", "■ OFF");
  off.onclick = async () => {
    try { await fetch("/api/recon/stop", { method: "POST" }); } catch (e) {}
  };
  bar.appendChild(off);
  page.appendChild(bar);
  const scanError = el("div", "recon-error");
  scanError.id = "recon-error"; scanError.setAttribute("role", "alert"); scanError.hidden = true;
  page.appendChild(scanError);

  const chips = el("div", "re-chip");
  const mk = (k, v, lab) => {
    const b = el("button", "chip" + (reconFilter[k] === v ? " on" : ""), lab);
    b.onclick = () => { reconFilter[k] = v; reconDo(reconLast.st, reconLast.d, reconLast.lg); };
    chips.appendChild(b);
  };
  mk("band", "all", "ALL"); mk("band", "2.4", "2.4G"); mk("band", "5", "5G");
  mk("sec", "all", "ANY"); mk("sec", "open", "OPEN"); mk("sec", "wpa", "WPA");
  page.appendChild(chips);

  const tabs = el("div", "re-tabs");
  for (const [value, label] of [["aps", "▣ ACCESS POINTS"], ["clients", "◈ CLIENTS"], ["map", "NETWORK MAP"]]) {
    const tab = el("button", "chip" + (reconTab === value ? " on" : ""), label);
    tab.dataset.reconTab = value;
    tab.onclick = () => { reconTab = value; reconDo(reconLast.st, reconLast.d, reconLast.lg); };
    tabs.append(tab);
  }
  page.appendChild(tabs);

  const table = el("div", "re-table");
  table.id = "re-table";
  const logBox = el("div", "re-log");
  logBox.id = "re-log";
  page.appendChild(table);
  const target = el("div", "", ""); target.id = "re-target"; page.appendChild(target);
  page.appendChild(logBox);

  c.appendChild(page);
  reconLast = { st: { running: false, iface: null, aps: 0, clients: 0 }, d: { aps: [], clients: [] }, lg: { log: "" } };
  reconDo(reconLast.st, reconLast.d, reconLast.lg);
  renderReconArrivals();

  let polling = false, lastTableRender = 0;
  const poke = async () => {
    if (!reconPageOpen || polling) return;
    polling = true;
    try {
      const response = await fetch("/api/recon/snapshot", {signal: AbortSignal.timeout(4000)});
      if (!response.ok) throw new Error("Scanner unavailable");
      const {st,d,lg} = await response.json();
      if (!reconPageOpen) return;
      reconLast = { st, d, lg };
      if(Date.now()-lastTableRender>=2000) { reconDo(st, d, lg, false); lastTableRender=Date.now(); }
      reconSample();
    } catch (e) {} finally { polling = false; }
  };
  reconTimer = setInterval(poke, 1000);
  reconAnimation = setInterval(()=>{if(reconPageOpen && reconGraphView==="waterfall" && reconLast.st.running && !document.hidden)renderReconWaterfall();},100);
  poke();
}

let reconLast = { st: { running: false, iface: null, aps: 0, clients: 0 }, d: { aps: [], clients: [] }, lg: { log: "" } };

/* ================= Handshake Hunter ================= */

let hunterTimer = null;
let hunterScanT = null;
let hunterAps = [];

function leaveHunter() {
  if (hunterTimer) { clearInterval(hunterTimer); hunterTimer = null; }
  if (hunterScanT) { clearTimeout(hunterScanT); hunterScanT = null; }
  hunterPageOpen = false;
}
let hunterPageOpen = false;

async function hunterEnvScan() {
  const hint = document.getElementById("hunter-hint");
  if (hint) hint.textContent = "scanning environment…";
  try {
    await fetch("/api/recon/start", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
  } catch (e) {}
  let tries = 0;
  hunterScanT = setInterval(async () => {
    tries++;
    try {
      const d = await fetch("/api/recon/data").then(r => r.json());
      if (d.aps && d.aps.length) {
        hunterAps = d.aps;
        renderHunterAps();
        if (hint) hint.textContent = "environment: " + d.aps.length + " APs · pick a target";
        clearInterval(hunterScanT); hunterScanT = null;
        await fetch("/api/recon/stop", { method: "POST" });
        return;
      }
    } catch (e) {}
    if (tries >= 10) {
      clearInterval(hunterScanT); hunterScanT = null;
      await fetch("/api/recon/stop", { method: "POST" });
      if (hint) hint.textContent = "no APs found — move closer / check adapter";
    }
  }, 2000);
}

function renderHunterAps() {
  const list = document.getElementById("hunter-aps");
  if (!list) return;
  list.innerHTML = "";
  const aps = hunterAps.slice()
    .sort((a, b) => (parseInt(b.power, 10) || -100) - (parseInt(a.power, 10) || -100));
  const no = el("div", "re-empty", "press ▶ SCAN ENV to survey");
  if (!aps.length) { list.appendChild(no); return; }
  for (const ap of aps) {
    const row = el("div", "ra-row");
    const t1 = el("div", "ra-main");
    const s = el("span", "ra-sig", (ap.power || "??") + " dBm");
    s.style.background = signalColor(ap.power);
    const tr = reconTrend[ap.bssid] || "flat";
    const arr = el("span", "ra-tr", tr === "up" ? "▲" : tr === "down" ? "▼" : "—");
    arr.style.color = tr === "up" ? "#39ff14" : tr === "down" ? "#ff4d4d" : "#3f6b5a";
    const essid = el("span", "ra-essid", ap.essid ? ap.essid : "████ (hidden)");
    const ch = el("span", "ra-ch", "CH " + ap.channel);
    const btn = el("button", "mini-btn hunt", "HUNT");
    btn.onclick = () => hsHunt(ap);
    t1.append(s, arr, essid, ch, btn);
    const t2 = el("div", "ra-sub", ap.bssid + "  ·  " + (ap.privacy || "?"));
    row.append(t1, t2);
    list.appendChild(row);
  }
}

async function hsHunt(ap) {
  const hint = document.getElementById("hunter-hint");
  if (hint) hint.textContent = "hunting " + (ap.essid || ap.bssid) + "…";
  const poke = document.getElementById("hunter-autodeauth");
  try {
    const r = await fetch("/api/hs/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bssid: ap.bssid, essid: ap.essid,
        channel: parseInt(ap.channel, 10) || null,
        autodeauth: !poke || poke.checked,
      }),
    });
    const j = await r.json();
    if (hint) hint.textContent = j.ok ? "▶ capturing " + j.msg + (j.ok && (!poke || poke.checked) ? " — jamming until handshake" : " — waiting for handshake") : "✗ " + j.msg;
  } catch (e) {}
}

async function hsDeauth(bssid, client) {
  try {
    await fetch("/api/hs/deauth", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(client ? { bssid, client } : { bssid }),
    });
  } catch (e) {}
}

async function hsCrack(base) {
  const hint = document.getElementById("hunter-hint");
  try {
    const r = await fetch("/api/hs/crack", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base }),
    });
    const j = await r.json();
    if (hint) hint.textContent = j.ok ? "cracking " + base + " …" : "✗ " + j.msg;
  } catch (e) {}
}

function hunterStats(st) {
  const stats = document.getElementById("hunter-stats");
  if (!stats) return;
  stats.innerHTML = "";
  const hsCell = st.handshakes > 0
    ? "✓ " + st.handshakes + " HS"
    : (st.pmkid > 0 ? "PMKID" : st.running ? "wait" : "0");
  stats.append(
    mkStatCell("IFACE", st.iface ? "▣ " + st.iface : "○ none"),
    mkStatCell("TARGET", st.target ? st.target.slice(0, 15) : "—"),
    mkStatCell("CH", st.channel || "any"),
    mkStatCell("CAP", st.captures),
    mkStatCell("HS", hsCell, st.handshakes > 0 ? "ok" : (st.pmkid > 0 ? "ok" : "")),
    mkStatCell("CRACK", st.cracking ? "● RUN" : "idle"),
  );
}

function hunterAlert(st) {
  const al = document.getElementById("hunter-alert");
  if (!al) return;
  if (st.running && st.handshakes > 0) {
    al.textContent = st.cracked && st.cracked !== "null"
      ? "✓ HANDSHAKE CRACKED — " + st.cracked
      : "✓ HANDSHAKE CAPTURED" + (st.handshakes > 1 ? " ×" + st.handshakes : "") + " — cracking…";
    al.className = "hs-alert ok";
  } else if (st.running && st.pmkid > 0) {
    al.textContent = "✓ PMKID CAPTURED — cracking…";
    al.className = "hs-alert ok";
  } else if (st.running && st.poke) {
    al.textContent = "◙ jamming — " + (st.pokes || 0) + " deauth round(s) sent, watching for the handshake…";
    al.className = "hs-alert warn";
  } else if (st.running) {
    al.textContent = "capturing — deauth-auto off, press ⚡ to force a handshake";
    al.className = "hs-alert";
  } else if (al.textContent) {
    al.textContent = "";
    al.className = "hs-alert";
  }
}

function renderHunterCaps(caps) {
  const list = document.getElementById("hunter-caps");
  if (!list) return;
  list.innerHTML = "";
  const no = el("div", "re-empty", "no captures yet");
  if (!caps.length) { list.appendChild(no); return; }
  for (const c of caps.slice().reverse()) {
    const base = c.file.replace(/-01\.cap$/, "");
    const row = el("div", "ra-row");
    const t1 = el("div", "ra-main");
    const essid = el("span", "ra-essid", base);
    const badge = c.handshakes > 0
      ? el("span", "hs-badge ok", c.handshakes + " HS")
      : el("span", "hs-badge", (c.pmkid > 0 ? "PMKID" : "no HS"));
    t1.append(essid, badge);
    const t2 = el("div", "ra-sub", c.file + "  ·  " + Math.round(c.size / 1024) + " KB");
    row.append(t1, t2);
    list.appendChild(row);
    if (c.hash) {
      const row2 = el("div", "ra-row");
      const t = el("div", "ra-main");
      const name = el("span", "ra-essid", "🎯 hash ready (22000)");
      t.append(name);
      const stbtn = el("button", "mini-btn", "STATUS");
      stbtn.onclick = () => hsCrackStatus(base);
      const ck = el("button", "mini-btn hunt", "CRACK");
      ck.onclick = () => hsCrack(base);
      t.append(stbtn, ck);
      row2.appendChild(t);
      const pw = el("div", "ra-sub");
      pw.id = "hs-pw-" + base;
      if (c.cracked === null || c.cracked === "null") pw.textContent = "not cracked yet";
      else { pw.textContent = "PASS: " + c.cracked; pw.style.color = "#39ff14"; }
      row2.appendChild(pw);
      list.appendChild(row2);
    }
  }
}

async function hsCrackStatus(base) {
  const hint = document.getElementById("hunter-hint");
  try {
    const j = await fetch("/api/hs/crack/status?base=" + encodeURIComponent(base)).then(r => r.json());
    const pw = document.getElementById("hs-pw-" + base);
    if (pw) {
      if (j.cracked && j.cracked !== "null") { pw.textContent = "PASS: " + j.cracked; pw.style.color = "#39ff14"; }
      else pw.textContent = j.cracking ? "● cracking…" : "no pass yet";
    }
    if (hint) hint.textContent = j.cracking ? "hashcat is running…" : "crack idle";
  } catch (e) {}
}

function showHunter() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null;
  state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  hunterPageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "✕ HUNTER"));
  const pine = el("div", "re-pine", "handshake · pmkid · crack");
  head.appendChild(pine);
  const hint = el("div", "hint", "");
  hint.id = "hunter-hint";
  head.appendChild(hint);
  page.appendChild(head);

  const stats = el("div", "re-stats");
  stats.id = "hunter-stats";
  page.appendChild(stats);

  const alert = el("div", "hs-alert");
  alert.id = "hunter-alert";
  page.appendChild(alert);

  const bar = el("div", "re-bar");
  const scan = el("button", "big-btn run", "▶ SCAN ENV");
  scan.onclick = () => hunterEnvScan();
  const stop = el("button", "big-btn stop", "■ STOP");
  stop.onclick = async () => {
    try { await fetch("/api/hs/stop", { method: "POST" }); } catch (e) {}
  };
  const pokeLbl = el("label", null);
  const pokeChk = el("input");
  pokeChk.type = "checkbox";
  pokeChk.id = "hunter-autodeauth";
  pokeChk.checked = true;
  pokeLbl.style.cssText = "display:flex;align-items:center;gap:6px;padding:0 10px;font:13px/1 'Fira Code',monospace;color:#9febb9;";
  pokeLbl.appendChild(pokeChk);
  pokeLbl.appendChild(el("span", null, " deauth-auto"));
  bar.append(scan, stop, pokeLbl);
  page.appendChild(bar);

  const apsHead = el("div", "re-tabs");
  apsHead.appendChild(el("span", "ra-sub", "TARGETS — tap HUNT to capture"));
  page.appendChild(apsHead);
  const aps = el("div", "re-table");
  aps.id = "hunter-aps";
  page.appendChild(aps);

  const capHead = el("div", "re-tabs");
  capHead.appendChild(el("span", "ra-sub", "CAPTURES — convert + crack with rockyou"));
  page.appendChild(capHead);
  const caps = el("div", "re-table");
  caps.id = "hunter-caps";
  page.appendChild(caps);

  c.appendChild(page);
  renderHunterAps();

  const tick = async () => {
    if (!hunterPageOpen) return;
    try {
      const st = await fetch("/api/hs/state").then(r => r.json());
      const cp = await fetch("/api/hs/captures").then(r => r.json());
      hunterStats(st);
      hunterAlert(st);
      renderHunterCaps(cp.captures);
      const h = document.getElementById("hunter-hint");
      if (h && st.running) h.textContent = "▶ capturing " + (st.target || "").slice(0, 14) + " on ch " + (st.channel || "any") + " — deauth to force";
      if (h && st.running) {
        let d = document.getElementById("hunter-deauth");
        if (!d) {
          d = el("button", "mini-btn warn", "◙ DEAUTH NOW");
          d.id = "hunter-deauth";
          d.style.margin = "6px 0 0";
          d.onclick = () => hsDeauth(st.target);
          const stes = document.getElementById("hunter-stats");
          stes.parentNode.insertBefore(d, stes.nextSibling);
        }
      }
    } catch (e) {}
  };
  hunterTimer = setInterval(tick, 3000);
  tick();
}

/* ================= Wardrive ================= */

let wardrivePageOpen = false;
let wardriveTimer = null;

function showWardrive() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null;
  state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  wardrivePageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "◈ WARD-RIVE"));
  const pine = el("div", "re-pine", "phone-GPS · QR page · WiGLE csv");
  head.appendChild(pine);
  const hint = el("div", "hint", "");
  hint.id = "wardrive-hint";
  head.appendChild(hint);
  page.appendChild(head);

  const stats = el("div", "re-stats");
  stats.id = "wardrive-stats";
  page.appendChild(stats);

  // setup / control bar
  const ctr = el("div", "wardrive-ctr");
  const ifaceRow = el("div", "wdr-row");
  ifaceRow.appendChild(el("span", "wdr-lbl", "card"));
  const sel = el("select", "wdr-sel");
  sel.id = "wardrive-iface";
  const opt = el("option", null, "auto");
  opt.value = "";
  sel.appendChild(opt);
  ifaceRow.appendChild(sel);
  const bleLbl = el("label", "wdr-ble");
  const bleChk = el("input");
  bleChk.type = "checkbox";
  bleChk.id = "wardrive-ble";
  bleLbl.appendChild(bleChk);
  bleLbl.appendChild(el("span", null, " BLE"));
  ifaceRow.appendChild(bleLbl);
  ctr.appendChild(ifaceRow);

  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ START DRIVE");
  start.id = "wardrive-start";
  start.onclick = () => wardriveStart();
  const stop = el("button", "big-btn stop", "■ STOP");
  stop.id = "wardrive-stop";
  stop.onclick = async () => { try { await fetch("/api/wardrive/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);

  // phone / QR area
  const qrHead = el("div", "re-tabs");
  qrHead.appendChild(el("span", "ra-sub", "PHONE LINK — always live — scan the QR, accept the cert, tap START ON THE PHONE"));
  page.appendChild(qrHead);
  const qrBox = el("div", "wardrive-qr");
  qrBox.id = "wardrive-qr";
  page.appendChild(qrBox);

  const logHead = el("div", "re-tabs");
  logHead.appendChild(el("span", "ra-sub", "DRIVE LOG"));
  page.appendChild(logHead);
  const log = el("div", "re-console");
  log.id = "wardrive-log";
  page.appendChild(log);

  c.appendChild(page);

  const tick = async () => {
    if (!wardrivePageOpen) return;
    try {
      const st = await fetch("/api/wardrive/status").then(r => r.json());
      wardriveRender(st);
    } catch (e) {}
  };
  wardriveTimer = setInterval(tick, 2500);
  tick();
}

function wardriveRender(st) {
  const sel = document.getElementById("wardrive-iface");
  if (sel && st.ifaces && st.ifaces.length) {
    const cur = sel.value;
    sel.innerHTML = "";
    const opts = [["", "auto"], ...st.ifaces.map(i => [i, i])];
    opts.forEach(([v, lab]) => {
      const o = el("option", null, lab);
      o.value = v;
      sel.appendChild(o);
    });
    if (st.ifaces.includes(cur)) sel.value = cur;
    else sel.value = st.iface && st.ifaces.includes(st.iface) ? st.iface : "";
  }
  const stBox = document.getElementById("wardrive-stats");
  const last = st.last || {};
  const gpsCls = last.gps === "fresh" ? "ok" : (last.gps === "none" ? "idle" : "warn");
  const phCls = last.phone === "up" ? "ok" : (last.phone === "manual" ? "ok" : "idle");
  const rows = [
    ["RUN", st.running ? "▶ live" : "idle", st.running ? "ok" : "idle"],
    ["iface", st.iface || "—", ""],
    ["GPS", last.gps || "none", gpsCls],
    ["phone", last.phone || "down", phCls],
    ["APs", (last.total != null ? last.total : "—"), ""],
    ["locatd", (last.located != null ? last.located : "—"), ""],
  ];
  if (st.running && last.cycle != null) rows.push(["cycle", last.cycle, ""]);
  if (stBox) {
    stBox.innerHTML = "";
    rows.forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      const lab = el("span", "re-stat-lab", k);
      const val = el("span", "re-stat-val" + (cls ? " " + cls : ""), v);
      cell.append(lab, val);
      stBox.appendChild(cell);
    });
  }
  const sbtn = document.getElementById("wardrive-start");
  if (sbtn) sbtn.disabled = st.running;
  const qr = document.getElementById("wardrive-qr");
  if (qr) {
    qr.innerHTML = "";
    if (st.qr) {
      const imgBox = el("div", "wdr-qr-img");
      const img = el("img");
      img.src = st.qr;
      img.alt = "QR";
      imgBox.appendChild(img);
      qr.appendChild(imgBox);
      qr.appendChild(el("div", "wdr-qr-url", st.url || "…"));
      qr.prepend(el("div", "wdr-qr-tip",
        st.running
          ? "phone must be on the same network — open this with your phone's camera:"
          : "phone GPS link is LIVE — scan, tap START on the phone, then START DRIVE here to record."));
    } else {
      const idle = el("div", "wdr-qr-tip", "phone GPS link is starting — scan as soon as it appears.");
      qr.appendChild(idle);
    }
  }
  const log = document.getElementById("wardrive-log");
  if (log) {
    if (st.tail.length > 0) {
      log.innerHTML = "";
      st.tail.forEach(evt => {
        if (typeof evt === "string") {
          log.appendChild(el("div", "lg-ln", evt));
        } else if (evt.event === "scan") {
          log.appendChild(el("div", "lg-ln",
            "#" + evt.cycle + "  " + evt.wifi + " APs  GPS:" + (evt.gps || "none") +
            "  ph:" + (evt.phone || "?") + "  located:" + (evt.located || 0)));
        } else if (evt.event === "done") {
          log.appendChild(el("div", "lg-ln", "■ done — " + evt.total + " APs → " + evt.out));
        } else if (evt.event === "error") {
          log.appendChild(el("div", "lg-ln err", "✕ " + (evt.msg || "error")));
        } else if (evt.event === "boot") {
          log.appendChild(el("div", "lg-ln", "▶ drive on " + evt.iface + " → " + evt.out +
            (evt.manual ? " [manual pin]" : "")));
        } else {
          log.appendChild(el("div", "lg-ln", JSON.stringify(evt)));
        }
      });
      log.scrollTop = log.scrollHeight;
    } else {
      log.appendChild(el("div", "lg-ln idle", "no drive yet."));
    }
  }
}

async function wardriveStart() {
  const iface = document.getElementById("wardrive-iface").value;
  const ble = document.getElementById("wardrive-ble").checked;
  const sbtn = document.getElementById("wardrive-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "starting…"; }
  try {
    const r = await fetch("/api/wardrive/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ iface, ble }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ START DRIVE" : "start failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ START DRIVE"; }, 3000);
    }
  } catch (e) {
    if (sbtn) { sbtn.textContent = "▶ START DRIVE"; sbtn.disabled = false; }
  }
}

/* ================= Rogue AP ================= */

let roguePageOpen = false;
let rogueTimer = null;

function showRogue() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null;
  state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  roguePageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "⚑ ROGUE AP"));
  const pine = el("div", "re-pine", "evil twin · captive portal · cred capture");
  head.appendChild(pine);
  const hint = el("div", "hint", "");
  hint.id = "rogue-hint";
  head.appendChild(hint);
  page.appendChild(head);

  const stats = el("div", "re-stats");
  stats.id = "rogue-stats";
  page.appendChild(stats);

  const ctr = el("div", "wardrive-ctr");

  const row1 = el("div", "wdr-row");
  row1.appendChild(el("span", "wdr-lbl", "card"));
  const sel = el("select", "wdr-sel");
  sel.id = "rogue-iface";
  row1.appendChild(sel);
  ctr.appendChild(row1);

  const row2 = el("div", "wdr-row");
  row2.appendChild(el("span", "wdr-lbl", "ssid"));
  const ssid = el("input", "wdr-inp");
  ssid.id = "rogue-ssid";
  ssid.value = "Free-WiFi";
  ssid.maxLength = 26;
  row2.appendChild(ssid);
  ctr.appendChild(row2);

  const row3 = el("div", "wdr-row");
  row3.appendChild(el("span", "wdr-lbl", "ch"));
  const ch = el("input", "wdr-inp wdr-sm");
  ch.id = "rogue-ch";
  ch.value = "6";
  ch.inputMode = "numeric";
  row3.appendChild(ch);
  const psLbl = el("span", "wdr-lbl", "wpa2-psk");
  const ps = el("input", "wdr-inp");
  ps.id = "rogue-psk";
  ps.placeholder = "leave empty for open";
  row3.appendChild(psLbl);
  row3.appendChild(ps);
  ctr.appendChild(row3);

  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ SPIN UP AP");
  start.id = "rogue-start";
  start.onclick = () => rogueStart();
  const stop = el("button", "big-btn stop", "■ TEAR DOWN");
  stop.id = "rogue-stop";
  stop.onclick = async () => { try { await fetch("/api/rogue/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);

  const clHead = el("div", "re-tabs");
  clHead.appendChild(el("span", "ra-sub", "CLIENTS"));
  page.appendChild(clHead);
  const clients = el("div", "re-table");
  clients.id = "rogue-clients";
  page.appendChild(clients);

  const crHead = el("div", "re-tabs");
  crHead.appendChild(el("span", "ra-sub", "CAPTURED CREDS — dnsmasq points every name here"));
  page.appendChild(crHead);
  const creds = el("div", "re-table");
  creds.id = "rogue-creds";
  page.appendChild(creds);

  c.appendChild(page);

  const tick = async () => {
    if (!roguePageOpen) return;
    try {
      const st = await fetch("/api/rogue/status").then(r => r.json());
      rogueRender(st);
    } catch (e) {}
  };
  rogueTimer = setInterval(tick, 2500);
  tick();
}

function rogueRender(st) {
  const sel = document.getElementById("rogue-iface");
  if (sel && st.ifaces) {
    const cur = sel.value;
    sel.innerHTML = "";
    const opts = [["", "auto"], ...(st.ifaces || []).map(i => [i, i])];
    opts.forEach(([v, lab]) => {
      const o = el("option", null, lab);
      o.value = v;
      sel.appendChild(o);
    });
    sel.value = cur || "";
  }
  const stBox = document.getElementById("rogue-stats");
  if (stBox) {
    stBox.innerHTML = "";
    const rows = [
      ["AP", st.running ? "▶ live" : "down", st.running ? "ok" : "idle"],
      ["ssid", st.ssid || "—", ""],
      ["ch", st.channel != null ? st.channel : "—", ""],
      ["hostapd", st.hostapd ? "ok" : "missing", st.hostapd ? "ok" : "warn"],
      ["clients", st.clients ? st.clients.length : 0, ""],
      ["creds", st.creds ? st.creds.length : 0, ""],
    ];
    rows.forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k),
                  el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
  }
  const hint = document.getElementById("rogue-hint");
  if (hint) hint.textContent = st.running ? "victims connect to '" + st.ssid + "' on " + st.iface : "";
  const sbtn = document.getElementById("rogue-start");
  if (sbtn) sbtn.disabled = st.running;
  const clients = document.getElementById("rogue-clients");
  if (clients) {
    clients.innerHTML = "";
    const rows = st.clients || [];
    if (!rows.length) clients.appendChild(el("div", "re-empty", "waiting for DHCP clients…"));
    rows.forEach(cx => {
      const r = el("div", "ra-row");
      const m = el("div", "ra-main");
      m.appendChild(el("span", "ra-sig", "•"));
      m.appendChild(el("div", null, cx.ip + "  " + cx.mac.toUpperCase()));
      if (cx.host && cx.host !== "*") m.appendChild(el("div", "sub", cx.host));
      r.appendChild(m);
      clients.appendChild(r);
    });
  }
  const creds = document.getElementById("rogue-creds");
  if (creds) {
    creds.innerHTML = "";
    const rows = st.creds || [];
    if (!rows.length) creds.appendChild(el("div", "re-empty", "no credentials captured yet."));
    rows.forEach(rc => {
      const r = el("div", "ra-row");
      const m = el("div", "ra-main");
      m.appendChild(el("span", "ra-sig", "◎"));
      const mid = el("div", "tb-mid");
      mid.appendChild(el("div", null, rc.user + " / " + rc.pw));
      mid.appendChild(el("div", "sub", rc.time + "  from " + rc.ip + "  (" + rc.ssid + ")"));
      m.appendChild(mid);
      r.appendChild(m);
      creds.appendChild(r);
    });
  }
}

async function rogueStart() {
  const iface = document.getElementById("rogue-iface").value;
  const ssid = document.getElementById("rogue-ssid").value || "Free-WiFi";
  const ch = document.getElementById("rogue-ch").value || "6";
  const psk = document.getElementById("rogue-psk").value || "";
  const sbtn = document.getElementById("rogue-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "spinning up…"; }
  try {
    const r = await fetch("/api/rogue/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ iface, ssid, channel: ch, psk: psk || null }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ SPIN UP AP" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ SPIN UP AP"; }, 3500);
    }
  } catch (e) {
    if (sbtn) { sbtn.textContent = "▶ SPIN UP AP"; sbtn.disabled = false; }
  }
}

/* ================= WiFi Radar ================= */

let radarPageOpen = false;
let radarTimer = null;
let radarRAF = 0;
let radarSweepDeg = 0;
let radarLastD = { aps: [], clients: [] };
let radarLastSt = { running: false, iface: null };
let radarFilter = "all";
const radarAngle = {};

function radarAng(b) {
  if (!(b in radarAngle)) {
    let hd = 7;
    for (const ch of b) hd = (hd * 31 + ch.charCodeAt(0)) >>> 0;
    radarAngle[b] = (hd % 3600) / 10;
  }
  return radarAngle[b];
}

function radarDist(p) {
  const v = parseInt(p, 10);
  if (Number.isNaN(v)) return 0.5;
  const d = 1 - ((v + 95) / 65);
  return Math.min(0.95, Math.max(0.05, d));
}

function radarBand(ap) {
  return parseInt(ap.channel, 10) <= 14 ? "2.4" : "5";
}

function radarPos(ap, W, H) {
  const ang = (radarAng(ap.bssid) * Math.PI) / 180;
  const R = Math.min(W, H) / 2 - 10;
  const cx = W / 2, cy = H / 2;
  const d = radarDist(ap.power);
  return { x: cx + Math.cos(ang) * d * R, y: cy + Math.sin(ang) * d * R };
}

function drawRadar(aps, sweepDeg, now) {
  const cv = document.getElementById("radar-canvas");
  if (!cv) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const W = cv.clientWidth || 450;
  const H = cv.clientHeight || 330;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) {
    cv.width = Math.round(W * dpr);
    cv.height = Math.round(H * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const bg = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.min(W, H) / 2);
  bg.addColorStop(0, "#06281a");
  bg.addColorStop(1, "#02100a");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2;
  const R = Math.min(W, H) / 2 - 8;
  ctx.strokeStyle = "rgba(26,110,78,.5)";
  ctx.lineWidth = 1;
  [0.3, 0.6, 0.85].forEach(f => {
    ctx.beginPath();
    ctx.arc(cx, cy, R * f, 0, 7);
    ctx.stroke();
  });
  ctx.fillStyle = "#2f7a5e";
  ctx.font = "8px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  [-50, -70, -90].forEach((v, i) => {
    const rr = radarDist(v) * R;
    ctx.fillText("'" + String(v), cx + rr + 7, cy - 2);
  });
  ctx.strokeStyle = "rgba(26,110,78,.22)";
  for (let a = 0; a < 360; a += 45) {
    const rad = (a * Math.PI) / 180;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(rad) * R, cy + Math.sin(rad) * R);
    ctx.stroke();
  }
  const ang = (sweepDeg * Math.PI) / 180;
  const fan = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
  fan.addColorStop(0, "rgba(57,255,20,0)");
  fan.addColorStop(0.7, "rgba(57,255,20,0.045)");
  fan.addColorStop(1, "rgba(57,255,20,0.15)");
  ctx.fillStyle = fan;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.arc(cx, cy, R, ang - 0.65, ang);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "rgba(140,255,170,.9)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(ang) * R, cy + Math.sin(ang) * R);
  ctx.stroke();
  ctx.fillStyle = "#b8ffc0";
  ctx.shadowColor = "#39ff14";
  ctx.shadowBlur = 8;
  ctx.beginPath();
  ctx.arc(cx + Math.cos(ang) * R, cy + Math.sin(ang) * R, 2.6, 0, 7);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillStyle = "#39ff14";
  ctx.font = "9px monospace";
  ctx.fillText("APS " + aps.length, 10, 10);
  ctx.fillStyle = "#2f7a5e";
  ctx.fillText("2.4 ● " + "5G ●  OPN ●", 10, H - 16);
  for (const ap of aps) {
    const p = radarPos(ap, W, H);
    const isOpen = /OPN/i.test(ap.privacy || "");
    const col = isOpen ? "#ff5f5f" : (radarBand(ap) === "2.4" ? "#39ff14" : "#00d9ff");
    const pulse = 2.6 + 1.4 * Math.sin(now / 230 + radarAng(ap.bssid));
    ctx.shadowColor = col;
    ctx.shadowBlur = 9;
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.arc(p.x, p.y, pulse, 0, 7);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#d8ffe9";
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 1.1, 0, 7);
    ctx.fill();
    ctx.fillStyle = "#9fdfc0";
    ctx.font = "9px monospace";
    const nm = (ap.essid ? ap.essid : "hidden").slice(0, 12);
    const lx = Math.min(Math.max(p.x - 14, 2), W - 60);
    ctx.fillText(nm, lx, p.y - 11);
  }
}

function radarPick(ev) {
  const cv = document.getElementById("radar-canvas");
  if (!cv) return;
  const rect = cv.getBoundingClientRect();
  const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
  const filtered = radarLastD.aps.filter(ap => radarFilter === "all" || radarBand(ap) === radarFilter);
  const hit = filtered.find(ap => {
    const p = radarPos(ap, rect.width, rect.height);
    return Math.hypot(px - p.x, py - p.y) < 26;
  });
  if (!hit) return;
  const det = document.getElementById("radar-detail");
  if (!det) return;
  const nclients = radarLastD.clients.filter(c => c.bssid && c.bssid.toUpperCase() === hit.bssid.toUpperCase()).length;
  det.innerHTML = "";
  const tt = el("div", "radar-pop");
  tt.appendChild(el("div", "re-pine", hit.essid ? "◈ " + hit.essid : "◈ hidden"));
  const sub = el("div", "ra-sub", hit.bssid + "  ·  CH " + hit.channel + "  ·  " + (hit.power || "?") + " dBm  ·  " +
    (hit.privacy || "?") + "  ·  clients " + nclients);
  tt.appendChild(sub);
  const bt = el("div", "ra-btnrow");
  const hunt = el("button", "mini-btn hunt", "HUNT");
  hunt.onclick = () => { hsHunt(hit); det.classList.add("hidden"); };
  const da = el("button", "mini-btn warn", "DEAUTH");
  da.onclick = () => { hsDeauth(hit.bssid); det.classList.add("hidden"); };
  const close = el("button", "mini-btn", "CLOSE");
  close.onclick = () => det.classList.add("hidden");
  bt.append(hunt, da, close);
  tt.appendChild(bt);
  det.appendChild(tt);
  det.classList.remove("hidden");
}

function renderRadarAps() {
  const list = document.getElementById("radar-aps");
  if (!list) return;
  const stats = document.getElementById("radar-stats");
  if (stats) {
    let best = -200;
    for (const a of radarLastD.aps) { const p = parseInt(a.power, 10) || -200; if (p > best) best = p; }
    const two = radarLastD.aps.filter(a => radarBand(a) === "2.4").length;
    const five = radarLastD.aps.filter(a => radarBand(a) === "5").length;
    stats.innerHTML = "";
    stats.append(
      mkStatCell("IFACE", radarLastSt.iface ? "▣ " + radarLastSt.iface : "○ none"),
      mkStatCell("APs", radarLastD.aps.length),
      mkStatCell("STRONG", best > -200 ? best + " dBm" : "—"),
      mkStatCell("2.4G", two),
      mkStatCell("5G", five),
    );
  }
  list.innerHTML = "";
  const aps = radarLastD.aps
    .filter(ap => radarFilter === "all" || radarBand(ap) === radarFilter)
    .sort((a, b) => (parseInt(b.power, 10) || -100) - (parseInt(a.power, 10) || -100));
  const no = el("div", "re-empty", "press ▶ SCAN ON to populate");
  if (!aps.length) { list.appendChild(no); return; }
  for (const ap of aps.slice(0, 8)) {
    const row = el("div", "ra-row");
    const t1 = el("div", "ra-main");
    const s = el("span", "ra-sig", (ap.power || "??") + " dBm");
    s.style.background = signalColor(ap.power);
    const essid = el("span", "ra-essid", ap.essid ? ap.essid : "████ (hidden)");
    const ch = el("span", "ra-ch", "CH " + ap.channel);
    const nclients = radarLastD.clients.filter(c => c.bssid && c.bssid.toUpperCase() === ap.bssid.toUpperCase()).length;
    const sec = el("span", "ra-sec", ap.privacy || "?");
    const cl = el("span", "ra-cl", "◈ " + nclients);
    t1.append(s, essid, ch, sec, cl);
    const t2 = el("div", "ra-sub", ap.bssid);
    row.append(t1, t2);
    list.appendChild(row);
  }
}

function showRadar() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null;
  state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  radarPageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "◎ RADAR"));
  const pine = el("div", "re-pine", "live · real-time platform");
  head.appendChild(pine);
  const hint = el("div", "hint", "");
  hint.id = "radar-hint";
  head.appendChild(hint);
  page.appendChild(head);

  const rstats = el("div", "re-stats");
  rstats.id = "radar-stats";
  page.appendChild(rstats);

  const box = el("div", "radar-box");
  const cv = document.createElement("canvas");
  cv.className = "radar-canvas";
  cv.id = "radar-canvas";
  cv.addEventListener("pointerdown", radarPick);
  box.appendChild(cv);
  const detail = el("div", "radar-detail");
  detail.id = "radar-detail";
  detail.classList.add("hidden");
  box.appendChild(detail);
  page.appendChild(box);

  const bar = el("div", "re-bar");
  const on = el("button", "big-btn run", "▶ SCAN ON");
  on.onclick = async () => {
    on.classList.add("busy"); on.textContent = "starting…";
    try {
      const r = await fetch("/api/recon/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const j = await r.json();
      if (hint) hint.textContent = j.ok ? "scanning " + j.msg : "✗ " + j.msg;
    } catch (e) {}
    on.classList.remove("busy"); on.textContent = "▶ SCAN ON";
  };
  const off = el("button", "big-btn stop", "■ OFF");
  off.onclick = async () => {
    try { await fetch("/api/recon/stop", { method: "POST" }); } catch (e) {}
  };
  bar.append(on, off);
  page.appendChild(bar);

  const chips = el("div", "re-chip");
  const mk = (v, lab) => {
    const b = el("button", "chip" + (radarFilter === v ? " on" : ""), lab);
    b.onclick = () => { radarFilter = v; renderRadarAps(); };
    chips.appendChild(b);
  };
  mk("all", "ALL"); mk("2.4", "2.4G"); mk("5", "5G");
  page.appendChild(chips);

  const capHead = el("div", "re-tabs");
  capHead.appendChild(el("span", "ra-sub", "STRONGEST — tap blips or scan to hunt"));
  page.appendChild(capHead);
  const aps = el("div", "re-table");
  aps.id = "radar-aps";
  page.appendChild(aps);

  c.appendChild(page);
  renderRadarAps();

  const poke = async () => {
    if (!radarPageOpen) return;
    try {
      const [st, d] = await Promise.all([
        fetch("/api/recon/state").then(r => r.json()),
        fetch("/api/recon/data").then(r => r.json()),
      ]);
      radarLastD = d;
      radarLastSt = st;
      renderRadarAps();
      if (hint) {
        if (st.running) hint.textContent = "scanning " + (st.iface || "") + " · " + d.aps.length + " APs";
        else if (d.aps.length === 0) hint.textContent = "press ▶ SCAN ON";
      }
    } catch (e) {}
  };
  radarTimer = setInterval(poke, 3000);
  poke();
  const loop = (now) => {
    if (!radarPageOpen) return;
    radarSweepDeg = (now / 1000) * 20 % 360;
    drawRadar(radarLastD.aps.filter(ap => radarFilter === "all" || radarBand(ap) === radarFilter), radarSweepDeg, now);
    radarRAF = requestAnimationFrame(loop);
  };
  radarRAF = requestAnimationFrame(loop);
}

function leaveRadar() {
  radarPageOpen = false;
  if (radarTimer) { clearInterval(radarTimer); radarTimer = null; }
  if (radarRAF) { cancelAnimationFrame(radarRAF); radarRAF = 0; }
}

function leaveWardrive() {
  wardrivePageOpen = false;
  if (wardriveTimer) { clearInterval(wardriveTimer); wardriveTimer = null; }
}

function leaveRogue() {
  roguePageOpen = false;
  if (rogueTimer) { clearInterval(rogueTimer); rogueTimer = null; }
}

/* ================= Probe Tracker ================= */

let probePageOpen = false;
let probeTimer = null;

function showProbe() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  probePageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "◉ PROBE TRACKER"));
  head.appendChild(el("div", "re-pine", "who's prospecting which SSIDs"));
  page.appendChild(head);
  const stats = el("div", "re-stats");
  stats.id = "probe-stats";
  page.appendChild(stats);
  const ctr = el("div", "wardrive-ctr");
  const ifRow = el("div", "wdr-row");
  ifRow.appendChild(el("span", "wdr-lbl", "card"));
  const sel = el("select", "wdr-sel");
  sel.id = "probe-iface";
  ifRow.appendChild(sel);
  ctr.appendChild(ifRow);
  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ LISTEN");
  start.id = "probe-start";
  start.onclick = () => probeStart();
  const stop = el("button", "big-btn stop", "■ STOP");
  stop.id = "probe-stop";
  stop.onclick = async () => { try { await fetch("/api/probe/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);
  const tHead = el("div", "re-tabs");
  tHead.appendChild(el("span", "ra-sub", "SSIDs BEING PROBED"));
  page.appendChild(tHead);
  const top = el("div", "re-table");
  top.id = "probe-top";
  page.appendChild(top);
  const cHead = el("div", "re-tabs");
  cHead.appendChild(el("span", "ra-sub", "PROBING CLIENTS"));
  page.appendChild(cHead);
  const clients = el("div", "re-table");
  clients.id = "probe-clients";
  page.appendChild(clients);
  c.appendChild(page);
  const tick = async () => {
    if (!probePageOpen) return;
    try { probeRender(await fetch("/api/probe/status").then(r => r.json())); } catch (e) {}
  };
  probeTimer = setInterval(tick, 2500);
  tick();
}

function probeRender(st) {
  const sel = document.getElementById("probe-iface");
  if (sel && st.ifaces) {
    const cur = sel.value;
    sel.innerHTML = "";
    const opts = [["", "auto"], ...(st.ifaces || []).map(i => [i, i])];
    opts.forEach(([v, lab]) => { const o = el("option", null, lab); o.value = v; sel.appendChild(o); });
    sel.value = cur || st.iface || "";
  }
  const stBox = document.getElementById("probe-stats");
  if (stBox) {
    stBox.innerHTML = "";
    [
      ["RUN", st.running ? "▶ live" : "idle", st.running ? "ok" : "idle"],
      ["iface", st.iface || "—", ""],
      ["SSIDs", st.seen != null ? st.seen : 0, ""],
      ["clients", st.clients ? st.clients.length : 0, ""],
    ].forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k), el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
  }
  const sbtn = document.getElementById("probe-start");
  if (sbtn) sbtn.disabled = st.running;
  const top = document.getElementById("probe-top");
  if (top) {
    top.innerHTML = "";
    const rows = st.top || [];
    if (!rows.length) top.appendChild(el("div", "re-empty", st.running ? "waiting for probes…" : "listening…"));
    const max = Math.max(1, ...rows.map(r => r.count));
    rows.forEach(r => {
      const row = el("div", "ra-row");
      const m = el("div", "ra-main");
      m.appendChild(el("span", "ra-sig", "◉"));
      const mid = el("div", "tb-mid");
      mid.appendChild(el("div", null, '"' + r.ssid + '"'));
      const fill = el("div", "fl-bar");
      const pixel = el("div", "fl-fill");
      pixel.style.width = Math.round(100 * r.count / max) + "%";
      fill.appendChild(pixel);
      mid.appendChild(fill);
      mid.appendChild(el("div", "sub", r.count + " clients ringing"));
      m.appendChild(mid);
      row.appendChild(m);
      top.appendChild(row);
    });
  }
  const cl = document.getElementById("probe-clients");
  if (cl) {
    cl.innerHTML = "";
    const rows = st.clients || [];
    if (!rows.length) cl.appendChild(el("div", "re-empty", "no probing clients seen yet."));
    rows.forEach(cx => {
      const row = el("div", "ra-row");
      const m = el("div", "ra-main");
      m.appendChild(el("span", "ra-sig", "»"));
      const mid = el("div", "tb-mid");
      mid.appendChild(el("div", null, cx.mac  + "  ·  " + (cx.power || "?") + " dBm"));
      mid.appendChild(el("div", "sub", "wants: " + cx.names.join(" , ")));
      m.appendChild(mid);
      row.appendChild(m);
      cl.appendChild(row);
    });
  }
}

async function probeStart() {
  const iface = document.getElementById("probe-iface").value;
  const sbtn = document.getElementById("probe-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "arming…"; }
  try {
    const r = await fetch("/api/probe/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ iface }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ LISTEN" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ LISTEN"; }, 3000);
    }
  } catch (e) { if (sbtn) { sbtn.textContent = "▶ LISTEN"; sbtn.disabled = false; } }
}

function leaveProbe() {
  probePageOpen = false;
  if (probeTimer) { clearInterval(probeTimer); probeTimer = null; }
}

/* ================= Deauth Blaster ================= */

let deauthPageOpen = false;
let deauthTimer = null;

function showDeauth() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  deauthPageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "⚡ DEAUTH BLASTER"));
  head.appendChild(el("div", "re-pine", "targeted — or everyone-cuts"));
  page.appendChild(head);
  const stats = el("div", "re-stats");
  stats.id = "deauth-stats";
  page.appendChild(stats);
  const ctr = el("div", "wardrive-ctr");
  const modeRow = el("div", "wdr-row");
  modeRow.appendChild(el("span", "wdr-lbl", "mode"));
  const mode = el("select", "wdr-sel");
  mode.id = "deauth-mode";
  [["target", "targeted AP"], ["flood", "EVERYONE in range"]].forEach(([v, lab]) => {
    const o = el("option", null, lab); o.value = v; mode.appendChild(o);
  });
  modeRow.appendChild(mode);
  ctr.appendChild(modeRow);
  const bRow = el("div", "wdr-row");
  bRow.appendChild(el("span", "wdr-lbl", "bssid"));
  const bb = el("input", "wdr-inp");
  bb.id = "deauth-bssid";
  bb.placeholder = "AA:BB:CC:DD:EE:FF";
  bRow.appendChild(bb);
  const sc = el("button", "mini-btn", "SCAN");
  sc.id = "deauth-scan";
  sc.onclick = () => deauthScan();
  bRow.appendChild(sc);
  ctr.appendChild(bRow);
  const cRow = el("div", "wdr-row");
  cRow.appendChild(el("span", "wdr-lbl", "ch"));
  const ch = el("input", "wdr-inp wdr-sm");
  ch.id = "deauth-ch";
  ch.value = "6";
  ch.inputMode = "numeric";
  cRow.appendChild(ch);
  cRow.appendChild(el("span", "wdr-lbl", "client"));
  const cl = el("input", "wdr-inp");
  cl.id = "deauth-client";
  cl.placeholder = "optional";
  cRow.appendChild(cl);
  ctr.appendChild(cRow);
  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ BLAST");
  start.id = "deauth-start";
  start.onclick = () => deauthStart();
  const stop = el("button", "big-btn stop", "■ STOP");
  stop.id = "deauth-stop";
  stop.onclick = async () => { try { await fetch("/api/deauth/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);
  const aHead = el("div", "re-tabs");
  aHead.appendChild(el("span", "ra-sub", "PICK A TARGET FROM SCAN"));
  page.appendChild(aHead);
  const aps = el("div", "re-table");
  aps.id = "deauth-aps";
  page.appendChild(aps);
  c.appendChild(page);
  const tick = async () => {
    if (!deauthPageOpen) return;
    try { deauthRender(await fetch("/api/deauth/status").then(r => r.json())); } catch (e) {}
  };
  deauthTimer = setInterval(tick, 2500);
  tick();
}

function deauthRender(st) {
  const stBox = document.getElementById("deauth-stats");
  if (stBox) {
    stBox.innerHTML = "";
    [
      ["RUN", st.running ? "▶ blasting" : "idle", st.running ? "ok" : "idle"],
      ["mode", st.mode || "—", ""],
      ["target", st.target || "—", ""],
      ["elapsed", st.elapsed ? st.elapsed + "s" : "—", ""],
    ].forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k), el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
  }
  const sbtn = document.getElementById("deauth-start");
  if (sbtn) sbtn.disabled = st.running;
}

async function deauthScan() {
  const out = document.getElementById("deauth-aps");
  if (!out) return;
  out.innerHTML = "";
  out.appendChild(el("div", "re-empty", "scanning 7s…"));
  try {
    const r = await fetch("/api/deauth/scan", { method: "POST" }).then(r => r.json());
    out.innerHTML = "";
    const rows = r.aps || [];
    if (!rows.length) out.appendChild(el("div", "re-empty", "no APs heard."));
    rows.forEach(a => {
      const row = el("div", "ra-row");
      const m = el("div", "ra-main");
      m.appendChild(el("span", "ra-sig", "✕"));
      const mid = el("div", "tb-mid");
      mid.appendChild(el("div", null, (a.essid || "(hidden)") + "  ·  ch " + a.channel));
      mid.appendChild(el("div", "sub", a.bssid + "  " + a.power + " dBm"));
      m.appendChild(mid);
      row.appendChild(m);
      row.onclick = () => {
        const b = document.getElementById("deauth-bssid");
        const ch = document.getElementById("deauth-ch");
        if (b) b.value = a.bssid;
        if (ch) ch.value = a.channel;
      };
      out.appendChild(row);
    });
  } catch (e) { out.innerHTML = ""; out.appendChild(el("div", "re-empty", "scan failed")); }
}

async function deauthStart() {
  const mode = document.getElementById("deauth-mode").value;
  const bssid = document.getElementById("deauth-bssid").value;
  const ch = document.getElementById("deauth-ch").value;
  const client = document.getElementById("deauth-client").value;
  const sbtn = document.getElementById("deauth-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "arming…"; }
  try {
    const r = await fetch("/api/deauth/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, bssid, channel: ch, client }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ BLAST" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ BLAST"; }, 3500);
    }
  } catch (e) { if (sbtn) { sbtn.textContent = "▶ BLAST"; sbtn.disabled = false; } }
}

function leaveDeauth() {
  deauthPageOpen = false;
  if (deauthTimer) { clearInterval(deauthTimer); deauthTimer = null; }
}

/* ================= Beacon Flood ================= */

let floodPageOpen = false;
let floodTimer = null;

function showFlood() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  floodPageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "◐ BEACON FLOOD"));
  head.appendChild(el("div", "re-pine", "fake SSIDs flooding the air"));
  page.appendChild(head);
  const stats = el("div", "re-stats");
  stats.id = "flood-stats";
  page.appendChild(stats);
  const ctr = el("div", "wardrive-ctr");
  const sRow = el("div", "wdr-row");
  sRow.appendChild(el("span", "wdr-lbl", "ssids"));
  const ss = el("input", "wdr-inp");
  ss.id = "flood-ssids";
  ss.placeholder = "Starbucks-Guest, ATT, iPhone, …";
  sRow.appendChild(ss);
  ctr.appendChild(sRow);
  const opts = el("div", "wdr-row");
  const chLbl = el("label", "wdr-ble");
  const fchk = el("input");
  fchk.type = "checkbox";
  fchk.id = "flood-borrow";
  chLbl.appendChild(fchk);
  chLbl.appendChild(el("span", null, " borrow probed names"));
  opts.appendChild(chLbl);
  const hLbl = el("label", "wdr-ble");
  const hchk = el("input");
  hchk.type = "checkbox";
  hchk.id = "flood-hidden";
  hLbl.appendChild(hchk);
  hLbl.appendChild(el("span", null, " hidden"));
  opts.appendChild(hLbl);
  ctr.appendChild(opts);
  const chRow = el("div", "wdr-row");
  chRow.appendChild(el("span", "wdr-lbl", "channels"));
  const cc = el("input", "wdr-inp");
  cc.id = "flood-channels";
  cc.value = "1,6,11";
  chRow.appendChild(cc);
  ctr.appendChild(chRow);
  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ FLOOD");
  start.id = "flood-start";
  start.onclick = () => floodStart();
  const stop = el("button", "big-btn stop", "■ STOP");
  stop.id = "flood-stop";
  stop.onclick = async () => { try { await fetch("/api/flood/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);
  c.appendChild(page);
  const tick = async () => {
    if (!floodPageOpen) return;
    try { floodRender(await fetch("/api/flood/status").then(r => r.json())); } catch (e) {}
  };
  floodTimer = setInterval(tick, 2500);
  tick();
}

function floodRender(st) {
  const stBox = document.getElementById("flood-stats");
  if (stBox) {
    stBox.innerHTML = "";
    [
      ["RUN", st.running ? "▶ flooding" : "idle", st.running ? "ok" : "idle"],
      ["iface", st.iface || "—", ""],
      ["frames", st.sent != null ? st.sent : 0, ""],
    ].forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k), el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
  }
  const sbtn = document.getElementById("flood-start");
  if (sbtn) sbtn.disabled = st.running;
}

async function floodStart() {
  const ssids = document.getElementById("flood-ssids").value;
  const channels = document.getElementById("flood-channels").value;
  const borrow = document.getElementById("flood-borrow").checked;
  const hidden = document.getElementById("flood-hidden").checked;
  const sbtn = document.getElementById("flood-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "arming…"; }
  try {
    const r = await fetch("/api/flood/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ssids, channels, borrow, hidden }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ FLOOD" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ FLOOD"; }, 3500);
    }
  } catch (e) { if (sbtn) { sbtn.textContent = "▶ FLOOD"; sbtn.disabled = false; } }
}

function leaveFlood() {
  floodPageOpen = false;
  if (floodTimer) { clearInterval(floodTimer); floodTimer = null; }
}

/* ================= Portal Kit ================= */

let portalPageOpen = false;
let portalTimer = null;

function showPortal() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  portalPageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "✪ PORTAL KIT"));
  head.appendChild(el("div", "re-pine", "pit the right dream"));
  page.appendChild(head);
  const stats = el("div", "re-stats");
  stats.id = "portal-stats";
  page.appendChild(stats);
  const ctr = el("div", "wardrive-ctr");
  const tRow = el("div", "wdr-row");
  tRow.appendChild(el("span", "wdr-lbl", "theme"));
  const theme = el("select", "wdr-sel");
  theme.id = "portal-theme";
  tRow.appendChild(theme);
  ctr.appendChild(tRow);
  const iRow = el("div", "wdr-row");
  iRow.appendChild(el("span", "wdr-lbl", "card"));
  const sel = el("select", "wdr-sel");
  sel.id = "portal-iface";
  iRow.appendChild(sel);
  ctr.appendChild(iRow);
  const sRow = el("div", "wdr-row");
  sRow.appendChild(el("span", "wdr-lbl", "ssid"));
  const ss = el("input", "wdr-inp");
  ss.id = "portal-ssid";
  ss.value = "Free-WiFi";
  ss.maxLength = 26;
  sRow.appendChild(ss);
  ctr.appendChild(sRow);
  const cRow = el("div", "wdr-row");
  cRow.appendChild(el("span", "wdr-lbl", "ch"));
  const ch = el("input", "wdr-inp wdr-sm");
  ch.id = "portal-ch";
  ch.value = "6";
  ch.inputMode = "numeric";
  cRow.appendChild(ch);
  cRow.appendChild(el("span", "wdr-lbl", "wpa2-psk"));
  const ps = el("input", "wdr-inp");
  ps.id = "portal-psk";
  ps.placeholder = "leave empty for open";
  cRow.appendChild(ps);
  ctr.appendChild(cRow);
  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ SPIN UP");
  start.id = "portal-start";
  start.onclick = () => portalStart();
  const stop = el("button", "big-btn stop", "■ TEAR DOWN");
  stop.id = "portal-stop";
  stop.onclick = async () => { try { await fetch("/api/portal/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);
  const crHead = el("div", "re-tabs");
  crHead.appendChild(el("span", "ra-sub", "CAPTURED CREDS"));
  page.appendChild(crHead);
  const creds = el("div", "re-table");
  creds.id = "portal-creds";
  page.appendChild(creds);
  c.appendChild(page);
  const tick = async () => {
    if (!portalPageOpen) return;
    try { portalRender(await fetch("/api/portal/status").then(r => r.json())); } catch (e) {}
  };
  portalTimer = setInterval(tick, 2500);
  tick();
}

function portalRender(st) {
  const themeSel = document.getElementById("portal-theme");
  if (themeSel && st.themes) {
    const cur = themeSel.value || st.theme;
    themeSel.innerHTML = "";
    st.themes.forEach(t => {
      const o = el("option", null, t);
      o.value = t;
      themeSel.appendChild(o);
    });
    themeSel.value = cur;
  }
  const sel = document.getElementById("portal-iface");
  if (sel && st.ifaces) {
    const cur = sel.value;
    sel.innerHTML = "";
    const opts = [["", "auto"], ...(st.ifaces || []).map(i => [i, i])];
    opts.forEach(([v, lab]) => { const o = el("option", null, lab); o.value = v; sel.appendChild(o); });
    sel.value = cur || "";
  }
  const stBox = document.getElementById("portal-stats");
  if (stBox) {
    stBox.innerHTML = "";
    [
      ["AP", st.running ? "▶ live" : "down", st.running ? "ok" : "idle"],
      ["theme", st.theme || "—", ""],
      ["clone", st.clone_present ? "ready" : "none", st.clone_present ? "ok" : "idle"],
      ["ssid", st.ssid || "—", ""],
      ["clients", st.clients ? st.clients.length : 0, ""],
      ["creds", st.creds ? st.creds.length : 0, ""],
    ].forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k), el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
  }
  const sbtn = document.getElementById("portal-start");
  if (sbtn) sbtn.disabled = st.running;
  const creds = document.getElementById("portal-creds");
  if (creds) {
    creds.innerHTML = "";
    const rows = st.creds || [];
    if (!rows.length) creds.appendChild(el("div", "re-empty", "no credentials captured yet."));
    rows.forEach(rc => {
      const r = el("div", "ra-row");
      const m = el("div", "ra-main");
      m.appendChild(el("span", "ra-sig", "◎"));
      const mid = el("div", "tb-mid");
      mid.appendChild(el("div", null, rc.user + " / " + rc.pw));
      mid.appendChild(el("div", "sub", rc.time + "  from " + rc.ip + "  (" + rc.ssid + ")"));
      m.appendChild(mid);
      r.appendChild(m);
      creds.appendChild(r);
    });
  }
}

async function portalStart() {
  const theme = document.getElementById("portal-theme").value;
  const iface = document.getElementById("portal-iface").value;
  const ssid = document.getElementById("portal-ssid").value || "Free-WiFi";
  const ch = document.getElementById("portal-ch").value || "6";
  const psk = document.getElementById("portal-psk").value || "";
  const sbtn = document.getElementById("portal-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "spinning up…"; }
  try {
    const r = await fetch("/api/portal/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme, iface, ssid, channel: ch, psk: psk || null }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ SPIN UP" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ SPIN UP"; }, 3500);
    }
  } catch (e) { if (sbtn) { sbtn.textContent = "▶ SPIN UP"; sbtn.disabled = false; } }
}

function leavePortal() {
  portalPageOpen = false;
  if (portalTimer) { clearInterval(portalTimer); portalTimer = null; }
}

/* ================= Login Clone ================= */

let clonePageOpen = false;
let cloneTimer = null;

function showClone() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  clonePageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "❒ LOGIN CLONE"));
  head.appendChild(el("div", "re-pine", "serve a real login page from the rogue AP"));
  page.appendChild(head);
  const stats = el("div", "re-stats");
  stats.id = "clone-stats";
  page.appendChild(stats);
  const ctr = el("div", "wardrive-ctr");
  const uRow = el("div", "wdr-row");
  uRow.appendChild(el("span", "wdr-lbl", "url"));
  const url = el("input", "wdr-inp");
  url.id = "clone-url";
  url.value = "https://";
  uRow.appendChild(url);
  ctr.appendChild(uRow);
  const bar = el("div", "re-bar");
  const go = el("button", "big-btn run", "⤓ FETCH & REWRITE");
  go.id = "clone-go";
  go.onclick = () => cloneStart();
  const clear = el("button", "big-btn stop", "✕ CLEAR");
  clear.id = "clone-clear";
  clear.onclick = async () => { try { await fetch("/api/clone/clear", { method: "POST" }); } catch (e) {} };
  bar.append(go, clear);
  ctr.appendChild(bar);
  page.appendChild(ctr);
  const nHead = el("div", "re-tabs");
  nHead.appendChild(el("span", "ra-sub", "CLONE STATUS"));
  page.appendChild(nHead);
  const note = el("div", "re-console");
  note.id = "clone-note";
  page.appendChild(note);
  c.appendChild(page);
  const tick = async () => {
    if (!clonePageOpen) return;
    try { cloneRender(await fetch("/api/clone/status").then(r => r.json())); } catch (e) {}
  };
  cloneTimer = setInterval(tick, 2500);
  tick();
}

function cloneRender(st) {
  const stBox = document.getElementById("clone-stats");
  if (stBox) {
    stBox.innerHTML = "";
    [
      ["clone", st.present ? "ready" : "none", st.present ? "ok" : "idle"],
      ["busy", st.busy ? "fetching…" : "idle", st.busy ? "warn" : ""],
      ["portal", st.rogue_running ? "up" : "down", st.rogue_running ? "ok" : "idle"],
    ].forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k), el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
  }
  const note = document.getElementById("clone-note");
  if (note) {
    note.innerHTML = "";
    const m = st.meta || {};
    const lines = [];
    lines.push(m.ok ? "clone ready — portal serves it for every host/path" : (st.present ? "clone ready" : "no clone yet"));
    if (m.url) lines.push("source: " + m.url);
    if (m.http) lines.push("HTTP " + m.http + " · " + m.size + " bytes · " + (m.forms || 0) + " form(s) rewritten");
    if (m.time) lines.push("captured " + new Date(m.time * 1000).toLocaleTimeString());
    if (m.error) lines.push("error: " + m.error);
    lines.push(st.rogue_running ? "portal is up — victims see THIS page." : "start a Rogue AP / Portal Kit to serve it.");
    lines.forEach(ln => note.appendChild(el("div", "lg-ln" + (ln.indexOf("error") >= 0 ? " err" : ""), ln)));
  }
  const go = document.getElementById("clone-go");
  if (go) go.disabled = st.busy;
}

async function cloneStart() {
  const url = document.getElementById("clone-url").value || "";
  const go = document.getElementById("clone-go");
  if (go) { go.disabled = true; go.textContent = "fetching…"; }
  try {
    const r = await fetch("/api/clone/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }).then(r => r.json());
    if (go) {
      go.textContent = r.ok ? "⤓ FETCH & REWRITE" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (go) go.textContent = "⤓ FETCH & REWRITE"; }, 3000);
    }
  } catch (e) { if (go) { go.textContent = "⤓ FETCH & REWRITE"; go.disabled = false; } }
}

function leaveClone() {
  clonePageOpen = false;
  if (cloneTimer) { clearInterval(cloneTimer); cloneTimer = null; }
}

/* ================= Auto-Pentest ================= */

let pentestPageOpen = false;
let pentestTimer = null;

function showPentest() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null; state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  pentestPageOpen = true;
  const c = document.querySelector(".content");
  c.innerHTML = "";
  const page = el("div", "recon");
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "⛧ AUTO-PENTEST"));
  head.appendChild(el("div", "re-pine", "capture → deauth → crack → decrypt"));
  page.appendChild(head);
  const stats = el("div", "re-stats");
  stats.id = "pentest-stats";
  page.appendChild(stats);
  const ctr = el("div", "wardrive-ctr");
  const bRow = el("div", "wdr-row");
  bRow.appendChild(el("span", "wdr-lbl", "bssid"));
  const bb = el("input", "wdr-inp");
  bb.id = "pentest-bssid";
  bb.placeholder = "AA:BB:CC:DD:EE:FF";
  bRow.appendChild(bb);
  ctr.appendChild(bRow);
  const eRow = el("div", "wdr-row");
  eRow.appendChild(el("span", "wdr-lbl", "essid"));
  const ee = el("input", "wdr-inp");
  ee.id = "pentest-essid";
  ee.placeholder = "network name (optional)";
  eRow.appendChild(ee);
  ctr.appendChild(eRow);
  const cRow = el("div", "wdr-row");
  cRow.appendChild(el("span", "wdr-lbl", "ch"));
  const ch = el("input", "wdr-inp wdr-sm");
  ch.id = "pentest-ch";
  ch.value = "6";
  ch.inputMode = "numeric";
  cRow.appendChild(ch);
  ctr.appendChild(cRow);
  const bar = el("div", "re-bar");
  const start = el("button", "big-btn run", "▶ GO");
  start.id = "pentest-start";
  start.onclick = () => pentestStart();
  const stop = el("button", "big-btn stop", "■ ABORT");
  stop.id = "pentest-stop";
  stop.onclick = async () => { try { await fetch("/api/apent/stop", { method: "POST" }); } catch (e) {} };
  bar.append(start, stop);
  ctr.appendChild(bar);
  page.appendChild(ctr);
  const lHead = el("div", "re-tabs");
  lHead.appendChild(el("span", "ra-sub", "MISSION LOG"));
  page.appendChild(lHead);
  const log = el("div", "re-console");
  log.id = "pentest-log";
  page.appendChild(log);
  c.appendChild(page);
  const tick = async () => {
    if (!pentestPageOpen) return;
    try { pentestRender(await fetch("/api/apent/status").then(r => r.json())); } catch (e) {}
  };
  pentestTimer = setInterval(tick, 2500);
  tick();
}

function pentestRender(st) {
  const stBox = document.getElementById("pentest-stats");
  if (stBox) {
    stBox.innerHTML = "";
    const phaseCol = st.running ? "ok" : (st.phase === "cracked" ? "ok" : "idle");
    [
      ["phase", st.phase || "idle", phaseCol],
      ["iface", st.iface || "—", ""],
      ["target", st.bssid || "—", ""],
      ["chan", st.channel != null ? st.channel : "—", ""],
      ["runtime", st.runtime ? st.runtime + "s" : "—", ""],
    ].forEach(([k, v, cls]) => {
      const cell = el("div", "re-stat");
      cell.append(el("span", "re-stat-lab", k), el("span", "re-stat-val" + (cls ? " " + cls : ""), v));
      stBox.appendChild(cell);
    });
    if (st.handshake) {
      const hs = el("div", "re-stat");
      hs.appendChild(el("span", "re-stat-lab", "handshake"));
      hs.appendChild(el("span", "re-stat-val ok", "GOT IT"));
      stBox.appendChild(hs);
    }
    if (st.key) {
      const kw = el("div", "re-stat");
      kw.appendChild(el("span", "re-stat-lab", "KEY"));
      kw.appendChild(el("span", "re-stat-val ok", st.key));
      stBox.appendChild(kw);
    }
    if (st.decrypted != null) {
      const dd = el("div", "re-stat");
      dd.appendChild(el("span", "re-stat-lab", "decrypted"));
      dd.appendChild(el("span", "re-stat-val" + (st.decrypted ? " ok" : ""), st.decrypted + " pkt"));
      stBox.appendChild(dd);
    }
  }
  const sbtn = document.getElementById("pentest-start");
  if (sbtn) sbtn.disabled = st.running;
  const log = document.getElementById("pentest-log");
  if (log) {
    log.innerHTML = "";
    const rows = st.log || [];
    if (!rows.length) log.appendChild(el("div", "lg-ln idle", "no mission yet."));
    rows.forEach(e2 => {
      const t = new Date(e2.t * 1000).toLocaleTimeString();
      log.appendChild(el("div", "lg-ln" + (e2.m.indexOf("KEY FOUND") >= 0 ? " ok" : ""), t + "  " + e2.m));
    });
    log.scrollTop = log.scrollHeight;
  }
}

async function pentestStart() {
  const bssid = document.getElementById("pentest-bssid").value;
  const essid = document.getElementById("pentest-essid").value;
  const ch = document.getElementById("pentest-ch").value;
  const sbtn = document.getElementById("pentest-start");
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = "arming…"; }
  try {
    const r = await fetch("/api/apent/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bssid, essid, channel: ch }),
    }).then(r => r.json());
    if (sbtn) {
      sbtn.textContent = r.ok ? "▶ GO" : "failed: " + (r.msg || "?");
      setTimeout(() => { if (sbtn) sbtn.textContent = "▶ GO"; }, 3500);
    }
  } catch (e) { if (sbtn) { sbtn.textContent = "▶ GO"; sbtn.disabled = false; } }
}

function leavePentest() {
  pentestPageOpen = false;
  if (pentestTimer) { clearInterval(pentestTimer); pentestTimer = null; }
}

/* ================= boot splash ================= */

// Boot animation is managed by startup.js.


initTelemetry();
