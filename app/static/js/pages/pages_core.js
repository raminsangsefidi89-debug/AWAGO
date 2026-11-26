/** Pages: Overview, Pair Detail, Compare, Data Quality. */
import { apiGet } from "../core/api.js";
import { barChart, fanChart, lineChart } from "../core/charts.js";
import { faDate, faDateTime, faNumber } from "../core/format.js";
import {
  badge,
  emptyBox,
  errorBox,
  esc,
  honestyBadges,
  skeleton,
  table,
  verbatimNote,
} from "../core/ui.js";
import { navigate } from "../core/router.js";

const DISCLAIMER = "Educational and analytical use only. Not financial advice.";

export async function overviewPage(_params, mount) {
  mount.innerHTML = `<h2>نمای کلی</h2>${skeleton(4)}`;
  try {
    const [health, board] = await Promise.allSettled([
      apiGet("/api/v1/health"),
      apiGet("/api/v1/leaderboards/latest"),
    ]);
    const pairs = await apiGet("/api/v1/pairs");
    const rows = (pairs.items || []).map((p) => [
      `<a href="#/pair/${encodeURIComponent(p.symbol)}">${esc(p.symbol)}</a>`,
      faNumber(p.last_close, 5),
      esc(p.name_fa || ""),
      p.is_demo ? badge("آزمایشی", "warn") : badge("واقعی", "ok"),
      faDate(p.last_bar_time),
    ]);
    let boardHtml = emptyBox("هنوز آزمونی اجرا نشده است — از صفحه «آزمایش‌ها» یا دکمه‌های «کارها» شروع کنید.");
    if (board.status === "fulfilled" && board.value) {
      const b = board.value;
      const top = (b.rows || []).slice(0, 8).map((r) => [
        esc(r.pair_symbol),
        faNumber(r.target_horizon, 0),
        esc(r.model_name),
        faNumber(r.mae, 5),
        badge(r.verdict, r.verdict.includes("baseline (yardstick)") ? "muted" : r.beats_baseline ? "ok" : "warn"),
      ]);
      boardHtml = table(["جفت‌ارز", "افق", "مدل", "MAE", "نتیجه"], top, { numeric: [1, 3] });
    }
    mount.innerHTML = `
      <h2>نمای کلی</h2>
      ${honestyBadges({
        source: health.status === "fulfilled" ? health.value.data_source : "نامشخص",
        isDemo: health.status === "fulfilled" ? health.value.is_demo_data : true,
        lastUpdate: health.status === "fulfilled" ? health.value.last_bar_time : null,
      })}
      <section class="card">
        <h3>جفت‌ارزها</h3>
        ${table(["نماد", "آخرین قیمت", "نام فارسی", "نوع داده", "آخرین داده"], rows, { numeric: [1] })}
      </section>
      <section class="card">
        <h3>آخرین جدول رتبه‌بندی (رهگیری پیش‌بینی واک‌فوروارد)</h3>
        ${boardHtml}
      </section>
      <section class="features" aria-label="قابلیت‌های کلیدی">
        <article class="card feature-card">
          <img src="/static/img/card-forecast.webp" onerror="this.onerror=null;this.src='/static/img/card-forecast.svg';" alt="تصویر پیش‌بینی چندافقی با بازه اطمینان" width="640" height="400" loading="lazy">
          <h3>پیش‌بینی چندافقی</h3>
          <p>پیش‌بینی با بازه اطمینان و نمودار پروبالی — همیشه با پوشش تجربی اندازه‌گیری‌شده، نه فقط سطح اسمی.</p>
        </article>
        <article class="card feature-card">
          <img src="/static/img/card-trend.webp" onerror="this.onerror=null;this.src='/static/img/card-trend.svg';" alt="تصویر تحلیل روند: خط روند روی نوسانات قیمت" width="640" height="400" loading="lazy">
          <h3>تحلیل روند و رژیم بازار</h3>
          <p>جهت، شیب و رژیم نوسانی بازار به‌صورت نقطه‌به‌زمان (point-in-time) محاسبه می‌شود — بدون نگاه به آینده.</p>
        </article>
        <article class="card feature-card">
          <img src="/static/img/card-evaluation.webp" onerror="this.onerror=null;this.src='/static/img/card-evaluation.svg';" alt="تصویر ارزیابی مدل: مقایسه منحنی مدل با خط پایه" width="640" height="400" loading="lazy">
          <h3>ارزیابی صادقانه</h3>
          <p>هر مدل با خط پایه مقایسه می‌شود و نتیجه آماری — از جمله «بهتر نیست» بودن — صادقانه نمایش داده می‌شود.</p>
        </article>
      </section>
      ${verbatimNote(DISCLAIMER)}`;
  } catch (err) {
    mount.innerHTML = `<h2>نمای کلی</h2>${errorBox(err.message)}`;
  }
}

export async function pairPage(params, mount) {
  const symbol = params.symbol || "EUR-USD";
  const pair = symbol.replace("-", "/");
  mount.innerHTML = `<h2>جزئیات جفت‌ارز ${esc(pair)}</h2>${skeleton(5)}`;
  try {
    const [history, quality, prob, vol] = await Promise.allSettled([
      apiGet(`/api/v1/pairs/${symbol}/history`, { days: 365 }),
      apiGet(`/api/v1/quality/${symbol}`),
      apiGet(`/api/v1/forecasts/probabilistic/${symbol}`, { horizon: 7, level: 0.9 }),
      apiGet(`/api/v1/volatility/${symbol}`, { horizon: 7 }),
    ]);
    const h = history.status === "fulfilled" ? history.value : null;
    const q = quality.status === "fulfilled" ? quality.value : null;
    const p = prob.status === "fulfilled" ? prob.value : null;
    const v = vol.status === "fulfilled" ? vol.value : null;

    const labels = (h?.items || []).map((b) => faDate(b.timestamp));
    const closes = (h?.items || []).map((b) => b.close);

    let fanHtml = emptyBox("پیش‌بینی در دسترس نیست.");
    if (p) {
      fanHtml = `
        <div class="chart-box"><canvas id="fanChart" role="img" aria-label="نمودار پروبالی پیش‌بینی با بازه اطمینان"></canvas></div>
        <p>روش: ${esc(p.method)} · پوشش تجربی ${faNumber(p.empirical_coverage_on_wf * 100, 1)}٪ در برابر سطح اسمی ${faNumber(p.nominal_level * 100, 0)}٪</p>
        ${verbatimNote(p.caveat || "")}`;
    }

    mount.innerHTML = `
      <h2>جزئیات ${esc(pair)}</h2>
      ${honestyBadges({
        source: h ? h.data_source : "نامشخص",
        isDemo: q ? q.is_demo : true,
        lastUpdate: h?.items?.length ? h.items[h.items.length - 1].timestamp : null,
        calibration: p ? `${faNumber(p.empirical_coverage_on_wf * 100, 1)}٪ تجربی` : null,
      })}
      <section class="card">
        <h3>قیمت (۳۶۵ روز اخیر)</h3>
        <div class="chart-box"><canvas id="priceChart" role="img" aria-label="نمودار قیمت"></canvas></div>
        <div class="controls">
          <a class="btn" href="/api/v1/pairs/${symbol}/export?format=csv" download>دریافت CSV</a>
          <a class="btn" href="/api/v1/pairs/${symbol}/export?format=parquet" download>دریافت Parquet</a>
        </div>
      </section>
      <section class="card">
        <h3>پیش‌بینی احتمالی ۷ روزه (نمودار پروبالی)</h3>
        ${fanHtml}
      </section>
      <section class="card">
        <h3>کیفیت داده</h3>
        ${q ? table(["بررسی", "نتیجه"], [
          ["شکاف‌ها", faNumber(q.gaps.missing_count, 0)],
          ["کهنه‌بودن", q.stale.is_stale ? badge("کهنه", "warn") : badge("تازه", "ok")],
          ["پرت‌ها", faNumber(q.outliers.outlier_count, 0)],
          ["اعتبار OHLC", q.ohlc_validation.valid ? badge("معتبر", "ok") : badge("نامعتبر", "err")],
          ["وضعیت", esc(q.summary.status)],
        ], { numeric: [1] }) : emptyBox("گزارش کیفیت در دسترس نیست.")}
      </section>
      <section class="card">
        <h3>نوسانات</h3>
        ${v ? table(["روش", "سیگما h", "نوسان ۲۰ روزه"], [[esc(v.method), faNumber(v.sigma_h, 5), faNumber(v.realized_vol_20d, 5)]], { numeric: [1, 2] }) : emptyBox("—")}
        ${v ? verbatimNote(v.detail + " " + DISCLAIMER) : ""}
      </section>`;

    if (h?.items?.length) {
      lineChart("priceChart", labels, [
        { label: "قیمت بسته‌شدن", data: closes, borderColor: "#4f8cff" },
      ]);
    }
    if (p) fanChart("fanChart", p.fan_chart);
  } catch (err) {
    mount.innerHTML = `<h2>جزئیات جفت‌ارز</h2>${errorBox(err.message)}`;
  }
}

export async function comparePage(_params, mount) {
  mount.innerHTML = `<h2>مقایسه جفت‌ارزها</h2>${skeleton(3)}`;
  try {
    const pairs = await apiGet("/api/v1/pairs");
    const symbols = (pairs.items || []).slice(0, 6).map((p) => p.symbol);
    const histories = await Promise.allSettled(
      symbols.map((s) => apiGet(`/api/v1/pairs/${s.replace("/", "-")}/history`, { days: 180 }))
    );
    const datasets = [];
    let labels = [];
    histories.forEach((res, i) => {
      if (res.status !== "fulfilled" || !res.value?.items?.length) return;
      const items = res.value.items;
      const base = items[0].close;
      if (!labels.length) labels = items.map((b) => faDate(b.timestamp));
      datasets.push({
        label: symbols[i],
        data: items.map((b) => (b.close / base) * 100),
      });
    });
    mount.innerHTML = `
      <h2>مقایسه جفت‌ارزها (شاخص نرمال‌شده، مبدأ ۱۰۰)</h2>
      <section class="card">
        <div class="chart-box chart-tall"><canvas id="cmpChart" role="img" aria-label="مقایسه عملکرد نرمال‌شده جفت‌ارزها"></canvas></div>
      </section>
      ${verbatimNote("مقایسه توصیفی است؛ بازده گذشته نشان‌دهنده بازده آینده نیست. " + DISCLAIMER)}`;
    if (datasets.length) lineChart("cmpChart", labels, datasets);
  } catch (err) {
    mount.innerHTML = `<h2>مقایسه</h2>${errorBox(err.message)}`;
  }
}

export async function qualityPage(_params, mount) {
  mount.innerHTML = `<h2>کیفیت داده</h2>${skeleton(4)}`;
  try {
    const [providers, pairs] = await Promise.all([apiGet("/api/v1/providers"), apiGet("/api/v1/pairs")]);
    const first = (pairs.items || [])[0];
    let reportHtml = emptyBox("جفت‌ارزی برای بررسی موجود نیست.");
    if (first) {
      const q = await apiGet(`/api/v1/quality/${first.symbol.replace("/", "-")}`, { refresh: true });
      reportHtml = table(["بررسی", "نتیجه"], [
        ["جفت‌ارز", esc(q.pair_symbol)],
        ["منبع داده", esc(q.data_source)],
        ["تعداد ردیف", faNumber(q.row_count, 0)],
        ["شکاف (روز کاری)", faNumber(q.gaps.missing_count, 0)],
        ["پرت (Hampel)", faNumber(q.outliers.outlier_count, 0)],
        ["OHLC", q.ohlc_validation.valid ? badge("معتبر", "ok") : badge("نامعتبر", "err")],
        ["مثلثی (cross-rate)", q.triangular_consistency.applicable ? badge("اجرا شد", "info") : badge("غیرقابل اجرا روی داده آزمایشی", "muted")],
        ["وضعیت", esc(q.summary.issues.join("؛ ") || "تمیز")],
      ], { numeric: [2, 3, 4] });
    }
    const provRows = (providers.providers || []).map((p) => [
      esc(p.name),
      p.verified_live ? badge("تأیید شده", "ok") : badge("تأیید نشده در محیط ساخت", "warn"),
      p.is_demo ? badge("آزمایشی", "warn") : badge("واقعی/فایل", "info"),
      esc(p.license_notes),
    ]);
    mount.innerHTML = `
      <h2>کیفیت داده</h2>
      <section class="card">
        <h3>گزارش کیفیت (${esc(first ? first.symbol : "—")})</h3>
        ${reportHtml}
      </section>
      <section class="card">
        <h3>ارائه‌دهندگان داده</h3>
        ${table(["نام", "وضعیت تأیید", "نوع", "یادداشت مجوز"], provRows)}
        <p class="fine-print">${esc(providers.note || "")}</p>
      </section>`;
  } catch (err) {
    mount.innerHTML = `<h2>کیفیت داده</h2>${errorBox(err.message)}`;
  }
}
