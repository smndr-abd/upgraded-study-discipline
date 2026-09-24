const REFRESH_MS = 5000; // matches the tracker's own poll interval

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

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

// ---------------------------------------------------------------------
// Animated number counting. Keyed so repeated calls on the same element
// cancel any in-flight animation instead of stacking frames.
// ---------------------------------------------------------------------
const activeAnimations = new Map();

function animateValue(el, fromValue, toValue, { duration = 700, formatter = Math.round } = {}) {
  if (fromValue === toValue) {
    el.textContent = formatter(toValue);
    return;
  }

  const existing = activeAnimations.get(el);
  if (existing) cancelAnimationFrame(existing);

  const start = performance.now();

  function frame(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = easeOutCubic(t);
    const current = fromValue + (toValue - fromValue) * eased;
    el.textContent = formatter(current);

    if (t < 1) {
      activeAnimations.set(el, requestAnimationFrame(frame));
    } else {
      activeAnimations.delete(el);
      el.textContent = formatter(toValue);
    }
  }

  activeAnimations.set(el, requestAnimationFrame(frame));
}

// Tracks the last value shown for each animated stat so we always tween
// FROM where the number actually is, not from a stale snapshot.
const lastValues = {
  streak: 0,
  longest: 0,
  focusSeconds: 0,
  distractionSeconds: 0,
};

// ---------------------------------------------------------------------
// Summary (streaks, today's totals, progress bar)
// ---------------------------------------------------------------------
async function loadSummary() {
  const res = await fetch('/api/summary');
  const data = await res.json();

  animateValue(els.streakValue, lastValues.streak, data.current_streak, { formatter: Math.round });
  lastValues.streak = data.current_streak;

  animateValue(els.longestValue, lastValues.longest, data.longest_streak, { formatter: Math.round });
  lastValues.longest = data.longest_streak;

  const focusSeconds = data.today.focus_seconds;
  const goalSeconds = data.goal_seconds;
  animateValue(els.todayFocusValue, lastValues.focusSeconds, focusSeconds, { formatter: fmtMinutes });
  lastValues.focusSeconds = focusSeconds;
  els.todayGoalUnit.textContent = `of ${fmtMinutes(goalSeconds)} goal`;

  const distractionSeconds = data.today.distraction_seconds;
  animateValue(els.todayDistractionValue, lastValues.distractionSeconds, distractionSeconds, { formatter: fmtMinutes });
  lastValues.distractionSeconds = distractionSeconds;

  const pct = Math.min(100, (focusSeconds / goalSeconds) * 100);
  els.progressFill.style.width = `${pct}%`; // CSS transition on width handles the smoothing
  els.progressFraction.textContent = `${fmtMinutes(focusSeconds)} / ${fmtMinutes(goalSeconds)}`;

  return { goalSeconds };
}

// ---------------------------------------------------------------------
// Chain grid — updates existing cells in place (by day key) so the
// background-color CSS transition actually plays, instead of destroying
// and recreating every cell on every poll.
// ---------------------------------------------------------------------
const chainCellsByDay = new Map();
let chainInitialized = false;

async function loadChain(goalSeconds) {
  const res = await fetch('/api/history');
  const days = await res.json();

  const daysMatchExisting =
    chainInitialized && days.every((d) => chainCellsByDay.has(d.day));

  if (!daysMatchExisting) {
    buildChainGrid(days, goalSeconds);
  } else {
    for (const d of days) {
      const cell = chainCellsByDay.get(d.day);
      updateChainCell(cell, d, goalSeconds);
    }
  }

  drawChainLinks(days.map((d) => chainCellsByDay.get(d.day)), days);
}

function updateChainCell(cell, d, goalSeconds) {
  if (d.is_future) {
    cell.className = 'chain-cell future';
    cell.removeAttribute('title');
    return;
  }
  const level = levelForFocus(d.focus_seconds, goalSeconds);
  cell.className = `chain-cell level-${level}`;
  cell.title = `${d.day} · ${fmtMinutes(d.focus_seconds)} focus${d.goal_met ? ' · goal met' : ''}`;
  cell.dataset.goalMet = d.goal_met ? '1' : '0';
}

function buildChainGrid(days, goalSeconds) {
  els.chainGrid.innerHTML = '';
  chainCellsByDay.clear();

  for (const d of days) {
    const cell = document.createElement('div');
    cell.dataset.day = d.day;
    updateChainCell(cell, d, goalSeconds);
    els.chainGrid.appendChild(cell);
    chainCellsByDay.set(d.day, cell);
  }
  chainInitialized = true;
}

function drawChainLinks(cellEls, days) {
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

// ---------------------------------------------------------------------
// Breakdown list — same incremental-update approach, keyed by app+category,
// so the width transition on each bar actually animates on refresh instead
// of popping to the new value.
// ---------------------------------------------------------------------
const breakdownRowsByKey = new Map();

async function loadBreakdown() {
  const res = await fetch('/api/breakdown');
  const rows = await res.json();

  if (rows.length === 0) {
    if (breakdownRowsByKey.size > 0 || els.breakdownList.children.length === 0) {
      els.breakdownList.innerHTML = '<div class="empty-note">No sessions closed yet today — switch apps at least once for this to populate.</div>';
      breakdownRowsByKey.clear();
    }
    return;
  }

  const maxSeconds = Math.max(...rows.map((r) => r.total_seconds));
  const seenKeys = new Set();

  // Clear the "empty" placeholder if it's still showing
  if (breakdownRowsByKey.size === 0 && els.breakdownList.querySelector('.empty-note')) {
    els.breakdownList.innerHTML = '';
  }

  for (const row of rows) {
    const key = `${row.app_name}|${row.category}`;
    seenKeys.add(key);
    const pct = Math.max(4, (row.total_seconds / maxSeconds) * 100);

    let entry = breakdownRowsByKey.get(key);
    if (!entry) {
      const el = document.createElement('div');
      el.className = 'breakdown-row';
      el.innerHTML = `
        <span class="breakdown-name"></span>
        <span class="breakdown-bar-track"><span class="breakdown-bar-fill"></span></span>
        <span class="breakdown-time"></span>
      `;
      els.breakdownList.appendChild(el);
      entry = {
        row: el,
        nameEl: el.querySelector('.breakdown-name'),
        fillEl: el.querySelector('.breakdown-bar-fill'),
        timeEl: el.querySelector('.breakdown-time'),
      };
      breakdownRowsByKey.set(key, entry);
    }

    entry.nameEl.textContent = row.app_name;
    entry.fillEl.className = `breakdown-bar-fill ${row.category}`;
    entry.fillEl.style.width = `${pct}%`;
    entry.timeEl.textContent = fmtMinutes(row.total_seconds);
  }

  // Remove rows for apps that no longer appear in today's breakdown
  for (const [key, entry] of breakdownRowsByKey) {
    if (!seenKeys.has(key)) {
      entry.row.remove();
      breakdownRowsByKey.delete(key);
    }
  }
}

async function refreshAll() {
  const { goalSeconds } = await loadSummary();
  await loadChain(goalSeconds);
  await loadBreakdown();
}

window.addEventListener('resize', () => {
  const days = Array.from(chainCellsByDay.entries()).map(([day, cell]) => ({
    day,
    goal_met: cell.dataset.goalMet === '1',
  }));
  if (days.length) {
    drawChainLinks(days.map((d) => chainCellsByDay.get(d.day)), days);
  }
});

refreshAll();
setInterval(refreshAll, REFRESH_MS);
