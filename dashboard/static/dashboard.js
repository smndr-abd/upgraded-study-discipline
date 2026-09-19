const els = {
  streakValue: document.getElementById('streakValue'),
  longestValue: document.getElementById('longestValue'),
  todayFocusValue: document.getElementById('todayFocusValue'),
  todayGoalUnit: document.getElementById('todayGoalUnit'),
  todayDistractionValue: document.getElementById('todayDistractionValue'),
  progressFraction: document.getElementById('progressFraction'),
  progressFill: document.getElementById('progressFill'),
  chainGrid: document.getElementById('chainGrid'),
  chainLinks: document.getElementById('chainLinks'),
  breakdownList: document.getElementById('breakdownList'),
};

function fmtMinutes(seconds) {
  const m = Math.floor(seconds / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}

function levelForFocus(seconds, goalSeconds) {
  if (seconds <= 0) return 0;
  const frac = seconds / goalSeconds;
  if (frac < 0.34) return 1;
  if (frac < 0.85) return 2;
  return 3;
}

async function loadSummary() {
  const res = await fetch('/api/summary');
  const data = await res.json();

  els.streakValue.textContent = data.current_streak;
  els.longestValue.textContent = data.longest_streak;

  const focusSeconds = data.today.focus_seconds;
  const goalSeconds = data.goal_seconds;
  els.todayFocusValue.textContent = fmtMinutes(focusSeconds);
  els.todayGoalUnit.textContent = `of ${fmtMinutes(goalSeconds)} goal`;
  els.todayDistractionValue.textContent = fmtMinutes(data.today.distraction_seconds);

  const pct = Math.min(100, (focusSeconds / goalSeconds) * 100);
  els.progressFill.style.width = `${pct}%`;
  els.progressFraction.textContent = `${fmtMinutes(focusSeconds)} / ${fmtMinutes(goalSeconds)}`;

  return { goalSeconds };
}

async function loadChain(goalSeconds) {
  const res = await fetch('/api/history');
  const days = await res.json();

  els.chainGrid.innerHTML = '';
  const cellEls = [];

  for (const d of days) {
    const cell = document.createElement('div');
    if (d.is_future) {
      cell.className = 'chain-cell future';
    } else {
      const level = levelForFocus(d.focus_seconds, goalSeconds);
      cell.className = `chain-cell level-${level}`;
      cell.title = `${d.day} · ${fmtMinutes(d.focus_seconds)} focus${d.goal_met ? ' · goal met' : ''}`;
    }
    cell.dataset.day = d.day;
    cell.dataset.goalMet = d.goal_met ? '1' : '0';
    els.chainGrid.appendChild(cell);
    cellEls.push(cell);
  }

  drawChainLinks(cellEls, days);
}

function drawChainLinks(cellEls, days) {
  // Draw a connecting line between consecutive calendar days that both met
  // the goal — "the chain" — regardless of where they wrap in the grid.
  const svg = els.chainLinks;
  svg.innerHTML = '';

  const gridRect = els.chainGrid.getBoundingClientRect();

  const points = cellEls.map((cell) => {
    const r = cell.getBoundingClientRect();
    return {
      x: r.left - gridRect.left + r.width / 2,
      y: r.top - gridRect.top + r.height / 2,
    };
  });

  const ns = 'http://www.w3.org/2000/svg';
  for (let i = 0; i < days.length - 1; i++) {
    if (days[i].goal_met === true && days[i + 1].goal_met === true) {
      const line = document.createElementNS(ns, 'line');
      line.setAttribute('x1', points[i].x);
      line.setAttribute('y1', points[i].y);
      line.setAttribute('x2', points[i + 1].x);
      line.setAttribute('y2', points[i + 1].y);
      line.setAttribute('stroke', '#F2B84B');
      line.setAttribute('stroke-width', '2');
      line.setAttribute('stroke-linecap', 'round');
      svg.appendChild(line);
    }
  }
}

async function loadBreakdown() {
  const res = await fetch('/api/breakdown');
  const rows = await res.json();

  els.breakdownList.innerHTML = '';

  if (rows.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-note';
    empty.textContent = 'No sessions closed yet today — switch apps at least once for this to populate.';
    els.breakdownList.appendChild(empty);
    return;
  }

  const maxSeconds = Math.max(...rows.map(r => r.total_seconds));

  for (const row of rows) {
    const el = document.createElement('div');
    el.className = 'breakdown-row';
    const pct = Math.max(4, (row.total_seconds / maxSeconds) * 100);
    el.innerHTML = `
      <span class="breakdown-name">${row.app_name}</span>
      <span class="breakdown-bar-track"><span class="breakdown-bar-fill ${row.category}" style="width:${pct}%"></span></span>
      <span class="breakdown-time">${fmtMinutes(row.total_seconds)}</span>
    `;
    els.breakdownList.appendChild(el);
  }
}

async function refreshAll() {
  const { goalSeconds } = await loadSummary();
  await loadChain(goalSeconds);
  await loadBreakdown();
}

window.addEventListener('resize', () => {
  // Recompute link positions if the window resizes (grid may reflow)
  const cells = Array.from(els.chainGrid.children);
  const days = cells.map(c => ({ goal_met: c.dataset.goalMet === '1' }));
  if (cells.length) drawChainLinks(cells, days);
});

refreshAll();
setInterval(refreshAll, 30000); // keep it live without making a manual refresh
