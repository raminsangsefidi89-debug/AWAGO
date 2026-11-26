/** AWAGO v2 dashboard entry: theme, nav, router registration. */
import { apiGet } from "./core/api.js";
import { faDate } from "./core/format.js";
import { startRouter, route, navigate } from "./core/router.js";
import { badge, esc } from "./core/ui.js";
import { comparePage, overviewPage, pairPage, qualityPage } from "./pages/pages_core.js";
import {
  backtestsPage,
  evaluationPage,
  jobsPage,
  modelsPage,
  settingsPage,
} from "./pages/pages_ml.js";

// ---- theme (localStorage preference; reduced-motion respected in charts) ----
const savedTheme = localStorage.getItem("awago-theme") || "dark";
document.body.dataset.theme = savedTheme;
const themeToggle = document.getElementById("themeToggle");
function syncThemeIcon() {
  if (themeToggle) themeToggle.textContent = document.body.dataset.theme === "light" ? "🌙" : "☀️";
}
syncThemeIcon();
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const next = document.body.dataset.theme === "light" ? "dark" : "light";
    document.body.dataset.theme = next;
    localStorage.setItem("awago-theme", next);
    syncThemeIcon();
  });
}

// ---- health badge + demo banner ----
async function refreshHealth() {
  const el = document.getElementById("healthBadge");
  try {
    const h = await apiGet("/api/v1/health");
    if (el) {
      el.textContent = h.status === "ok" ? "سرویس فعال" : "خطای سرویس";
      el.className = `badge badge-${h.status === "ok" ? "ok" : "err"}`;
      el.title = `منبع داده: ${h.data_source}`;
    }
    const banner = document.getElementById("demoBanner");
    if (banner) banner.hidden = !(h.is_demo_data ?? true);
    const upd = document.getElementById("heroLastUpdate");
    if (upd) upd.textContent = faDate(h.last_bar_time);
    const src = document.getElementById("heroSource");
    if (src) src.textContent = h.data_source === "demo" ? "داده آزمایشی (Demo)" : h.data_source;
  } catch {
    if (el) {
      el.textContent = "سرویس در دسترس نیست";
      el.className = "badge badge-err";
    }
  }
}
refreshHealth();

// ---- routes (deep links: #/pair/EUR-USD etc.) ----
const mount = document.getElementById("page");
route("", overviewPage);
route("overview", overviewPage);
route("pair/:symbol", pairPage);
route("compare", comparePage);
route("models", modelsPage);
route("evaluation", evaluationPage);
route("backtests", backtestsPage);
route("quality", qualityPage);
route("jobs", jobsPage);
route("settings", settingsPage);

function fallback(params, el) {
  el.innerHTML = `
    <h2>صفحه پیدا نشد</h2>
    <div class="empty-state">
      <p>مسیر نامعتبر است — به <a href="#/overview">نمای کلی</a> بروید.</p>
    </div>`;
  return {};
}

startRouter(mount, fallback);
