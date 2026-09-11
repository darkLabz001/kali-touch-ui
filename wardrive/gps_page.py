#!/usr/bin/env python3
"""The phone-facing GPS page, built to survive iOS backgrounding.

Safari suspends a backgrounded tab: timers stop, `watchPosition` callbacks
stop, and the wardriver's fix silently goes stale while the user is looking at
maps or music. Nothing in a web page can fully prevent that -- only an app with
a location background mode can (see gps_nmea.py) -- but four things together
push it a long way:

  * a Screen Wake Lock, so the phone does not auto-lock while it is sitting in
    a cradle streaming position;
  * a looping silent audio element, which puts the tab on the media playback
    path and keeps it running when another app comes to the front;
  * a watchdog that notices `watchPosition` has gone quiet and restarts it,
    because iOS often kills the watch without firing the error callback;
  * an armed flag in localStorage plus re-arming on every visibility/pageshow
    event, so returning to the tab (or a reload, or Safari discarding and
    restoring it) resumes streaming without the user pressing anything.

The result is a feed that stops only when STOP is pressed, rather than
whenever the screen changes.
"""

import base64
import struct

# Queue depth on the phone. At 1Hz this is ~5 minutes of driving held across a
# WiFi dropout, which is more than enough to cover losing the laptop's hotspot
# at a junction and picking it up again.
QUEUE_LIMIT = 300


def _silent_wav(seconds: float = 0.5, rate: int = 8000) -> str:
    """A valid silent mono WAV as a data: URI.

    It has to be real decodable audio, not an empty file: iOS only keeps the
    page alive if the media element is actually playing.
    """
    frames = int(rate * seconds)
    data = b'\x00\x00' * frames          # 16-bit PCM silence
    header = b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE'
    header += b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16)
    header += b'data' + struct.pack('<I', len(data))
    return 'data:audio/wav;base64,' + base64.b64encode(header + data).decode()


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>NIGHTRIDER GPS</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    margin: 0; padding: env(safe-area-inset-top) 16px env(safe-area-inset-bottom);
    background: #05060a; color: #00ff41;
    font: 16px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
    text-align: center; min-height: 100vh;
    display: flex; flex-direction: column; justify-content: center; gap: 14px;
  }
  h1 { font-size: 1.1rem; letter-spacing: .35em; margin: 0; color: #00a32a; }
  button {
    width: 100%; padding: 22px; font: inherit; font-weight: 700;
    letter-spacing: .2em; border: 2px solid #00ff41; border-radius: 10px;
    background: #0d2b17; color: #00ff41; touch-action: manipulation;
  }
  button:active { background: #00ff41; color: #05060a; }
  button.stop { border-color: #ff4d5e; background: #3d0f14; color: #ff4d5e; }
  #state { font-size: 1.4rem; font-weight: 700; letter-spacing: .2em; }
  #coords { font-size: 1.05rem; line-height: 1.7; word-break: break-all; }
  #detail, #warn { font-size: .78rem; color: #1f6b3a; line-height: 1.6; }
  #warn { color: #d4ff00; }
  .off { color: #7a3038; }
  .on  { color: #00ff41; }
  .bad { color: #ff4d5e; }
  .pills { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap;
           font-size: .68rem; letter-spacing: .1em; }
  .pill { border: 1px solid #12351f; border-radius: 999px; padding: 3px 9px; }
</style>
</head>
<body>
  <h1>NIGHTRIDER</h1>
  <div id="state" class="off">STANDBY</div>
  <div id="coords">no fix</div>
  <div class="pills">
    <span class="pill" id="p_wake">screen —</span>
    <span class="pill" id="p_audio">keepalive —</span>
    <span class="pill" id="p_queue">queue 0</span>
    <span class="pill" id="p_sent">sent 0</span>
  </div>
  <button id="go">START</button>
  <button id="halt" class="stop" hidden>STOP</button>
  <div id="warn"></div>
  <div id="detail">
    Keep this tab open. Streaming continues while you use other apps, and stops
    only when you press STOP.
  </div>
  <audio id="ka" loop playsinline preload="auto" src="__SILENT_WAV__"></audio>

<script>
"use strict";
var QUEUE_LIMIT = __QUEUE_LIMIT__;

var S = {
  armed: false,
  watchId: null,
  wakeLock: null,
  lastFixAt: 0,      // Date.now() of the most recent position callback
  sent: 0,
  queue: [],         // fixes not yet acknowledged by the wardriver
  lastCoords: null,
  flushing: false
};

var $ = function (id) { return document.getElementById(id); };

/* ---------- transport -------------------------------------------------- */

/* Fixes are queued and flushed rather than fired individually, so a dropout
   on the link to the laptop delays the track instead of punching holes in it.
   Each fix carries the phone's own timestamp; the wardriver maps those onto
   its clock, so a batch that arrives late is still laid down at the right
   points along the track. */
function enqueue(c, when) {
  S.queue.push({
    lat: c.latitude, lon: c.longitude,
    acc: c.accuracy == null ? null : Math.round(c.accuracy * 10) / 10,
    alt: c.altitude == null ? null : Math.round(c.altitude * 10) / 10,
    spd: c.speed == null ? null : Math.round(c.speed * 100) / 100,
    hdg: c.heading == null ? null : Math.round(c.heading),
    t: when
  });
  if (S.queue.length > QUEUE_LIMIT) S.queue.splice(0, S.queue.length - QUEUE_LIMIT);
  flush();
}

function flush() {
  if (S.flushing || !S.queue.length) return;
  S.flushing = true;
  var batch = S.queue.slice();
  fetch('/gps/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ armed: S.armed, fixes: batch }),
    keepalive: true                    // survives the page being hidden
  }).then(function (r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    S.queue.splice(0, batch.length);   // only drop what was accepted
    S.sent += batch.length;
    S.flushing = false;
    paint();
    if (S.queue.length) flush();
  }).catch(function () {
    // Leave the batch queued; the next fix or heartbeat retries it.
    S.flushing = false;
    paint();
  });
}

function tell(path) {
  fetch(path, { keepalive: true }).catch(function () {});
}

/* ---------- keepalive -------------------------------------------------- */

/* Wake Lock stops the phone auto-locking mid-drive. iOS drops the lock on
   every visibility change, so it is re-requested rather than assumed held. */
function acquireWake() {
  if (!('wakeLock' in navigator) || !S.armed) return;
  if (document.visibilityState !== 'visible') return;
  navigator.wakeLock.request('screen').then(function (lock) {
    S.wakeLock = lock;
    lock.addEventListener('release', function () { S.wakeLock = null; paint(); });
    paint();
  }).catch(function () { S.wakeLock = null; paint(); });
}

/* Silent looping audio keeps the tab on the media path, which is what stops
   iOS freezing its timers the moment another app takes the foreground. It
   needs a user gesture to start, so failure here is reported rather than
   swallowed -- without it, backgrounding will cut the feed. */
function startAudio() {
  var a = $('ka');
  a.volume = 0;
  var p = a.play();
  if (p && p.catch) p.catch(function () { paint(); });
}

function stopAudio() {
  var a = $('ka');
  a.pause();
  try { a.currentTime = 0; } catch (e) {}
}

/* ---------- geolocation ------------------------------------------------ */

function onPosition(pos) {
  S.lastFixAt = Date.now();
  S.lastCoords = pos.coords;
  enqueue(pos.coords, pos.timestamp || Date.now());
  paint();
}

function onPosError(err) {
  if (err.code === 1) {          // PERMISSION_DENIED is terminal
    disarm();
    $('warn').textContent = 'Location permission denied. Allow it in Settings '
      + '> Safari > Location, then press START again.';
    return;
  }
  $('warn').textContent = 'GPS: ' + err.message;
}

function startWatch() {
  stopWatch();
  var opts = { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 };
  navigator.geolocation.getCurrentPosition(onPosition, onPosError, opts);
  S.watchId = navigator.geolocation.watchPosition(onPosition, onPosError, opts);
}

function stopWatch() {
  if (S.watchId !== null) {
    navigator.geolocation.clearWatch(S.watchId);
    S.watchId = null;
  }
}

/* ---------- arm / disarm ----------------------------------------------- */

function arm(fromGesture) {
  S.armed = true;
  localStorage.setItem('wd_armed', '1');
  $('warn').textContent = '';
  startWatch();
  acquireWake();
  if (fromGesture) startAudio();
  paint();
}

function disarm() {
  S.armed = false;
  localStorage.removeItem('wd_armed');
  stopWatch();
  stopAudio();
  if (S.wakeLock) { try { S.wakeLock.release(); } catch (e) {} S.wakeLock = null; }
  flush();                       // hand over anything still queued
  tell('/gps/stop');
  paint();
}

/* ---------- watchdog --------------------------------------------------- */

/* iOS routinely stops delivering positions without ever calling the error
   handler, so silence is the only signal that the watch has died. Restarting
   it is cheap and is what makes the feed survive a trip through another app. */
var STALE_MS = 15000;

setInterval(function () {
  if (!S.armed) return;
  var quiet = Date.now() - S.lastFixAt;
  if (S.lastFixAt && quiet > STALE_MS) startWatch();
  if (!S.wakeLock) acquireWake();
  if ($('ka').paused && document.visibilityState === 'visible') startAudio();
  flush();
  // Heartbeat: lets the wardriver distinguish "phone still here, not moving"
  // from "feed died", which look identical from a stale fix alone.
  tell('/gps/ping?armed=' + (S.armed ? 1 : 0) + '&q=' + S.queue.length);
  paint();
}, 5000);

/* Any return to the foreground is a chance to repair the feed. */
['visibilitychange', 'pageshow', 'focus', 'online', 'resume'].forEach(function (ev) {
  window.addEventListener(ev, function () {
    if (!S.armed) return;
    if (document.visibilityState === 'visible') {
      startWatch();
      acquireWake();
      startAudio();
    }
    flush();
    paint();
  });
});

window.addEventListener('pagehide', function () { flush(); });

/* ---------- ui --------------------------------------------------------- */

function paint() {
  var st = $('state');
  if (!S.armed) {
    st.textContent = 'STANDBY'; st.className = 'off';
  } else if (S.lastFixAt && Date.now() - S.lastFixAt < STALE_MS) {
    st.textContent = 'STREAMING'; st.className = 'on';
  } else {
    st.textContent = 'ACQUIRING'; st.className = 'bad';
  }

  var c = S.lastCoords;
  $('coords').innerHTML = c
    ? c.latitude.toFixed(6) + '<br>' + c.longitude.toFixed(6)
      + '<br><span style="color:#1f6b3a">&plusmn;' + Math.round(c.accuracy) + 'm'
      + (c.speed != null ? '  ' + Math.round(c.speed * 2.237) + 'mph' : '') + '</span>'
    : 'no fix';

  $('p_wake').textContent = 'screen ' + (S.wakeLock ? 'held' : 'free');
  $('p_wake').className = 'pill ' + (S.wakeLock ? 'on' : 'off');
  var alive = !$('ka').paused;
  $('p_audio').textContent = 'keepalive ' + (alive ? 'on' : 'off');
  $('p_audio').className = 'pill ' + (alive ? 'on' : 'bad');
  $('p_queue').textContent = 'queue ' + S.queue.length;
  $('p_queue').className = 'pill ' + (S.queue.length ? 'bad' : 'off');
  $('p_sent').textContent = 'sent ' + S.sent;

  $('go').hidden = S.armed;
  $('halt').hidden = !S.armed;

  if (S.armed && !alive) {
    $('warn').textContent = 'Tap START again to enable background keepalive '
      + '— without it iOS will pause the feed when you switch apps.';
  }
}

$('go').addEventListener('click', function () { arm(true); });
$('halt').addEventListener('click', function () { disarm(); });

/* Safari discards and restores background tabs. If the session was armed,
   come back up streaming instead of waiting to be pressed again. */
if (localStorage.getItem('wd_armed') === '1') {
  arm(false);                    // audio needs a gesture; paint() will say so
}
paint();
</script>
</body>
</html>
"""


def render_page() -> bytes:
    return (_PAGE
            .replace('__SILENT_WAV__', _silent_wav())
            .replace('__QUEUE_LIMIT__', str(QUEUE_LIMIT))
            .encode('utf-8'))
