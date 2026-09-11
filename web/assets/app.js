const state = { data: null, section: null, tool: null, running: false, evtSource: null, wordlists: [], terminal: false, termSend: null };

const icons = {
  radar: "◉", search: "◎", globe: "◍", key: "❋", wifi: "✱",
  lock: "▣", shield: "◆", tool: "⚒", root: "⚑", settings: "⚙",
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function mkStatCell(lab, val) {
  const b = el("div", "re-stat");
  b.append(el("span", "re-stat-lab", lab), el("span", "re-stat-val", val));
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
      if (i.ssid) { miss = 0; lastNet = i.ssid + " · " + (i.ip || "--"); }
      else if (++miss > 3) { lastNet = "no-wifi · " + (i.ip || "--"); }
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

async function load() {
  state.data = await api("/api/tools");
  try { state.wordlists = (await api("/api/wordlists")).wordlists || []; } catch (e) { state.wordlists = []; }
  showHome();
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
  grid.appendChild(mkc("self-built", "◈", "Custom Tools", "3 apps", "acc-cy", () => showCustomTools()));
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

function showCustomTools() {
  state.section = null; state.tool = null; state.settings = false; state.terminal = false; state.running = false;
  const c = document.querySelector(".content");
  document.querySelector(".btn-back").style.display = "flex";
  c.innerHTML = "";
  const head = el("div", "section-head");
  head.appendChild(el("h2", null, "◈ Custom Tools"));
  head.appendChild(el("div", "hint", "3 apps · self-built"));
  c.appendChild(head);
  const list = el("div", "tool-list");
  const apps = [
    ["◉", "Recon — PineAP", "live AP scan · signal graph · deauth", "#39ff14", showRecon],
    ["✕", "Handshake Hunter", "capture handshakes · crack with hashcat", "#00d9ff", showHunter],
    ["◎", "WiFi Radar", "live radar sweep of scanned APs", "#ffc93d", showRadar],
  ];
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
  const otaMeta = el("div", "ota-meta", "checking…");
  const otaBtns = el("div", "ota-btns");
  const otaCheck = el("button", "set-btn", "⟳ Check");
  const otaUpd = el("button", "set-btn warn", "⬇ Update");
  otaUpd.disabled = true;
  otaBtns.appendChild(otaCheck);
  otaBtns.appendChild(otaUpd);
  const otaLog = el("div", "ota-log");
  otaLog.style.display = "none";
  otaCard.appendChild(otaMeta);
  otaCard.appendChild(otaBtns);
  otaCard.appendChild(otaLog);
  page.appendChild(otaCard);
  c.appendChild(page);

  scanBtn.onclick = () => doWifiScan(scanBtn, netList, statusRow);
  otaCheck.onclick = () => refreshOta(otaMeta, otaLog, otaUpd, otaCheck);
  otaUpd.onclick = () => otaRun(otaMeta, otaLog, otaUpd, otaCheck);
  refreshOta(otaMeta, otaLog, otaUpd, otaCheck);

  Promise.all([api("/api/network"), api("/api/wifi/scan")]).then(([net, scan]) => {
    renderNetworkInfo(infoBody, net.info);
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

function refreshOta(meta, logBox, updBtn, chkBtn) {
  api("/api/ota/status").then(s => {
    if (!s.installed) {
      meta.textContent = "OTA not enabled — reinstall from GitHub first.";
      updBtn.disabled = true;
      return;
    }
    const st = s.up_to_date ? "up to date" : "update available";
    meta.textContent = "v" + (s.version || "?") + " · local " + s.local_short + " · latest " + (s.remote_short || "—") + " · " + st;
    updBtn.disabled = s.busy || s.up_to_date;
    chkBtn.disabled = s.busy;
    if (s.busy) {
      showOtaLog(logBox, s.log);
      setTimeout(() => refreshOta(meta, logBox, updBtn, chkBtn), 2000);
    }
  }).catch(() => {
    meta.textContent = "backend unreachable";
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

function otaRun(meta, logBox, updBtn, chkBtn) {
  if (!confirm("Pull the latest version from GitHub and restart the device UI?")) return;
  updBtn.disabled = true;
  chkBtn.disabled = true;
  api("/api/ota/update", "POST").then(r => {
    const t = setInterval(() => {
      api("/api/ota/status").then(s => {
        if (logBox.style.display === "none" && (s.log || "").trim()) showOtaLog(logBox, s.log);
        if (!s.busy) {
          clearInterval(t);
          if (logBox.style.display === "none") showOtaLog(logBox, s.log);
          logBox.appendChild(el("div", "ota-line" + (r.ok ? " ok" : " err"), (r.ok ? "✓ " : "✗ ") + (r.msg || "done")));
          updBtn.disabled = false;
          chkBtn.disabled = false;
          meta.textContent = "v" + (s.version || "?") + " · local " + s.local_short + " · latest " + (s.remote_short || "—") + (s.up_to_date ? " · up to date" : " · update available");
        }
      }).catch(() => {});
    }, 2500);
  }).catch(e => {
    meta.textContent = "update failed: " + e;
    updBtn.disabled = false;
    chkBtn.disabled = false;
  });
}

function renderNetworkInfo(body, info) {
  body.innerHTML = "";
  const rows = [
    ["Hostname", info.hostname],
    ["OS", info.os],
    ["IP", info.ip || "—"],
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

  const row = el("div", "run-row");
  const runBtn = el("button", "big-btn run", "▶ RUN");
  const stopBtn = el("button", "big-btn stop", "■ STOP");
  stopBtn.disabled = true;
  runBtn.onclick = () => startRun(tool, runBtn, stopBtn);
  stopBtn.onclick = () => stopRun(stopBtn);
  row.appendChild(runBtn);
  row.appendChild(stopBtn);
  page.appendChild(row);

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
    tFeed(text);
    out.scrollTop = out.scrollHeight;
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
  rst.onclick = () => termConnect(termInit && termInit.cmd);
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
    if (v.length === 0) return;
    inp.value = "";
    api("/api/term/input", "POST", { data: v + "\r" }).catch(() => {});
  };
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); send(); }
  });
  go.onclick = send;
  state.termSend = send;
  setTimeout(() => inp.focus(), 150);
  termConnect(termInit && termInit.cmd);
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
let reconDirty = false;
let reconSeries = {};
let reconTrend = {};
const RECON_COLORS = ["#39ff14", "#00d9ff", "#ffb000", "#ff3bd3", "#ffe000", "#4cf0c0"];

function reconColor(bssid) {
  const keys = Object.keys(reconSeries);
  const i = keys.indexOf(bssid);
  if (reconPageOpen && i >= 0) return RECON_COLORS[i % RECON_COLORS.length];
  return "#39ff14";
}

function reconSample() {
  const cur = {};
  for (const ap of reconLast.d.aps) cur[ap.bssid] = parseInt(ap.power, 10);
  for (const b of Object.keys(cur)) if (!(b in reconSeries)) reconSeries[b] = [];
  for (const k of Object.keys(reconSeries)) {
    const s = reconSeries[k];
    const v = (k in cur) ? cur[k] : NaN;
    if (!(s.length && Number.isNaN(s[s.length - 1]) && Number.isNaN(v))) s.push(v);
    if (s.length > 60) s.shift();
  }
  reconTrend = {};
  for (const k of Object.keys(reconSeries)) {
    const s = reconSeries[k];
    if (s.length < 2 || Number.isNaN(s[s.length - 1]) || Number.isNaN(s[s.length - 2])) {
      reconTrend[k] = "flat";
    } else {
      const d = s[s.length - 1] - s[s.length - 2];
      reconTrend[k] = d > 1.5 ? "up" : (d < -1.5 ? "down" : "flat");
    }
  }
  renderReconGraph();
  renderReconLegend();
  renderReconChstrip();
}

function renderReconGraph() {
  const cv = document.getElementById("re-graph");
  if (!cv) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth || 450;
  const h = cv.clientHeight || 150;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, "#050b08");
  g.addColorStop(1, "#020604");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  const L = 34, R = 6, T = 12, B = 8;
  const pw = w - L - R, ph = h - T - B;
  const yTop = -30, yBot = -95;
  const Y = (v) => T + ((yTop - v) / (yTop - yBot)) * ph;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let v = -40; v >= -90; v -= 10) {
    ctx.strokeStyle = "rgba(20,90,68,.30)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(L, Y(v));
    ctx.lineTo(w - R, Y(v));
    ctx.stroke();
    ctx.fillStyle = "#3a8a6e";
    ctx.font = "8px monospace";
    ctx.fillText(String(v), L - 5, Y(v));
  }
  ctx.fillStyle = "#1d5c47";
  ctx.textAlign = "left";
  for (let k = 1; k <= 5; k++) {
    const x = L + (pw * k) / 6;
    ctx.strokeStyle = "rgba(20,90,68,.12)";
    ctx.beginPath();
    ctx.moveTo(x, T);
    ctx.lineTo(x, T + ph);
    ctx.stroke();
  }
  ctx.strokeStyle = "#0f4a36";
  ctx.lineWidth = 1;
  ctx.strokeRect(L, T, pw, ph);
  ctx.fillStyle = "#1f6b50";
  ctx.font = "8px monospace";
  ctx.fillText("RSSI " + yTop + ".." + yBot + " dBm", L + 6, T - 5);
  ctx.fillStyle = "#2f6f5a";
  ctx.textAlign = "right";
  ctx.fillText("~60s", w - R - 2, T - 5);
  const keys = Object.keys(reconSeries);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  keys.forEach((k, i) => {
    const pts = reconSeries[k];
    const len = pts.length;
    if (len < 2) return;
    const path = new Path2D();
    let started = false;
    for (let j = 0; j < len; j++) {
      const v = pts[j];
      if (Number.isNaN(v)) { started = false; continue; }
      const x = L + (pw * (j + 1)) / (len + 1);
      const y = Y(v);
      if (!started) { path.moveTo(x, y); started = true; }
      else path.lineTo(x, y);
    }
    const col = RECON_COLORS[i % RECON_COLORS.length];
    ctx.strokeStyle = col;
    ctx.globalAlpha = 0.16;
    ctx.lineWidth = 4.5;
    ctx.stroke(path);
    ctx.globalAlpha = 1;
    ctx.lineWidth = 1.7;
    ctx.stroke(path);
    const last = pts[len - 1];
    if (!Number.isNaN(last)) {
      const x = L + (pw * len) / (len + 1);
      const y = Y(last);
      ctx.shadowColor = col;
      ctx.shadowBlur = 6;
      ctx.fillStyle = "#d7ffe9";
      ctx.beginPath();
      ctx.arc(x, y, 2.4, 0, 7);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  });
  ctx.globalAlpha = 1;
}

function renderReconLegend() {
  const leg = document.getElementById("re-legend");
  if (!leg) return;
  leg.innerHTML = "";
  const top = reconLast.d.aps.slice()
    .sort((a, b) => (parseInt(b.power, 10) || -100) - (parseInt(a.power, 10) || -100))
    .slice(0, 4);
  for (const ap of top) {
    const item = el("span", "re-leg");
    const dot = el("span", "re-dot");
    dot.style.background = reconColor(ap.bssid);
    const name = ap.essid ? ap.essid : "hiddenssid";
    const st = document.createElement("strong");
    st.textContent = name.slice(0, 12) + " ";
    const val = el("span", null, (ap.power || "??") + " dBm ");
    const tr = reconTrend[ap.bssid] || "flat";
    const arrow = el("span", "re-tr", tr === "up" ? "▲" : tr === "down" ? "▼" : "—");
    arrow.style.color = tr === "up" ? "#39ff14" : tr === "down" ? "#ff4d4d" : "#5f8a7a";
    item.append(dot, st, val, arrow);
    leg.appendChild(item);
  }
}

function renderReconChstrip() {
  const cv = document.getElementById("re-chstrip");
  if (!cv) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = cv.clientWidth || 450;
  const h = 20;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const counts = {};
  for (const ap of reconLast.d.aps) {
    const ch = parseInt(ap.channel, 10);
    if (!Number.isNaN(ch)) counts[ch] = (counts[ch] || 0) + 1;
  }
  const mid = w * 0.45;
  const x24 = (ch) => 2 + ((ch - 1) / 14) * (mid - 4);
  const x5 = (ch) => mid + ((ch - 36) / (165 - 36)) * (w - mid - 4);
  ctx.font = "7px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillStyle = "#1c4a3a";
  ctx.fillText("2.4GHz", mid / 2, 0);
  ctx.fillText("5GHz", mid + (w - mid) / 2, 0);
  ctx.fillStyle = "#2f6f5a";
  for (const ch of [1, 6, 11, 36, 100, 149, 165]) {
    ctx.fillText(String(ch), ch <= 14 ? x24(ch) : x5(ch), 17);
  }
  for (const ch in counts) {
    const c = parseInt(ch, 10);
    const n = counts[ch];
    const x = c <= 14 ? x24(c) : x5(c);
    const bh = Math.min(12, 3 + n * 2.4);
    ctx.fillStyle = "#39ff14";
    ctx.fillRect(x - 1.5, 2 + (12 - bh), 3, bh);
  }
}

function leaveRecon() {
  if (reconTimer) { clearInterval(reconTimer); reconTimer = null; }
  reconPageOpen = false;
  reconOpen = null;
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

function reconRows(st, d) {
  const t = reconTab;
  const no = el("div", "re-empty", "no data yet");
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
      row.onclick = () => { reconOpen = reconOpen === ap.bssid ? null : ap.bssid; reconDirty = true; };
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

function reconDo(st, d, lg) {
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
  const rows = reconRows(st, d);
  table.innerHTML = "";
  for (const r of rows) table.appendChild(r);
  if (log) { log.textContent = lg.log.trim().split("\n").slice(-24).join("\n"); log.scrollTop = 1e9; }
  if (reconDirty) { reconDirty = false; }
}

function showRecon() {
  state.terminal = false; state.settings = false; state.tool = null; state.section = null;
  state.running = false;
  document.querySelector(".btn-back").style.display = "flex";
  reconPageOpen = true;
  reconOpen = null;
  reconSeries = {};
  reconTrend = {};
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
  gwrap.appendChild(legend);
  const gcanvas = document.createElement("canvas");
  gcanvas.className = "re-graph";
  gcanvas.id = "re-graph";
  gwrap.appendChild(gcanvas);
  page.appendChild(gwrap);
  const chcanvas = document.createElement("canvas");
  chcanvas.className = "re-chstrip";
  chcanvas.id = "re-chstrip";
  page.appendChild(chcanvas);

  const stats = el("div", "re-stats");
  stats.id = "re-stats";
  page.appendChild(stats);

  const bar = el("div", "re-bar");
  const on = el("button", "big-btn run", "▶ SCAN ON");
  on.onclick = async () => {
    on.classList.add("busy"); on.textContent = "starting…";
    try {
      const r = await fetch("/api/recon/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const j = await r.json();
      hint.textContent = j.ok ? "scanning " + j.msg : "✗ " + j.msg;
    } catch (e) {}
    on.classList.remove("busy"); on.textContent = "▶ SCAN ON";
  };
  bar.appendChild(on);
  const off = el("button", "big-btn stop", "■ OFF");
  off.onclick = async () => {
    try { await fetch("/api/recon/stop", { method: "POST" }); } catch (e) {}
  };
  bar.appendChild(off);
  page.appendChild(bar);

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
  const tAP = el("button", "chip on", "▣ ACCESS POINTS");
  const tCL = el("button", "chip", "◈ CLIENTS");
  tAP.onclick = () => { reconTab = "aps"; tAP.classList.add("on"); tCL.classList.remove("on"); reconDo(reconLast.st, reconLast.d, reconLast.lg); };
  tCL.onclick = () => { reconTab = "clients"; tCL.classList.add("on"); tAP.classList.remove("on"); reconDo(reconLast.st, reconLast.d, reconLast.lg); };
  tabs.append(tAP, tCL);
  page.appendChild(tabs);

  const table = el("div", "re-table");
  table.id = "re-table";
  const logBox = el("div", "re-log");
  logBox.id = "re-log";
  page.appendChild(table);
  page.appendChild(logBox);

  c.appendChild(page);
  reconLast = { st: { running: false, iface: null, aps: 0, clients: 0 }, d: { aps: [], clients: [] }, lg: { log: "" } };
  reconDo(reconLast.st, reconLast.d, reconLast.lg);

  const poke = async () => {
    if (!reconPageOpen) return;
    try {
      const [st, d, lg] = await Promise.all([
        fetch("/api/recon/state").then(r => r.json()),
        fetch("/api/recon/data").then(r => r.json()),
        fetch("/api/recon/log").then(r => r.json()),
      ]);
      reconLast = { st, d, lg };
      reconDo(st, d, lg);
      reconSample();
    } catch (e) {}
  };
  reconTimer = setInterval(poke, 3000);
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
  try {
    const r = await fetch("/api/hs/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bssid: ap.bssid, essid: ap.essid, channel: parseInt(ap.channel, 10) || null }),
    });
    const j = await r.json();
    if (hint) hint.textContent = j.ok ? "▶ capturing " + j.msg + " — waiting for handshake" : "✗ " + j.msg;
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
  stats.append(
    mkStatCell("IFACE", st.iface ? "▣ " + st.iface : "○ none"),
    mkStatCell("TARGET", st.target ? st.target.slice(0, 15) : "—"),
    mkStatCell("CH", st.channel || "any"),
    mkStatCell("CAP", st.captures),
    mkStatCell("CRACK", st.cracking ? "● RUN" : "idle"),
  );
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

  const bar = el("div", "re-bar");
  const scan = el("button", "big-btn run", "▶ SCAN ENV");
  scan.onclick = () => hunterEnvScan();
  const stop = el("button", "big-btn stop", "■ STOP");
  stop.onclick = async () => {
    try { await fetch("/api/hs/stop", { method: "POST" }); } catch (e) {}
  };
  bar.append(scan, stop);
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

/* ================= boot splash ================= */

(function bootSplash() {
  const SPLASH_MS = 4200;
  const splash = document.getElementById("boot-splash");
  if (!splash) return;

  const stateKey = "kali-touch-splash-seen";
  const skipBtn = document.getElementById("boot-skip");
  const fill = document.getElementById("ds-fill");
  const status = document.getElementById("ds-status");
  const dots = document.getElementById("ds-bootdots");
  const statuses = [
    "booting wireless stack…",
    "arming monitor interface…",
    "scanning 2.4 / 5 GHz…",
    "raising site services…",
  ];
  let done = false;

  function reveal() {
    if (done) return;
    done = true;
    splash.classList.add("fade");
    try { sessionStorage.setItem(stateKey, "1"); } catch (e) {}
    setTimeout(() => splash.remove(), 850);
  }

  let seen = false;
  try { seen = sessionStorage.getItem(stateKey) === "1"; } catch (e) {}
  if (seen) {
    splash.style.display = "none";
    return;
  }

  if (skipBtn) skipBtn.addEventListener("pointerdown", reveal);
  const t0 = Date.now();
  const iv = setInterval(() => {
    const e = (Date.now() - t0) / SPLASH_MS;
    if (fill) fill.style.width = Math.min(100, Math.round(e * 112)) + "%";
    if (status) status.textContent = statuses[Math.min(statuses.length - 1, Math.floor((e / 0.85) * statuses.length))];
    if (dots) {
      const active = Math.min(5, Math.floor(e / 0.2) + 1);
      [...dots.children].forEach((c, i) => c.classList.toggle("on", i < active));
    }
    if (e >= 1) { clearInterval(iv); reveal(); }
  }, 80);
  document.addEventListener("pointerdown", () => { if (Date.now() - t0 > 900) reveal(); });
})();

initTelemetry();