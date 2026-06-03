/* ── Polybot terminal dashboard ──────────────────────────────────────── */
'use strict';

const socket = io();

// P&L chart state
let pnlChart = null;
const pnlData = { labels: [], values: [] };

// Log ring buffer
const LOG_MAX = 50;
const logLines = [];

// Balance refresh interval (every 30s — on-chain call, expensive)
let balanceTimer = null;

// ── Init ──────────────────────────────────────────────────────────────────

let _wsAlive = false;          // flips true on first tick event
let _restPollTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  initChart();
  fetchInitial();
  startBalancePoller();
  startClock();
  // If no WS tick arrives within 2 s, fall back to REST polling
  setTimeout(() => {
    if (!_wsAlive) startRestPoll();
  }, 2000);
});

function startClock() {
  function tick() {
    const el = document.getElementById('clock');
    if (el) el.textContent = new Date().toUTCString().replace('GMT', 'UTC');
  }
  tick();
  setInterval(tick, 1000);
}

// ── Socket events ─────────────────────────────────────────────────────────

socket.on('connect', () => pushLog('Connected to polybot', 'action'));
socket.on('disconnect', () => pushLog('Disconnected', 'error'));

socket.on('tick', (data) => {
  if (!_wsAlive) {
    _wsAlive = true;
    stopRestPoll();
    pushLog('WebSocket live', 'action');
  }
  renderMarkets(data.markets || []);
  updateStatusBar(data);
  if (data.stats) updateStats(data.stats);
  if (data.last_action) pushLog(data.last_action, 'action');
  if (data.last_error)  pushLog('ERROR: ' + data.last_error, 'error');
});

socket.on('trade', (trade) => {
  prependTradeRow(trade);
});

socket.on('resolution', (data) => {
  if (data.stats) updateStats(data.stats);
  refreshTrades();
  refreshChart();
});

// ── Initial data fetch ────────────────────────────────────────────────────

function fetchInitial() {
  fetch('/api/trades?limit=200').then(r => r.json()).then(trades => {
    const tbody = document.getElementById('trade-tbody');
    tbody.innerHTML = '';
    trades.forEach(t => appendTradeRow(tbody, t));
  });
  fetch('/api/stats').then(r => r.json()).then(updateStats);
  refreshChart();
}

function refreshTrades() {
  fetch('/api/trades?limit=200').then(r => r.json()).then(trades => {
    const tbody = document.getElementById('trade-tbody');
    tbody.innerHTML = '';
    trades.forEach(t => appendTradeRow(tbody, t));
  });
}

// ── Status bar ────────────────────────────────────────────────────────────

function updateStatusBar(data) {
  const dot = document.getElementById('dot');
  if (dot) {
    dot.className = data.running ? 'running' : 'stopped';
  }
}

// ── Live Markets ──────────────────────────────────────────────────────────

function renderMarkets(markets) {
  const el = document.getElementById('markets-body');
  if (!el) return;

  if (!markets.length) {
    el.innerHTML = '<div style="color:#446644;padding:8px 0">NO ACTIVE MARKETS</div>';
    return;
  }

  el.innerHTML = markets.map(m => {
    const rem = m.remaining;
    const mm  = String(Math.floor(rem / 60)).padStart(2, '0');
    const ss  = String(rem % 60).padStart(2, '0');
    const timer = `${mm}:${ss}`;

    const upFav = m.up_ask >= m.down_ask;

    let badge, badgeClass;
    if (m.bet_placed && m.flagged_side) {
      badge = 'BET ✓';  badgeClass = 'bet';
    } else if (m.bet_placed) {
      badge = 'SKIP';   badgeClass = 'skipped';
    } else if (m.flagged) {
      badge = 'FLAGGED'; badgeClass = 'flagged';
    } else if (rem < 85) {
      badge = 'SKIP';   badgeClass = 'skipped';
    } else {
      badge = 'WATCH';  badgeClass = 'watching';
    }

    return `<div class="market-row">
      <span class="timer">${timer}</span>
      <div class="price-cell up-cell${upFav ? ' fav' : ''}">
        <span class="lbl">UP</span>
        <span class="val">${m.up_ask.toFixed(3)}</span>
      </div>
      <div class="price-cell dn-cell${!upFav ? ' fav' : ''}">
        <span class="lbl">DOWN</span>
        <span class="val">${m.down_ask.toFixed(3)}</span>
      </div>
      <span class="badge ${badgeClass}">${badge}</span>
    </div>`;
  }).join('');
}

// ── Trade history ─────────────────────────────────────────────────────────

function prependTradeRow(trade) {
  const tbody = document.getElementById('trade-tbody');
  if (!tbody) return;
  const row = buildTradeRow(trade);
  tbody.insertBefore(row, tbody.firstChild);
  row.classList.add('flash');
  setTimeout(() => row.classList.remove('flash'), 1500);
  // Keep max 50 rows
  while (tbody.children.length > 50) tbody.removeChild(tbody.lastChild);
}

function appendTradeRow(tbody, trade) {
  tbody.appendChild(buildTradeRow(trade));
}

function buildTradeRow(t) {
  const row = document.createElement('div');

  const dt = new Date(t.timestamp * 1000);
  const ts = dt.toTimeString().slice(0, 8);

  const sideClass = t.side.toLowerCase();
  let statusText, statusClass, pnlText, pnlClass;

  if (t.won === '1') {
    statusText = 'WIN'; statusClass = 'win';
    pnlText = '+' + parseFloat(t.pnl).toFixed(2);
  } else if (t.won === '0') {
    statusText = 'LOSS'; statusClass = 'loss';
    pnlText = parseFloat(t.pnl).toFixed(2);
  } else if (t.status === 'simulated') {
    statusText = 'SIM'; statusClass = 'sim'; pnlText = '—';
  } else if (t.status === 'failed') {
    statusText = 'FAIL'; statusClass = 'loss'; pnlText = '—';
  } else {
    statusText = 'PEND'; statusClass = 'pend'; pnlText = '—';
  }

  const rowExtra = t.won === '1' ? ' win' : t.won === '0' ? ' loss' : '';
  row.className = 'trade-row' + rowExtra;
  row.innerHTML = `
    <span class="ts-cell">${ts}</span>
    <span class="side-cell ${sideClass}">${t.side.toUpperCase()}</span>
    <span>${parseFloat(t.price).toFixed(3)}</span>
    <span>${t.shares}</span>
    <span class="status-cell ${statusClass}">${statusText}</span>
    <span class="pnl-cell">${pnlText}</span>
  `;
  return row;
}

// ── Stats ─────────────────────────────────────────────────────────────────

function updateStats(s) {
  setText('stat-total-bets',  s.total_bets);
  setText('stat-win-rate',    s.total_bets > 0 ? (s.win_rate * 100).toFixed(1) + '%' : '—');
  setText('stat-total-pnl',   fmtPnl(s.total_pnl));
  setText('stat-today-bets',  s.today_bets);
  setText('stat-today-wins',  s.today_wins);
  setText('stat-today-pnl',   fmtPnl(s.today_pnl));
  setText('stat-pending',     s.pending);
  setText('stat-simulated',   s.simulated);

  // Colour total P&L
  const pnlEl = document.getElementById('stat-total-pnl');
  if (pnlEl) {
    pnlEl.className = 'stat-value ' + (s.total_pnl >= 0 ? '' : 'red');
  }
  const tpnlEl = document.getElementById('stat-today-pnl');
  if (tpnlEl) {
    tpnlEl.className = 'stat-value dim ' + (s.today_pnl >= 0 ? '' : 'red');
  }
}

function fmtPnl(v) {
  if (v === null || v === undefined) return '—';
  return (v >= 0 ? '+' : '') + parseFloat(v).toFixed(2);
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── Balance poller ────────────────────────────────────────────────────────

function startBalancePoller() {
  function refresh() {
    fetch('/api/balance').then(r => r.json()).then(b => {
      setText('balance-usdc',  b.usdc !== undefined ? b.usdc.toFixed(2) : '—');
      setText('balance-matic', b.matic !== undefined ? b.matic.toFixed(4) : '—');
    }).catch(() => {});
  }
  refresh();
  balanceTimer = setInterval(refresh, 30000);
}

// ── P&L chart ─────────────────────────────────────────────────────────────

function initChart() {
  const canvas = document.getElementById('chart-canvas');
  if (!canvas || !window.Chart) return;

  pnlChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: pnlData.labels,
      datasets: [{
        data: pnlData.values,
        borderColor: '#00ff00',
        backgroundColor: 'rgba(0,255,0,0.04)',
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.1,
      }]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => (ctx.raw >= 0 ? '+' : '') + ctx.raw.toFixed(2) + ' USDC',
          },
          backgroundColor: '#001100',
          borderColor: '#006600',
          borderWidth: 1,
          titleColor: '#ffb000',
          bodyColor: '#00ff00',
        },
      },
      scales: {
        x: {
          display: false,
        },
        y: {
          grid: { color: '#001a00' },
          ticks: {
            color: '#446644',
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            callback: v => (v >= 0 ? '+' : '') + v.toFixed(2),
          },
        },
      },
    }
  });
}

function refreshChart() {
  fetch('/api/trades?limit=5000').then(r => r.json()).then(trades => {
    // Build cumulative P&L from oldest to newest
    const resolved = trades.filter(t => t.pnl !== '').reverse();
    let cum = 0;
    pnlData.labels = [];
    pnlData.values = [];
    for (const t of resolved) {
      cum += parseFloat(t.pnl);
      const dt = new Date(t.timestamp * 1000);
      pnlData.labels.push(dt.toLocaleDateString());
      pnlData.values.push(Math.round(cum * 1000) / 1000);
    }
    if (pnlChart) {
      pnlChart.data.labels  = pnlData.labels;
      pnlChart.data.datasets[0].data = pnlData.values;
      // Colour line red if final P&L is negative
      const last = pnlData.values[pnlData.values.length - 1] || 0;
      pnlChart.data.datasets[0].borderColor = last >= 0 ? '#00ff00' : '#ff3030';
      pnlChart.update('none');
    }
  });
}

// ── Log ───────────────────────────────────────────────────────────────────

function pushLog(msg, cls) {
  logLines.unshift({ msg, cls });
  if (logLines.length > LOG_MAX) logLines.pop();
  renderLog();
}

function renderLog() {
  const el = document.getElementById('log-body');
  if (!el) return;
  el.innerHTML = logLines.map(l =>
    `<div class="log-line ${l.cls || ''}">${escHtml(l.msg)}</div>`
  ).join('');
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── REST poll fallback (when WebSocket not available) ─────────────────────

function startRestPoll() {
  if (_restPollTimer) return;
  pushLog('WebSocket unavailable — polling REST', 'sim');
  _restPollTimer = setInterval(() => {
    fetch('/api/markets').then(r => r.json()).then(renderMarkets).catch(() => {});
    fetch('/api/stats').then(r => r.json()).then(updateStats).catch(() => {});
    fetch('/api/status').then(r => r.json()).then(updateStatusBar).catch(() => {});
  }, 1000);
}

function stopRestPoll() {
  if (_restPollTimer) {
    clearInterval(_restPollTimer);
    _restPollTimer = null;
  }
}

// ── Controls ──────────────────────────────────────────────────────────────

function ctrlStart() {
  fetch('/api/control/start', { method: 'POST' })
    .then(r => r.json())
    .then(d => pushLog(d.running ? 'Bot started' : 'Start failed', 'action'));
}

function ctrlStop() {
  fetch('/api/control/stop', { method: 'POST' })
    .then(r => r.json())
    .then(d => pushLog(d.running ? 'Stop requested' : 'Bot stopped', 'action'));
}
