/** Pages: Models, Evaluation, Backtests, Jobs, Settings. */
import { apiGet, apiPost } from "../core/api.js";
import { barChart } from "../core/charts.js";
import { faDateTime, faNumber, faPercent } from "../core/format.js";
import {
  badge,
  emptyBox,
  errorBox,
  esc,
  honestyBadges,
  skeleton,
  table,
  toast,
  verbatimNote,
} from "../core/ui.js";

const DISCLAIMER = "Educational and analytical use only. Not financial advice.";
const DEF_CAUTION =
  "With many models/horizons tried, the best observed Sharpe is biased upward (selection on noise).";

export async function modelsPage(_params, mount) {
  mount.innerHTML = `<h2>مدل‌ها</h2>${skeleton(4)}`;
  try {
    const [catalog, artifacts] = await Promise.all([
      apiGet("/api/v1/registry/models"),
      apiGet("/api/v1/registry/artifacts"),
    ]);
    const rows = (catalog.models || []).map((m) => [
      esc(m.name),
      esc(m.kind),
      m.available ? badge("در دسترس", "ok") : badge("در دسترس نیست", "warn"),
      m.available ? esc(m.description) : esc(m.unavailable_reason),
    ]);
    const champions = Object.entries(artifacts.champions || {}).map(([k, v]) => {
      const [pair, horizon] = k.split("|");
      return [esc(pair), faNumber(horizon, 0), esc(v)];
    });
    const events = (artifacts.recent_events || []).slice(-10).reverse().map((e) => [
      esc(e.event),
      esc(e.pair || ""),
      esc(e.model || e.champion || e.name || ""),
      faDateTime(e.at),
    ]);
    mount.innerHTML = `
      <h2>مدل‌ها</h2>
      <section class="card">
        <h3>کاتالوگ مدل‌ها (ثبت‌شده در registry)</h3>
        ${table(["نام", "خانواده", "وضعیت", "توضیح / دلیل عدم دسترس"], rows)}
      </section>
      <section class="card">
        <h3>قهرمانان فعلی (champion)</h3>
        ${champions.length ? table(["جفت‌ارز", "افق", "مدل قهرمان"], champions, { numeric: [1] }) : emptyBox("هنوز قهرمانی انتخاب نشده است.")}
      </section>
      <section class="card">
        <h3>رهگیری ممیزی (audit trail)</h3>
        ${events.length ? table(["رویداد", "جفت‌ارز", "مدل", "زمان"], events) : emptyBox("رویدادی ثبت نشده است.")}
      </section>
      ${verbatimNote("تغییر قهرمان فقط با آزمون معناداری آماری یا ثبت دستیِ ممیزی‌شده انجام می‌شود.")}`;
  } catch (err) {
    mount.innerHTML = `<h2>مدل‌ها</h2>${errorBox(err.message)}`;
  }
}

export async function evaluationPage(_params, mount) {
  mount.innerHTML = `<h2>ارزیابی</h2>${skeleton(5)}`;
  try {
    const board = await apiGet("/api/v1/leaderboards/latest");
    const rows = (board.rows || []).map((r) => [
      esc(r.pair_symbol),
      faNumber(r.target_horizon, 0),
      esc(r.model_name),
      faNumber(r.mae, 5),
      faNumber(r.rmse, 5),
      faPercent(r.directional_accuracy ? r.directional_accuracy * 100 : null, 1),
      r.dm_p_holm !== null && r.dm_p_holm !== undefined ? faNumber(r.dm_p_holm, 4) : "—",
      badge(r.verdict, r.verdict.includes("(yardstick)") ? "muted" : r.beats_baseline ? "ok" : "warn"),
    ]);
    const cov = (board.coverage || []).slice(0, 24).map((c) => [
      esc(c.pair_symbol),
      faNumber(c.target_horizon, 0),
      esc(c.method),
      faPercent(c.nominal_level * 100, 0),
      faPercent(c.empirical_coverage * 100, 1),
      faNumber(c.mean_width, 5),
      faNumber(c.n, 0),
    ]);
    mount.innerHTML = `
      <h2>ارزیابی مدل‌ها</h2>
      ${honestyBadges({
        source: "walk-forward",
        isDemo: true,
        lastUpdate: board.generated_at,
        modelVersion: `run ${String(board.run_id || "").slice(0, 12)}`,
      })}
      <section class="card">
        <h3>جدول رتبه‌بندی (run: ${esc(String(board.run_id || "").slice(0, 16))})</h3>
        ${table(
          ["جفت‌ارز", "افق", "مدل", "MAE", "RMSE", "دقت جهت", "p (Holm)", "نتیجه"],
          rows,
          { numeric: [1, 3, 4, 5, 6] }
        )}
      </section>
      <section class="card">
        <h3>کالیبراسیون بازه اطمینان: اسمی در برابر تجربی</h3>
        ${cov.length ? table(
          ["جفت‌ارز", "افق", "روش", "سطح اسمی", "پوشش تجربی", "میانگین عرض", "n"],
          cov,
          { numeric: [1, 3, 4, 5, 6] }
        ) : emptyBox("داده کالیبراسیون موجود نیست.")}
      </section>
      ${verbatimNote(
        "نتایج از ارزیابی واک‌فوروارد با purging به دست آمده‌اند؛ p-value ها با تصحیح چندمقایسه‌ای (Holm) گزارش می‌شوند. " + DISCLAIMER
      )}`;
  } catch (err) {
    mount.innerHTML = `<h2>ارزیابی</h2>${errorBox(err.message)}`;
  }
}

export async function backtestsPage(_params, mount) {
  mount.innerHTML = `<h2>بک‌تست (شبیه‌سازی)</h2>${skeleton(3)}`;
  try {
    const pairs = await apiGet("/api/v1/pairs");
    const options = (pairs.items || [])
      .map((p) => `<option value="${esc(p.symbol.replace("/", "-"))}">${esc(p.symbol)}</option>`)
      .join("");
    mount.innerHTML = `
      <h2>بک‌تست — شبیه‌سازی آموزشی</h2>
      <section class="card">
        <div class="controls">
          <label class="field"><span>جفت‌ارز</span><select id="btPair">${options}</select></label>
          <label class="field"><span>افق (روز)</span><input id="btHorizon" type="number" value="7" min="1" max="90"></label>
          <label class="field"><span>کارمزد (bps)</span><input id="btCost" type="number" value="1" min="0" max="100"></label>
          <label class="field"><span>لغزش (bps)</span><input id="btSlip" type="number" value="0.5" min="0" max="100"></label>
          <button id="btRun" class="btn btn-primary" type="button">اجرای شبیه‌سازی</button>
        </div>
      </section>
      <section class="card" id="btResult">${emptyBox("پارامترها را انتخاب کنید و اجرا کنید.")}</section>`;
    mount.querySelector("#btRun").addEventListener("click", async () => {
      const out = mount.querySelector("#btResult");
      out.innerHTML = skeleton(3);
      try {
        const res = await apiGet(`/api/v1/backtests/${mount.querySelector("#btPair").value}`, {
          horizon: mount.querySelector("#btHorizon").value,
          cost_bps: mount.querySelector("#btCost").value,
          slippage_bps: mount.querySelector("#btSlip").value,
        });
        const rows = [
          ["استراتژی (نشانه پیش‌بینی)", res.strategy],
          ["خرید و نگهداری", res.buy_and_hold],
          ["کنترل تصادفی", res.random_control],
        ].map(([name, s]) => [
          name,
          faPercent(s.total_return * 100, 2),
          faNumber(s.annualized_sharpe, 2),
          faPercent(s.max_drawdown * 100, 2),
          faPercent(s.hit_rate * 100, 1),
        ]);
        out.innerHTML = `
          ${honestyBadges({ source: "شبیه‌سازی", isDemo: true, verdict: res.verdict_vs_random })}
          ${table(["سناریو", "بازده کل", "شارپ سالانه", "افت قیمتی", "نرخ موفقیت"], rows, { numeric: [1, 2, 3, 4] })}
          <p>تعداد معاملات: ${faNumber(res.n_trades, 0)} · موقعیت: ${esc(res.position)}</p>
          <div class="warn-box" role="note"><strong>⚠️ هشدار</strong><p>${esc(res.deflated_sharpe_caution)}</p></div>
          ${verbatimNote(res.disclaimer)}`;
      } catch (err) {
        out.innerHTML = errorBox(err.message + " — ابتدا یک آزمون (experiment) اجرا کنید تا پیش‌بینی‌های واک‌فوروارد ذخیره شوند.");
      }
    });
  } catch (err) {
    mount.innerHTML = `<h2>بک‌تست</h2>${errorBox(err.message)}`;
  }
}

export async function jobsPage(_params, mount) {
  mount.innerHTML = `<h2>کارها</h2>${skeleton(3)}`;
  const render = async () => {
    try {
      const jobs = await apiGet("/api/v1/jobs", { limit: 25 });
      const rows = (jobs.items || []).map((j) => [
        esc(String(j.id).slice(0, 8)),
        esc(j.type),
        badge(
          { queued: "در صف", running: "در حال اجرا", done: "پایان", failed: "خطا", cancelled: "لغو شد" }[j.status] || j.status,
          j.status === "done" ? "ok" : j.status === "failed" ? "err" : j.status === "running" ? "info" : "muted"
        ),
        faPercent((j.progress || 0) * 100, 0),
        esc(j.message || ""),
        faDateTime(j.created_at),
      ]);
      mount.querySelector("#jobsTable").innerHTML = table(
        ["شناسه", "نوع", "وضعیت", "پیشرفت", "پیام", "زمان"],
        rows,
        { numeric: [3] }
      );
    } catch (err) {
      mount.querySelector("#jobsTable").innerHTML = errorBox(err.message);
    }
  };
  mount.innerHTML = `
    <h2>کارها</h2>
    <section class="card">
      <div class="controls">
        <button id="jobCollect" class="btn" type="button">جمع‌آوری داده</button>
        <button id="jobTrain" class="btn" type="button">آموزش سریع</button>
        <button id="jobExp" class="btn btn-primary" type="button">آزمون کامل (experiment)</button>
        <button id="jobRefresh" class="btn btn-ghost" type="button">تازه‌سازی</button>
      </div>
    </section>
    <section class="card"><div id="jobsTable">${skeleton(3)}</div></section>
    <p class="fine-print">کارها در صف محلی اجرا می‌شوند (حداکثر ۲ به‌طور همزمان)؛ قابل لغو هستند و تاریخچه‌شان پایدار است.</p>`;
  mount.querySelector("#jobRefresh").addEventListener("click", render);
  mount.querySelector("#jobCollect").addEventListener("click", async () => {
    await apiPost("/api/v1/jobs/collect-data", {});
    toast("کار جمع‌آوری داده در صف قرار گرفت");
    render();
  });
  mount.querySelector("#jobTrain").addEventListener("click", async () => {
    await apiPost("/api/v1/jobs/train", { quick: true });
    toast("آموزش سریع در صف قرار گرفت");
    render();
  });
  mount.querySelector("#jobExp").addEventListener("click", async () => {
    await apiPost("/api/v1/experiments/run", { quick: true });
    toast("آزمون در صف قرار گرفت");
    render();
  });
  await render();
}

export async function settingsPage(_params, mount) {
  mount.innerHTML = `<h2>تنظیمات</h2>${skeleton(3)}`;
  try {
    const features = await apiGet("/api/v1/features");
    const stored = {
      theme: localStorage.getItem("awago-theme") || "dark",
      defaultPair: localStorage.getItem("awago-pair") || "EUR-USD",
    };
    mount.innerHTML = `
      <h2>تنظیمات</h2>
      <section class="card">
        <h3>ترجیحات نمایش</h3>
        <div class="controls">
          <label class="field"><span>تم</span>
            <select id="setTheme">
              <option value="dark"${stored.theme === "dark" ? " selected" : ""}>تیره</option>
              <option value="light"${stored.theme === "light" ? " selected" : ""}>روشن</option>
            </select>
          </label>
          <label class="field"><span>جفت‌ارز پیش‌فرض</span>
            <input id="setPair" value="${esc(stored.defaultPair)}">
          </label>
          <button id="setSave" class="btn btn-primary" type="button">ذخیره</button>
        </div>
      </section>
      <section class="card">
        <h3>مجموعه ویژگی‌ها (${esc(features.name)} — نسخه ${esc(features.version)})</h3>
        ${table(
          ["نام", "گروه", "حداقل داده لازم", "توضیح"],
          (features.features || []).map((f) => [esc(f.name), esc(f.group), faNumber(f.lookback, 0), esc(f.description)]),
          { numeric: [2] }
        )}
        <p class="fine-print">${esc(features.point_in_time || "")}</p>
      </section>
      <section class="card">
        <h3>منابع داده</h3>
        <p>پیش‌فرض: داده آزمایشی (Demo). برای داده واقعی، <code>DATA_MODE=live</code> را در فایل <code>.env</code> تنظیم کنید و صحت را از صفحه «کیفیت داده» بررسی نمایید. کلیدهای API فقط در <code>.env</code> نگهداری می‌شوند.</p>
      </section>`;
    mount.querySelector("#setSave").addEventListener("click", () => {
      localStorage.setItem("awago-theme", mount.querySelector("#setTheme").value);
      localStorage.setItem("awago-pair", mount.querySelector("#setPair").value);
      document.body.dataset.theme = mount.querySelector("#setTheme").value;
      toast("ترجیحات ذخیره شد");
    });
  } catch (err) {
    mount.innerHTML = `<h2>تنظیمات</h2>${errorBox(err.message)}`;
  }
}
