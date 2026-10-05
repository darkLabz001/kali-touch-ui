/* Offline games and touchscreen social browser launchers. */
(() => {
  let dispose = null;
  window.leaveEntertainment = () => { if (dispose) dispose(); dispose = null; };

  function gamePage(title, subtitle) {
    leaveEntertainment();
    const content = document.getElementById('content');
    content.replaceChildren(); content.scrollTop = 0;
    const page = el('div', 'ent-page');
    const head = el('div', 'ent-head');
    const heading = el('div');
    heading.append(el('h2', null, title), el('p', 'ent-note', subtitle));
    head.appendChild(heading); page.appendChild(head); content.appendChild(page);
    const status = el('div', 'ent-status'); status.setAttribute('role', 'status');
    return { page, head, status };
  }

  function storedBest(key, value) {
    try {
      const best = Number(localStorage.getItem(key)) || 0;
      if (value !== undefined && value > best) localStorage.setItem(key, String(value));
      return Math.max(best, value || 0);
    } catch (_) { return value || 0; }
  }

  window.showSnake = function showSnake() {
    const { page, head, status } = gamePage('Snake', 'Use the arrows or swipe the board. Collect dots and avoid the walls.');
    const restart = el('button', 'ent-button', 'New game'); head.appendChild(restart);
    const body = el('div', 'ent-game-layout');
    const canvas = el('canvas', 'ent-snake'); canvas.width = 432; canvas.height = 288;
    canvas.tabIndex = 0; canvas.setAttribute('aria-label', 'Snake game board. Use arrow keys or the direction buttons.');
    const side = el('div', 'ent-side');
    const score = el('div', 'ent-score');
    const play = el('button', 'ent-button primary', 'Start');
    const pad = el('div', 'ent-pad');
    side.append(score, status, play, pad); body.append(canvas, side); page.appendChild(body);
    const ctx = canvas.getContext('2d');
    let snake, direction, pending, food, points, running = false, ended = false, timer = null;
    const width = 18, height = 12, cell = 24;
    function spawnFood() {
      const empty = [];
      for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
        if (!snake.some(p => p.x === x && p.y === y)) empty.push({ x, y });
      }
      return empty.length ? empty[Math.floor(Math.random() * empty.length)] : null;
    }
    function draw() {
      ctx.fillStyle = '#07121a'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#12242d';
      for (let x = 0; x <= width; x++) { ctx.beginPath(); ctx.moveTo(x * cell, 0); ctx.lineTo(x * cell, canvas.height); ctx.stroke(); }
      for (let y = 0; y <= height; y++) { ctx.beginPath(); ctx.moveTo(0, y * cell); ctx.lineTo(canvas.width, y * cell); ctx.stroke(); }
      if (food) { ctx.fillStyle = '#ffcf5a'; ctx.beginPath(); ctx.arc(food.x * cell + 12, food.y * cell + 12, 7, 0, Math.PI * 2); ctx.fill(); }
      snake.forEach((p, i) => { ctx.fillStyle = i ? '#219e56' : '#7cffad'; ctx.fillRect(p.x * cell + 2, p.y * cell + 2, 20, 20); });
      score.textContent = 'Score ' + points + ' · Best ' + storedBest('touchui-snake-best', points);
    }
    function pause(message = 'Paused') {
      clearInterval(timer); timer = null; running = false;
      play.textContent = ended ? 'Play again' : 'Resume'; status.textContent = message;
    }
    function step() {
      direction = pending;
      const next = { x: snake[0].x + direction.x, y: snake[0].y + direction.y };
      const eats = food && next.x === food.x && next.y === food.y;
      const body = eats ? snake : snake.slice(0, -1);
      if (next.x < 0 || next.x >= width || next.y < 0 || next.y >= height || body.some(p => p.x === next.x && p.y === next.y)) {
        ended = true; pause('Game over · score ' + points); return;
      }
      snake.unshift(next);
      if (eats) { points += 10; food = spawnFood(); }
      else snake.pop();
      if (!food) { ended = true; pause('You filled the board!'); }
      draw();
    }
    function reset() {
      clearInterval(timer); timer = null; running = false; ended = false; points = 0;
      snake = [{ x: 4, y: 5 }, { x: 3, y: 5 }, { x: 2, y: 5 }];
      direction = pending = { x: 1, y: 0 }; food = spawnFood();
      play.textContent = 'Start'; status.textContent = 'Ready'; draw();
    }
    function toggle() {
      if (running) { pause(); return; }
      if (ended) reset();
      running = true; play.textContent = 'Pause'; status.textContent = 'Playing';
      timer = setInterval(step, 160);
    }
    function turn(x, y) {
      if (x === -direction.x && y === -direction.y) return;
      pending = { x, y };
    }
    for (const [label, name, x, y] of [['↑', 'Up', 0, -1], ['←', 'Left', -1, 0], ['↓', 'Down', 0, 1], ['→', 'Right', 1, 0]]) {
      const button = el('button', 'ent-button ent-dir ' + name.toLowerCase(), label);
      button.setAttribute('aria-label', name);
      button.onpointerdown = event => { event.preventDefault(); turn(x, y); };
      button.onclick = () => turn(x, y); pad.appendChild(button);
    }
    let start = null;
    canvas.onpointerdown = event => { start = { x: event.clientX, y: event.clientY }; canvas.setPointerCapture(event.pointerId); };
    canvas.onpointerup = event => {
      if (!start) return;
      const dx = event.clientX - start.x, dy = event.clientY - start.y; start = null;
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 12) return;
      if (Math.abs(dx) > Math.abs(dy)) turn(Math.sign(dx), 0); else turn(0, Math.sign(dy));
    };
    canvas.onpointercancel = () => { start = null; };
    const key = event => {
      const directions = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
      if (directions[event.key]) { event.preventDefault(); turn(...directions[event.key]); }
      else if (event.code === 'Space' && event.target === canvas) { event.preventDefault(); toggle(); }
    };
    const visibility = () => { if (document.hidden && running) pause(); };
    document.addEventListener('keydown', key); document.addEventListener('visibilitychange', visibility);
    restart.onclick = reset; play.onclick = toggle; reset();
    dispose = () => { clearInterval(timer); document.removeEventListener('keydown', key); document.removeEventListener('visibilitychange', visibility); };
  };

  window.showMemoryGame = function showMemoryGame() {
    const { page, head, status } = gamePage('Memory Match', 'Find all eight pairs. Tap two cards to reveal them.');
    const restart = el('button', 'ent-button', 'New game'); head.appendChild(restart);
    const body = el('div', 'ent-game-layout');
    const board = el('div', 'ent-memory');
    const side = el('div', 'ent-side'); const score = el('div', 'ent-score');
    side.append(score, status); body.append(board, side); page.appendChild(body);
    let cards, open, matches, moves, locked, timer;
    function renderScore() { score.textContent = 'Pairs ' + matches + '/8 · Moves ' + moves; }
    function flip(index) {
      const card = cards[index];
      if (locked || card.matched || open.includes(index)) return;
      card.button.textContent = card.symbol; card.button.classList.add('revealed');
      card.button.setAttribute('aria-label', 'Card ' + (index + 1) + ': ' + card.symbol); open.push(index);
      if (open.length !== 2) return;
      moves++; renderScore();
      const a = cards[open[0]], b = cards[open[1]];
      if (a.symbol === b.symbol) {
        for (const item of [a, b]) { item.matched = true; item.button.disabled = true; item.button.classList.add('matched'); }
        matches++; open = []; renderScore(); status.textContent = matches === 8 ? 'All pairs found in ' + moves + ' moves!' : 'Pair found!';
      } else {
        locked = true; status.textContent = 'Try another pair';
        timer = setTimeout(() => {
          for (const index of open) { const item = cards[index]; item.button.textContent = '?'; item.button.classList.remove('revealed'); item.button.setAttribute('aria-label', 'Card ' + (index + 1) + ', face down'); }
          open = []; locked = false;
        }, 700);
      }
    }
    function reset() {
      clearTimeout(timer); board.replaceChildren(); open = []; matches = 0; moves = 0; locked = false;
      const symbols = [...'ABCDEFGH', ...'ABCDEFGH'];
      for (let i = symbols.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [symbols[i], symbols[j]] = [symbols[j], symbols[i]]; }
      cards = symbols.map((symbol, index) => {
        const button = el('button', 'ent-memory-card', '?'); button.dataset.card = index;
        button.setAttribute('aria-label', 'Card ' + (index + 1) + ', face down'); button.onclick = () => flip(index); board.appendChild(button);
        return { symbol, button, matched: false };
      });
      renderScore(); status.textContent = 'Ready';
    }
    restart.onclick = reset; reset(); dispose = () => clearTimeout(timer);
  };

  window.showSocial = function showSocial(site, title) {
    const { page, head, status } = gamePage(title, 'Internet required. Use Back to Kali in the browser toolbar to return.');
    const open = el('button', 'ent-button primary', 'Open ' + title);
    const note = el('p', 'ent-note', 'Sign in on the official website. Your browser session is saved on this device.');
    page.append(note, open, status);
    open.onclick = async () => {
      open.disabled = true; status.textContent = 'Opening browser…';
      try {
        if (!['127.0.0.1', 'localhost'].includes(location.hostname)) throw new Error('Open Social on the device touchscreen.');
        const response = await fetch('http://127.0.0.1:8082/api/entertainment/open', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ site }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Unable to open browser');
        status.textContent = 'Browser opened on the device. Use its keyboard button to type.';
      } catch (error) { status.textContent = error.message === 'Failed to fetch' ? 'Social launcher is unavailable. Check the touchui-entertainment service.' : error.message; }
      finally { open.disabled = false; }
    };
  };
})();
