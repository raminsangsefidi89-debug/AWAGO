/* ============================================================
   AWAGO dashboard application (vanilla JS + Chart.js, offline).
   All API calls go to /api/v1 on the same origin.
   ============================================================ */
'use strict';

const API = '/api/v1';
const state = {
  pair: null,
  range: '6m',
  horizon: 7,
  pairs: [],
  horizons: [1, 7, 30],
  history: null,
  theme: localStorage.getItem('awago-theme') || 'dark',
};

const $ = (id) => document.getElementById(id);

/* ---------------- Formatting helpers ---------------- */

function toFaDigits(value) {
  return String(value).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]);
}

/** Latin, tabular formatting for financial values (bidi-safe via .num class). */
function fmtNum(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${value > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;
}

/** Compact Jalali date for UI prose (charts keep ISO Gregorian). */
function jalaliDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const [jy, jm, jd] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
    return toFaDigits(`${jy}/${String(jm).padStart(2, '0')}/${String(jd).padStart(2, '0')}`);
  } catch {
    return iso.slice(0, 10);
  }
}

function fmtTimestamp(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${jalaliDate(iso)} — ${toFaDigits(`${hh}:${mm}`)}`;
  } catch {
    return iso;
  }
}

/* Gregorian → Jalali (Birashk / jalaali-js algorithm, public domain logic). */
function gregorianToJalali(gy, gm, gd) {
  const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let jy = gy <= 1600 ? 0 : 979;
  gy -= gy <= 1600 ? 621 : 1600;
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    365 * gy +
    Math.floor((gy2 + 3) / 4) -
    Math.floor((gy2 + 99) / 100) +
    Math.floor((gy2 + 399) / 400) -
    80 +
    gd +
    g_d_m[gm - 1];
  jy += 33 * Math.floor(days / 12053);
  days %= 12053;
  jy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    jy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }
  const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
  return [jy, jm, jd];
}

/* ---------------- HTTP ---------------- */

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON */
  }
  if (!res.ok) {
    const msg = (body && body.error && body.error.message) || `خطای HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

/* ---------------- Chart setup ---------------- */

let historyChart = null;
let forecastChart = null;

function chartTheme() {
  const styles = getComputedStyle(document.body);
  return {
    text: styles.getPropertyValue('--text-dim').trim(),
    grid: styles.getPropertyValue('--border').trim(),
    teal: '#2dd4bf',
    gold: '#f5b942',
    red: '#f87171',
  };
}

function baseChartOptions(yLabel) {
  const t = chartTheme();
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        rtl: true,
        textDirection: 'rtl',
        labels: { color: t.text, font: { family: 'Vazirmatn', size: 12 }, usePointStyle: true },
      },
      tooltip: {
        rtl: true,
        textDirection: 'rtl',
        titleFont: { family: 'Vazirmatn' },
        bodyFont: { family: 'Vazirmatn' },
        callbacks: {
          title(items) {
            return items.length ? jalaliDate(items[0].label) : '';
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: t.text,
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 9,
          font: { family: 'Vazirmatn', size: 11 },
          callback(value) {
            const label = this.getLabelForValue(value);
            return label ? label.slice(5) : '';
          },
        },
        grid: { color: t.grid },
      },
      y: {
        ticks: {
          color: t.text,
          font: { family: 'Vazirmatn', size: 11 },
          callback: (v) => Number(v).toLocaleString('en-US', { maximumFractionDigits: 4 }),
        },
        grid: { color: t.grid },
        title: { display: !!yLabel, text: yLabel, color: t.text, font: { family: 'Vazirmatn' } },
      },
    },
  };
}

function renderHistoryChart(bars) {
  const ctx = $('historyChart').getContext('2d');
  const t = chartTheme();
  const labels = bars.map((b) => b.timestamp);
  const closes = bars.map((b) => b.close);
  if (historyChart) historyChart.destroy();
  historyChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'قیمت بسته‌شدن',
          data: closes,
          borderColor: t.teal,
          backgroundColor: 'rgba(45, 212, 191, 0.12)',
          fill: true,
          tension: 0.22,
          pointRadius: 0,
          pointHitRadius: 8,
          borderWidth: 2,
        },
      ],
    },
    options: baseChartOptions('قیمت'),
  });
}

function renderForecastChart(tail, forecast) {
  const ctx = $('forecastChart').getContext('2d');
  const t = chartTheme();
  const labels = tail.map((b) => b.timestamp).concat(forecast ? [forecast.forecast_target_date] : []);
  const n = tail.length;
  const historyData = tail.map((b) => b.close).concat(forecast ? [null] : []);
  const forecastLine = new Array(labels.length).fill(null);
  const lower = new Array(labels.length).fill(null);
  const upper = new Array(labels.length).fill(null);
  if (forecast) {
    if (n > 0) forecastLine[n - 1] = tail[n - 1].close;
    forecastLine[n] = forecast.forecast_price;
    if (n > 0) {
      lower[n - 1] = tail[n - 1].close;
      upper[n - 1] = tail[n - 1].close;
    }
    lower[n] = forecast.interval_lower;
    upper[n] = forecast.interval_upper;
  }

  if (forecastChart) forecastChart.destroy();
  forecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'قیمت تاریخی',
          data: historyData,
          borderColor: t.teal,
          backgroundColor: 'transparent',
          tension: 0.22,
          pointRadius: 0,
          pointHitRadius: 8,
          borderWidth: 2,
          order: 1,
        },
        {
          label: 'پیش‌بینی',
          data: forecastLine,
          borderColor: t.gold,
          backgroundColor: t.gold,
          borderDash: [7, 5],
          tension: 0.15,
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2.4,
          spanGaps: false,
          order: 0,
        },
        {
          label: 'کران پایین بازه اطمینان',
          data: lower,
          borderColor: 'rgba(245, 185, 66, 0.55)',
          backgroundColor: 'transparent',
          pointRadius: 0,
          borderWidth: 1.2,
          tension: 0.15,
          spanGaps: false,
          order: 2,
        },
        {
          label: 'کران بالای بازه اطمینان',
          data: upper,
          borderColor: 'rgba(245, 185, 66, 0.55)',
          backgroundColor: 'rgba(245, 185, 66, 0.18)',
          pointRadius: 0,
          borderWidth: 1.2,
          tension: 0.15,
          spanGaps: false,
          fill: '-1',
          order: 2,
        },
      ],
    },
    options: baseChartOptions('قیمت'),
  });
}

/* ---------------- Data loading ---------------- */

function rangeStartDate(range) {
  const end = new Date();
  const map = { '1m': 31, '3m': 92, '6m': 183, '1y': 366 };
  if (!map[range]) return null;
  const d = new Date(end.getTime() - map[range] * 86400000);
  return d.toISOString().slice(0, 10);
}

function showOnly(panel) {
  $('emptyState').hidden = panel !== 'empty';
  $('errorState').hidden = panel !== 'error';
}

function showError(message) {
  $('errorStateMessage').textContent = message;
  showOnly('error');
}

async function loadHealth() {
  try {
    const h = await fetchJSON(`${API}/health`);
    const badge = $('healthBadge');
    if (h.latest_data_source === 'demo') {
      badge.textContent = 'حالت Demo — داده آزمایشی';
      badge.className = 'badge badge-demo';
      $('demoBanner').hidden = false;
    } else if (h.latest_data_source) {
      badge.textContent = `داده واقعی (${h.latest_data_source})`;
      badge.className = 'badge badge-real';
      $('demoBanner').hidden = true;
    } else {
      badge.textContent = 'بدون داده';
      badge.className = 'badge badge-muted';
      $('demoBanner').hidden = true;
    }
    $('heroLastUpdate').textContent = fmtTimestamp(h.latest_data_timestamp);
    $('heroSource').textContent = h.latest_data_source ? h.latest_data_source : '—';
  } catch {
    $('healthBadge').textContent = 'سرویس در دسترس نیست';
    $('healthBadge').className = 'badge badge-error';
  }
}

async function loadPairs() {
  const data = await fetchJSON(`${API}/pairs`);
  state.pairs = data.pairs;
  const select = $('pairSelect');
  select.innerHTML = '';
  for (const p of data.pairs) {
    const opt = document.createElement('option');
    opt.value = p.symbol;
    opt.textContent = `${p.display_name_fa} (${p.symbol})`;
    select.appendChild(opt);
  }
  if (data.pairs.length === 0) throw new Error('هیچ جفت‌ارزی ثبت نشده است.');
  if (!state.pair || !data.pairs.some((p) => p.symbol === state.pair)) {
    state.pair = data.pairs[0].symbol;
  }
  select.value = state.pair;
}

function renderPriceCard(price) {
  $('pairLabel').textContent = state.pair;
  $('currentPrice').textContent = fmtNum(price.price, price.price > 50 ? 2 : 4);
  const changeEl = $('priceChange');
  if (price.change_pct !== null && price.change_pct !== undefined) {
    changeEl.textContent = `${fmtPct(price.change_pct)} (${fmtNum(price.change_abs, 4)})`;
    changeEl.className = `change ${price.change_pct >= 0 ? 'up' : 'down'}`;
  } else {
    changeEl.textContent = '—';
    changeEl.className = 'change';
  }
  $('priceTimestamp').textContent = fmtTimestamp(price.timestamp);
  const badge = $('sourceBadge');
  if (price.is_demo) {
    badge.textContent = `منبع: ${price.data_source} (آزمایشی)`;
    badge.className = 'badge badge-demo';
    $('demoBanner').hidden = false;
  } else {
    badge.textContent = `منبع: ${price.data_source}`;
    badge.className = 'badge badge-real';
    $('demoBanner').hidden = true;
  }
}

const TREND_LABELS = { up: 'صعودی ▲', down: 'نزولی ▼', sideways: 'خنثی ◆' };
const VOL_LABELS = { low: 'کم', medium: 'متوسط', high: 'زیاد' };

function renderIndicators(data) {
  const trend = data.trend;
  const dirEl = $('trendDirection');
  dirEl.textContent = TREND_LABELS[trend.direction] || trend.direction;
  dirEl.className = `trend-pill ${trend.direction}`;
  $('trendStrength').textContent = toFaDigits(`${Math.round(trend.strength)}٪`);
  $('trendStrengthBar').style.width = `${Math.min(100, trend.strength)}%`;
  $('volRegime').textContent = VOL_LABELS[trend.volatility_regime] || trend.volatility_regime;
  const ind = trend.indicators || {};
  $('indRsi').textContent = ind.rsi_14 != null ? fmtNum(ind.rsi_14, 1) : '—';
  $('indMacd').textContent = ind.macd != null ? fmtNum(ind.macd, 5) : '—';
  $('indSma20').textContent = ind.sma_20 != null ? fmtNum(ind.sma_20, 4) : '—';
  $('indSma50').textContent = ind.sma_50 != null ? fmtNum(ind.sma_50, 4) : '—';
  $('indAtr').textContent = ind.atr_14 != null ? fmtNum(ind.atr_14, 5) : '—';
  $('indVol').textContent = ind.vol_20d_annualized != null ? `${fmtNum(ind.vol_20d_annualized, 2)}٪` : '—';
}

function renderForecast(forecast) {
  $('forecastPrice').textContent = fmtNum(forecast.forecast_price, forecast.forecast_price > 50 ? 2 : 4);
  const levelPct = toFaDigits(`${Math.round(forecast.interval_level * 100)}٪`);
  $('forecastInterval').textContent =
    `${levelPct}: ${fmtNum(forecast.interval_lower, 4)} — ${fmtNum(forecast.interval_upper, 4)}`;
  $('forecastTarget').textContent = jalaliDate(forecast.forecast_target_date);
  const model = forecast.model || {};
  $('modelName').textContent = model.model_name || '—';
  $('modelTrainedAt').textContent = fmtTimestamp(model.trained_at);
  const beatsEl = $('modelBeats');
  const noteEl = $('beatsNote');
  if (model.beats_baseline === true) {
    beatsEl.textContent = '✅ بهتر از خط پایه (ساده)';
    beatsEl.className = 'beats-yes';
    noteEl.textContent = 'در ارزیابی گذشته‌نگر، خطای این مدل کمتر از خط پایه «قیمت فردا = امروز» بوده است.';
  } else if (model.beats_baseline === false) {
    beatsEl.textContent = '⚠️ بهتر از خط پایه نیست';
    beatsEl.className = 'beats-no';
    noteEl.textContent =
      'صادقانه: در ارزیابی گذشته‌نگر، این مدل نتوانسته از خط پایه ساده بهتر عمل کند. پیش‌بینی‌ها را با احتیاط ببینید.';
  } else {
    beatsEl.textContent = '—';
    beatsEl.className = '';
    noteEl.textContent = '';
  }
  $('modelMae').textContent = model.mae != null ? fmtNum(model.mae, 6) : '—';
}

function renderMetricsTable(items) {
  const body = $('metricsBody');
  body.innerHTML = '';
  if (!items || items.length === 0) {
    body.innerHTML = '<tr><td colspan="8" class="empty-cell">هنوز مدلی آموزش داده نشده است. از بخش «عملیات داده و مدل» مدل‌ها را آموزش دهید.</td></tr>';
    return;
  }
  const isBaseline = (name) => name === 'naive' || name === 'drift';
  for (const m of items) {
    const tr = document.createElement('tr');
    const da = m.directional_accuracy === null || m.directional_accuracy === undefined
      ? 'تعریف‌نشده'
      : `${fmtNum(m.directional_accuracy, 1)}٪`;
    let compare;
    if (isBaseline(m.model_name)) {
      compare = '<span class="pill baseline">خط پایه</span>';
    } else if (m.beats_baseline) {
      compare = '<span class="pill win">بهتر از خط پایه ✓</span>';
    } else {
      compare = '<span class="pill lose">بهتر نیست</span>';
    }
    const name = isBaseline(m.model_name)
      ? (m.model_name === 'naive' ? 'ساده (بدون تغییر)' : 'روندها (Drift)')
      : m.model_name;
    tr.innerHTML = `
      <td class="num">${m.horizon}</td>
      <td class="num">${name}</td>
      <td class="num">${fmtNum(m.mae, 6)}</td>
      <td class="num">${fmtNum(m.rmse, 6)}</td>
      <td class="num">${fmtNum(m.smape, 3)}٪</td>
      <td class="num">${da}</td>
      <td class="num">${fmtNum(m.baseline_mae, 6)}</td>
      <td>${compare}</td>`;
    body.appendChild(tr);
  }
}

/* ---------------- Load-all ---------------- */

async function loadAll() {
  showOnly(null);
  try {
    await loadHealth();
    await loadPairs();

    const price = await fetchJSON(`${API}/pairs/${encodeURIComponent(state.pair)}/price`);
    renderPriceCard(price);

    const start = rangeStartDate(state.range);
    const qs = start ? `?start=${start}&limit=5000` : '?limit=5000';
    const history = await fetchJSON(`${API}/pairs/${encodeURIComponent(state.pair)}/history${qs}`);
    state.history = history;
    $('historyPairLabel').textContent = state.pair;

    if (!history.bars || history.bars.length === 0) {
      showOnly('empty');
    } else {
      renderHistoryChart(history.bars);

      const tail = history.bars.slice(-60);
      try {
        const forecast = await fetchJSON(
          `${API}/pairs/${encodeURIComponent(state.pair)}/forecast?horizon=${state.horizon}`
        );
        renderForecast(forecast);
        renderForecastChart(tail, forecast);
      } catch (err) {
        if (err.status === 404) {
          $('forecastPrice').textContent = '—';
          $('forecastInterval').textContent = '—';
          $('forecastTarget').textContent = '—';
          $('modelName').textContent = 'مدلی آموزش داده نشده';
          $('beatsNote').textContent =
            'برای این جفت‌ارز هنوز مدلی آموزش داده نشده است. از دکمه «آموزش مدل‌ها» استفاده کنید.';
          renderForecastChart(tail, null);
        } else {
          throw err;
        }
      }
    }

    try {
      const ind = await fetchJSON(`${API}/pairs/${encodeURIComponent(state.pair)}/indicators`);
      renderIndicators(ind);
    } catch {
      /* indicators are non-critical */
    }

    try {
      const metrics = await fetchJSON(`${API}/metrics/${encodeURIComponent(state.pair)}`);
      renderMetricsTable(metrics.metrics);
    } catch (err) {
      if (err.status === 404) {
        renderMetricsTable([]);
      } else {
        throw err;
      }
    }
  } catch (err) {
    showError(err.message || 'خطای ناشناخته در دریافت اطلاعات.');
  }
}

/* ---------------- Jobs ---------------- */

let jobPollTimer = null;

async function startJob(type, payload) {
  const statusBox = $('jobStatus');
  statusBox.hidden = false;
  $('jobMessage').textContent = 'در حال ارسال درخواست…';
  $('jobProgress').style.width = '3%';
  try {
    const job = await fetchJSON(`${API}/jobs/${type}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    pollJob(job.id);
  } catch (err) {
    $('jobMessage').textContent = `خطا: ${err.message}`;
  }
}

function pollJob(jobId) {
  if (jobPollTimer) clearInterval(jobPollTimer);
  jobPollTimer = setInterval(async () => {
    try {
      const job = await fetchJSON(`${API}/jobs/${jobId}`);
      $('jobMessage').textContent = `[${job.status === 'done' ? 'پایان' : job.status === 'failed' ? 'خطا' : 'در حال اجرا'}] ${job.message}`;
      $('jobProgress').style.width = `${Math.round((job.progress || 0) * 100)}%`;
      if (job.status === 'done' || job.status === 'failed') {
        clearInterval(jobPollTimer);
        jobPollTimer = null;
        if (job.status === 'done') {
          setTimeout(loadAll, 600);
        }
      }
    } catch {
      clearInterval(jobPollTimer);
      jobPollTimer = null;
      $('jobMessage').textContent = 'ارتباط با وضعیت شغل قطع شد.';
    }
  }, 1500);
}

/* ---------------- Theme ---------------- */

function applyTheme() {
  document.body.dataset.theme = state.theme;
  $('themeToggle').textContent = state.theme === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('awago-theme', state.theme);
  if (state.history && state.history.bars && state.history.bars.length) {
    renderHistoryChart(state.history.bars);
  }
}

/* ---------------- Horizon selector ---------------- */

function buildHorizonSelector() {
  const box = $('horizonSelector');
  box.innerHTML = '';
  for (const h of state.horizons) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.horizon = String(h);
    btn.textContent = `${toFaDigits(h)} روز`;
    if (h === state.horizon) btn.classList.add('active');
    btn.addEventListener('click', () => {
      state.horizon = h;
      box.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
      loadAll();
    });
    box.appendChild(btn);
  }
}

/* ---------------- Wiring ---------------- */

document.addEventListener('DOMContentLoaded', () => {
  applyTheme();

  $('themeToggle').addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    applyTheme();
    loadAll();
  });

  $('pairSelect').addEventListener('change', (e) => {
    state.pair = e.target.value;
    loadAll();
  });

  $('rangeSelector').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-range]');
    if (!btn) return;
    state.range = btn.dataset.range;
    $('rangeSelector').querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
    loadAll();
  });

  $('refreshBtn').addEventListener('click', loadAll);
  $('retryBtn').addEventListener('click', loadAll);
  $('collectBtn').addEventListener('click', () => startJob('collect-data', {}));
  $('trainBtn').addEventListener('click', () => startJob('train', { quick: true }));

  buildHorizonSelector();
  loadAll();
});
