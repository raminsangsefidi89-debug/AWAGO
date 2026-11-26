"""Persian RTL print-friendly HTML report — computed outputs only.

HARD RULE: every number in the report comes from a stored artifact
(leaderboard JSON, quality report, backtest result). The generator never
computes new metrics and never invents figures; missing sections render as
"گزارش نشده" (not reported) rather than estimates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.services.jalali import digits_fa, format_jalali_long_fa

logger = get_logger(__name__)

DISCLAIMER_EN = "Educational and analytical use only. Not financial advice."
DISCLAIMER_FA = (
    "⚠️ این گزارش صرفاً برای مقاصد آموزشی و تحلیلی است و توصیه مالی یا معاملاتی محسوب نمی‌شود. "
    "شبیه‌سازی‌های بک‌تست با کارمزد و لغزش مدل‌سازی شده‌اند؛ عملکرد گذشته نشان‌دهنده نتایج آینده نیست."
)


def _fa(value: Any, digits: int = 6) -> str:
    if value is None:
        return "گزارش نشده"
    try:
        if isinstance(value, float):
            if value != value:  # NaN
                return "گزارش نشده"
            text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
        else:
            text = str(value)
    except (TypeError, ValueError):
        text = str(value)
    return digits_fa(text)


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  font-family: Vazirmatn, Tahoma, sans-serif;
  direction: rtl;
  margin: 0;
  padding: 2rem;
  background: #f7f9fc;
  color: #16233b;
  line-height: 1.9;
}
h1 { font-size: 1.6rem; margin: 0 0 0.35rem; }
h2 { font-size: 1.2rem; border-bottom: 2px solid #d7e0ee; padding-bottom: 0.45rem; margin-top: 2.1rem; }
h3 { font-size: 1.02rem; margin-top: 1.45rem; }
.meta { color: #5a6b85; font-size: 0.88rem; }
table { border-collapse: collapse; width: 100%; margin: 0.85rem 0; font-size: 0.88rem; }
th, td { border: 1px solid #d7e0ee; padding: 0.5rem 0.75rem; text-align: right; }
th { background: #eaf0f9; }
td.num, th.num { text-align: left; direction: ltr; font-variant-numeric: tabular-nums; }
.badge { display: inline-block; padding: 0.18rem 0.7rem; border-radius: 999px; font-size: 0.78rem; margin: 0.12rem; }
.b-ok { background: #e2f6e8; color: #157a3c; }
.b-warn { background: #fdf1d7; color: #8a6116; }
.b-err { background: #fde5e5; color: #a12727; }
.b-muted { background: #e8ecf3; color: #55627a; }
.disclaimer { background: #fdf1d7; border: 1px solid #e6c778; border-radius: 10px; padding: 0.95rem 1.25rem; margin: 1.6rem 0; }
.disclaimer-en { direction: ltr; text-align: left; font-size: 0.8rem; color: #5a6b85; }
.badge-row { margin: 0.55rem 0 1.15rem; }
.fine-print { color: #5a6b85; font-size: 0.8rem; }
.page-break { page-break-before: always; }
@media print {
  body { padding: 0.6cm; background: #fff; }
  .page-break { page-break-before: always; }
  a { text-decoration: none; color: inherit; }
}
"""


def _badge(text: str, kind: str = "muted") -> str:
    return f'<span class="badge b-{kind}">{_esc(text)}</span>'


def _verdict_badge(verdict: str) -> str:
    if "yardstick" in verdict:
        kind = "muted"
    elif "significantly" in verdict and "not" not in verdict:
        kind = "ok"
    elif "worse" in verdict:
        kind = "err"
    else:
        kind = "warn"
    return _badge(verdict, kind)


def render_report(board: dict[str, Any], quality: dict[str, dict[str, Any]] | None = None) -> str:
    """Render the report HTML from a leaderboard doc (+ optional quality reports)."""
    quality = quality or {}
    generated = datetime.now(timezone.utc)
    rows_html = ""
    for row in board.get("rows", []):
        rows_html += (
            "<tr>"
            f"<td>{_esc(row.get('pair_symbol'))}</td>"
            f'<td class="num">{_fa(row.get("target_horizon"), 0)}</td>'
            f"<td>{_esc(row.get('model_name'))}</td>"
            f'<td class="num">{_fa(row.get("mae"))}</td>'
            f'<td class="num">{_fa(row.get("rmse"))}</td>'
            f'<td class="num">{_fa(row.get("directional_accuracy"))}</td>'
            f'<td class="num">{_fa(row.get("dm_p_holm"))}</td>'
            f"<td>{_verdict_badge(str(row.get('verdict', 'گزارش نشده')))}</td>"
            "</tr>"
        )
    cov_html = ""
    for cov in board.get("coverage", []):
        cov_html += (
            "<tr>"
            f"<td>{_esc(cov.get('pair_symbol'))}</td>"
            f'<td class="num">{_fa(cov.get("target_horizon"), 0)}</td>'
            f"<td>{_esc(cov.get('method'))}</td>"
            f'<td class="num">{_fa(cov.get("nominal_level"))}</td>'
            f'<td class="num">{_fa(cov.get("empirical_coverage"))}</td>'
            f'<td class="num">{_fa(cov.get("mean_width"))}</td>'
            f'<td class="num">{_fa(cov.get("n"), 0)}</td>'
            "</tr>"
        )
    quality_html = ""
    for pair, report in sorted(quality.items()):
        summary = report.get("summary", {})
        quality_html += (
            "<tr>"
            f"<td>{_esc(pair)}</td>"
            f"<td>{_esc(report.get('data_source'))}</td>"
            f'<td class="num">{_fa(report.get("row_count"), 0)}</td>'
            f'<td class="num">{_fa(report.get("gaps", {}).get("missing_count"), 0)}</td>'
            f'<td class="num">{_fa(report.get("outliers", {}).get("outlier_count"), 0)}</td>'
            f"<td>{_esc('؛ '.join(summary.get('issues', [])) or 'تمیز')}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>گزارش ارزیابی AWAGO — {digits_fa(board.get("run_id", "نامشخص")[:16])}</title>
<style>{CSS}</style>
</head>
<body>
<h1>گزارش ارزیابی مدل‌های AWAGO</h1>
<p class="meta">
  شناسه اجرا: <bdi>{_esc(board.get("run_id"))}</bdi> ·
  تاریخ تولید گزارش: {_fa(format_jalali_long_fa(generated))} ·
  تاریخ میلادی: {_esc(generated.strftime("%Y-%m-%d %H:%M UTC"))}
</p>
<div class="badge-row">
  {_badge("منبع داده: " + str(board.get("pairs", ["—"])[0]), "warn" if board.get("pairs") else "muted")}
  {_badge("روش: " + str(board.get("scheme", "expanding")) + f" ({_fa(board.get('n_splits'), 0)} بخش)", "muted")}
  {_badge("هش config: " + str(board.get("config_hash", "—"))[:12], "muted")}
  {_badge("هش snapshot: " + str(board.get("snapshot_hash", "—"))[:12], "muted")}
</div>

<h2>۱. جدول رتبه‌بندی (واک‌فوروارد)</h2>
<table>
  <thead><tr>
    <th>جفت‌ارز</th><th class="num">افق (روز)</th><th>مدل</th>
    <th class="num">MAE</th><th class="num">RMSE</th><th class="num">دقت جهت</th>
    <th class="num">p (Holm)</th><th>نتیجه مقایسه با خط پایه</th>
  </tr></thead>
  <tbody>{rows_html or '<tr><td colspan="8">گزارش نشده</td></tr>'}</tbody>
</table>
<p class="fine-print">
  نتایج از ارزیابی واک‌فوروارد با حذف ردیف‌های هم‌پوشان (purging) به دست آمده‌اند؛
  p-value ها با تصحیح چندمقایسه‌ای هولم گزارش می‌شوند. معیار «بهتر بودن»، خط پایه تصادفی (naive) در همان ردیف‌ها است.
</p>

<h2>۲. کالیبراسیون بازه اطمینان</h2>
<table>
  <thead><tr>
    <th>جفت‌ارز</th><th class="num">افق</th><th>روش</th>
    <th class="num">سطح اسمی</th><th class="num">پوشش تجربی</th><th class="num">میانگین عرض</th><th class="num">n</th>
  </tr></thead>
  <tbody>{cov_html or '<tr><td colspan="7">گزارش نشده</td></tr>'}</tbody>
</table>
<p class="fine-print">پوشش تجربی روی همان ردیف‌های واک‌فوروارد اندازه‌گیری شده است؛ سطح اسمی تضمین نیست.</p>

<h2>۳. کیفیت داده</h2>
<table>
  <thead><tr>
    <th>جفت‌ارز</th><th>منبع</th><th class="num">تعداد ردیف</th>
    <th class="num">شکاف</th><th class="num">پرت</th><th>مشکلات</th>
  </tr></thead>
  <tbody>{quality_html or '<tr><td colspan="6">گزارش نشده</td></tr>'}</tbody>
</table>

<h2>۴. روش‌شناسی</h2>
<ul>
  <li>هدف: بازده لگاریتمی آینده (افق‌های {", ".join(digits_fa(str(h)) for h in board.get("horizons", [])) or "گزارش نشده"} روزه).</li>
  <li>تفکیک: واک‌فوروارد {board.get("scheme", "expanding")!s} با purge برابر طول افق؛ وزن‌دهی ensembleها فقط روی بخش‌های قبلی.</li>
  <li>آمار: آزمون دیبلد-ماریانو با تصحیح هاروی در برابر خط پایه naive؛ تصحیح چندمقایسه‌ای هولم روی خانواده مدل‌ها.</li>
  <li>هر عدد این گزارش مستقیماً از خروجی‌های ذخیره‌شده (run_id: <bdi>{_esc(board.get("run_id"))}</bdi>) بازتولید شده است؛ هیچ مقدار جدیدی محاسبه یا تخمین زده نمی‌شود.</li>
</ul>

<div class="disclaimer">
  <p>{DISCLAIMER_FA}</p>
  <p class="disclaimer-en">{DISCLAIMER_EN} Past performance does not indicate future results. Backtests are simulations with modeled costs and slippage.</p>
</div>

<p class="fine-print">AWAGO · گزارش تولیدشده به‌صورت خودکار · تاریخ: {_fa(format_jalali_long_fa(generated))}</p>
</body>
</html>
"""


def load_board(run_id: str, base: Path | None = None) -> dict[str, Any]:
    from app.config import DATA_DIR

    root = (base or DATA_DIR) / "leaderboards"
    path = root / ("latest.json" if run_id in ("", "latest") else f"{run_id}.json")
    if not path.exists():
        raise FileNotFoundError(f"Leaderboard not found for run: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def generate_report(run_id: str = "latest", base: Path | None = None) -> str:
    board = load_board(run_id, base)
    return render_report(board)
