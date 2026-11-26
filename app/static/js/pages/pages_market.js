/**
 * Gold & Dollar / News / Drivers pages (addendum E).
 * Iranian RTL market view: global + unofficial Iran quotes side by side,
 * derived series (bubble/gap/implied), toman/rial toggle, news feed with
 * honesty badges, news-value verdict, driver analysis.
 */
import { apiGet } from "../core/api.js";
import {
  skeleton,
  honestyBadges,
  table,
  badge,
  esc,
  emptyBox,
  errorBox,
  verbatimNote,
} from "../core/ui.js";
import { faNumber, faPercent, faDateTime, faDigits } from "../core/format.js";

const UNOFFICIAL = `<span class="badge warn">قیمت بازار غیررسمی (unofficial market quote)</span>`;
const DISCLAIMER =
  "Educational and analytical use only. Not financial advice. قیمت‌های بازار ایران «نرخ غیررسمی» هستند.";

function quoteCard(q, { preferToman = true } = {}) {
  const unitLabel =
    q.unit && (q.unit.currency === "IRR" || q.unit.currency === "TOMAN")
      ? preferToman
        ? "تومان"
        : "ریال"
      : q.unit_label_fa || "";
  let val = q.value;
  if (q.unit && preferToman && q.unit.currency === "IRR") val = q.value / 10;
  if (q.unit && !preferToman && q.unit.currency === "TOMAN") val = q.value * 10;
  return `<article class="card">
    <h4>${esc(q.name_fa)} ${q.is_unofficial ? UNOFFICIAL : ""}</h4>
    <p class="metric">${faNumber(val, val > 1000 ? 0 : 2)} <small>${esc(unitLabel)}</small></p>
    <p class="meta">
      ${q.is_demo ? badge("Demo", "warn") : badge("واقعی", "ok")}
      ${badge(q.age_minutes > 240 ? "stale" : "تازه", q.age_minutes > 240 ? "warn" : "ok")}
      <span>منبع: ${esc((q.sources || []).join("، "))}</span>
      <span>زمان داده: ${faDateTime(q.as_of)}</span>
      ${q.dispersion_pct != null ? `<span>اختلاف منابع: ${faPercent(q.dispersion_pct)}</span>` : ""}
    </p>
  </article>`;
}

export async function marketsPage(_params, mount) {
  mount.innerHTML = `<h2>طلا و دلار</h2>${skeleton(5)}`;
  const preferToman = localStorage.getItem("awago_prefer_toman") !== "false";
  try {
    const doc = await apiGet(
      `/api/v1/markets/overview?prefer_toman=${preferToman ? "true" : "false"}`
    );
    const g = doc.global;
    const ir = doc.iran;
    const d = doc.derived;
    const warnHtml = (doc.warnings || [])
      .map(
        (w) =>
          `<p class="callout warn">${badge("هشدار کیفیت", "warn")} ${esc(
            w.message
          )} ${w.deviation_pct != null ? `(${faPercent(w.deviation_pct)})` : ""}</p>`
      )
      .join("");
    mount.innerHTML = `
      <h2>طلا و دلار</h2>
      <div class="toolbar">
        <label>نمایش مبالغ:
          <button id="unit-toggle" class="btn">${preferToman ? "تومان" : "ریال"} (تغییر)</button>
        </label>
      </div>
      ${honestyBadges({
        source: "demo",
        isDemo: doc.data_mode === "demo",
        lastUpdate: doc.generated_at,
      })}
      ${warnHtml}
      <section class="card">
        <h3>بازار جهانی</h3>
        <div class="features">${quoteCard(g.gold, { preferToman })}
          ${g.dollar_index ? quoteCard(g.dollar_index, { preferToman }) : ""}
          ${(g.basket || []).map((q) => quoteCard(q, { preferToman })).join("")}</div>
        <h4>محرک‌ها</h4>
        <div class="features">${(g.drivers || []).map((q) => quoteCard(q, { preferToman })).join("")}</div>
      </section>
      <section class="card">
        <h3>بازار ایران ${UNOFFICIAL}</h3>
        <p class="meta">${esc(ir.unofficial_badge)}</p>
        <div class="features">
          ${quoteCard(ir.usd_free, { preferToman })}
          ${quoteCard(ir.usd_official, { preferToman })}
          ${quoteCard(ir.gold18, { preferToman })}
          ${quoteCard(ir.coin_full, { preferToman })}
          ${quoteCard(ir.coin_half, { preferToman })}
          ${quoteCard(ir.coin_quarter, { preferToman })}
          ${quoteCard(ir.usdt, { preferToman })}
        </div>
      </section>
      <section class="card">
        <h3>سری‌های مشتق‌شده</h3>
        <p class="meta">فرمول‌ها ثبت شده‌اند؛ اختلاف‌ها «هشدار» داده می‌شوند و هرگز خودکار اصلاح نمی‌شوند.</p>
        ${table(
          ["سری", "مقدار", "واحد", "فرمول"],
          [
            [
              "ارزش ضمنی هر گرم طلا از بازار جهانی",
              faNumber(d.implied_gram_irr.display[0], 0),
              esc(d.implied_gram_irr.display[2]),
              faDigits(d.implied_gram_irr.formula),
            ],
            [
              "ارزش ضمنی طلای ۱۸ عیار",
              faNumber(d.implied_gram_irr_18k.display[0], 0),
              esc(d.implied_gram_irr_18k.display[2]),
              faDigits(d.implied_gram_irr_18k.formula),
            ],
            [
              "ارزش ذاتی سکه امامی",
              faNumber(d.coin_intrinsic_irr.display[0], 0),
              esc(d.coin_intrinsic_irr.display[2]),
              faDigits(d.coin_intrinsic_irr.formula),
            ],
            [
              "حباب سکه امامی",
              faNumber(d.coin_bubble.bubble_irr, 0),
              `${faPercent(d.coin_bubble.bubble_pct)}`,
              "بازار − ذاتی",
            ],
            [
              "شکاف دلار آزاد/رسمی",
              faNumber(d.usd_gap.gap_irr, 0),
              faPercent(d.usd_gap.gap_pct),
              "(آزاد − رسمی)/رسمی",
            ],
          ],
          { numeric: [1] }
        )}
      </section>
      ${verbatimNote(DISCLAIMER)}`;
    mount.querySelector("#unit-toggle").addEventListener("click", () => {
      localStorage.setItem("awago_prefer_toman", preferToman ? "false" : "true");
      marketsPage(_params, mount);
    });
  } catch (err) {
    mount.innerHTML = `<h2>طلا و دلار</h2>${errorBox(err.message)}`;
  }
}

export async function newsPage(_params, mount) {
  mount.innerHTML = `<h2>اخبار و اقتصاد</h2>${skeleton(3)}`;
  try {
    const [feed, value] = await Promise.allSettled([
      apiGet("/api/v1/markets/news"),
      apiGet("/api/v1/markets/news/value"),
    ]);
    const f = feed.status === "fulfilled" ? feed.value : { items: [] };
    const rows = (f.items || []).map((it) => [
      it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>` : esc(it.title),
      esc(it.source),
      esc((it.topics || []).join("، ")),
      it.sentiment > 0 ? badge("مثبت", "ok") : it.sentiment < 0 ? badge("منفی", "warn") : badge("خنثی", "muted"),
      it.is_demo ? badge("Demo", "warn") : badge("خبر", "ok"),
      faDateTime(it.available_at),
    ]);
    let verdictHtml = emptyBox("آزمون ارزش خبر هنوز اجرا نشده است.");
    if (value.status === "fulfilled" && value.value) {
      verdictHtml = `
        <p class="meta">${esc(value.value.method)}</p>
        ${table(
          ["ابزار", "افق", "MAE با خبر", "MAE بدون خبر", "DM stat", "نتیجه"],
          (value.value.verdicts || []).map((v) => [
            esc(v.instrument),
            faNumber(v.horizon, 0),
            faNumber(v.mae_with, 4),
            faNumber(v.mae_without, 4),
            v.dm_stat == null ? "—" : faNumber(v.dm_stat, 2),
            badge(v.verdict, v.verdict.includes("improve") ? "ok" : "muted"),
          ]),
          { numeric: [1, 2, 3, 4] }
        )}
        <p class="meta">${esc(value.value.policy)}</p>`;
    }
    mount.innerHTML = `
      <h2>اخبار و اقتصاد</h2>
      ${honestyBadges({ source: (f.active_sources || []).join("، ") || "—", isDemo: true, lastUpdate: f.last_successful_fetch })}
      <p class="callout">${esc(f.coverage_note || "")}</p>
      <section class="card">
        <h3>فید خبر</h3>
        ${rows.length ? table(["تیتر", "منبع", "موضوع‌ها", "حس", "نوع", "در دسترس از"], rows) : emptyBox("خبری دریافت نشده است.")}
      </section>
      <section class="card">
        <h3>حکم ارزش خبر (با خبر در برابر بدون خبر)</h3>
        ${verdictHtml}
      </section>
      ${verbatimNote(DISCLAIMER)}`;
  } catch (err) {
    mount.innerHTML = `<h2>اخبار و اقتصاد</h2>${errorBox(err.message)}`;
  }
}

export async function driversPage(_params, mount) {
  mount.innerHTML = `<h2>تحلیل محرک‌ها</h2>${skeleton(3)}`;
  try {
    const doc = await apiGet("/api/v1/markets/drivers?instrument=XAU_USD");
    const rows = Object.entries(doc.series || {}).map(([name, s]) => [
      esc(name),
      faNumber(s.rolling_corr, 3),
      faNumber(s.lead_lag.best_lag, 0),
      faNumber(s.lead_lag.best_corr, 3),
    ]);
    const regRows = Object.entries(doc.regime_dependence || {}).map(([r, c]) => [
      esc(r),
      faNumber(c, 3),
    ]);
    mount.innerHTML = `
      <h2>تحلیل محرک‌ها</h2>
      ${honestyBadges({ source: "demo", isDemo: doc.data_mode === "demo", lastUpdate: null })}
      <p class="callout warn">${esc(doc.caution || "")}</p>
      <section class="card">
        <h3>همبستگی غلتان و سر-و-تاخیر (XAU/USD)</h3>
        ${table(["محرک", "همبستگی غلتان", "بهترین تاخیر", "همبستگی در تاخیر"], rows, { numeric: [1, 2, 3] })}
      </section>
      <section class="card">
        <h3>وابستگی به رژیم بازار</h3>
        ${table(["رژیم", "همبستگی"], regRows, { numeric: [1] })}
      </section>
      <section class="card">
        <h3>اهمیت ویژگی (جایگذاری تصادفی)</h3>
        ${table(
          ["ویژگی", "اهمیت (کاهش MAE)"],
          (doc.permutation_importance || []).map((p) => [esc(p.feature), faNumber(p.importance, 4)]),
          { numeric: [1] }
        )}
      </section>
      ${verbatimNote(DISCLAIMER)}`;
  } catch (err) {
    mount.innerHTML = `<h2>تحلیل محرک‌ها</h2>${errorBox(err.message)}`;
  }
}
