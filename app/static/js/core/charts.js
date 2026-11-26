/** Chart.js wrappers: line charts, fan (uncertainty) charts, bars. */

const COLORS = {
  line: "#4f8cff",
  lineAlt: "#2dd4bf",
  band: "rgba(79, 140, 255, 0.18)",
  bandAlt: "rgba(45, 212, 191, 0.15)",
  gridDark: "rgba(255,255,255,0.08)",
  gridLight: "rgba(0,0,0,0.08)",
  textDark: "rgba(255,255,255,0.75)",
  textLight: "rgba(0,0,0,0.7)",
};

function themeColors() {
  const dark = document.body.dataset.theme !== "light";
  return {
    grid: dark ? COLORS.gridDark : COLORS.gridLight,
    text: dark ? COLORS.textDark : COLORS.textLight,
  };
}

export function destroyChart(canvasId) {
  const el = document.getElementById(canvasId);
  if (el && el.chart) {
    el.chart.destroy();
    el.chart = null;
  }
}

export function lineChart(canvasId, labels, datasets, opts = {}) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === "undefined") return null;
  if (el.chart) el.chart.destroy();
  const t = themeColors();
  el.chart = new Chart(el, {
    type: "line",
    data: {
      labels,
      datasets: datasets.map((d) => ({
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        ...d,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {},
      plugins: {
        legend: { labels: { color: t.text } },
        tooltip: { rtl: true },
      },
      scales: {
        x: { ticks: { color: t.text, maxTicksLimit: 8 }, grid: { color: t.grid } },
        y: { ticks: { color: t.text }, grid: { color: t.grid } },
      },
      ...(opts.extra || {}),
    },
  });
  return el.chart;
}

/** Fan chart: point line + lower/upper uncertainty band. */
export function fanChart(canvasId, fan, opts = {}) {
  const labels = fan.map((p) => p.step);
  const mid = fan.map((p) => p.price);
  const lower = fan.map((p) => p.lower);
  const upper = fan.map((p) => p.upper);
  return lineChart(
    canvasId,
    labels,
    [
      {
        label: opts.label || "پیش‌بینی نقطه‌ای",
        data: mid,
        borderColor: COLORS.line,
        backgroundColor: "transparent",
      },
      {
        label: "کران بالای بازه اطمینان",
        data: upper,
        borderColor: COLORS.band,
        backgroundColor: COLORS.band,
        fill: "+1",
        borderDash: [4, 4],
      },
      {
        label: "کران پایین",
        data: lower,
        borderColor: COLORS.band,
        backgroundColor: COLORS.band,
        fill: false,
        borderDash: [4, 4],
      },
    ],
    opts
  );
}

export function barChart(canvasId, labels, values, label, opts = {}) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === "undefined") return null;
  if (el.chart) el.chart.destroy();
  const t = themeColors();
  el.chart = new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label, data: values, backgroundColor: opts.color || COLORS.line }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: t.text } }, tooltip: { rtl: true } },
      scales: {
        x: { ticks: { color: t.text }, grid: { color: t.grid } },
        y: { ticks: { color: t.text }, grid: { color: t.grid } },
      },
    },
  });
  return el.chart;
}
