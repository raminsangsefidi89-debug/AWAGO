/** UI helpers: honesty badges, skeletons, tables, toasts, escape. */
import { faDate, faDateTime, faDigits, faNumber } from "./format.js";

export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function skeleton(rows = 3) {
  let html = '<div class="skeleton-stack" aria-busy="true" aria-live="polite">';
  for (let i = 0; i < rows; i += 1) html += '<div class="skeleton skeleton-row"></div>';
  return html + "</div>";
}

export function badge(text, kind = "muted", title = "") {
  return `<span class="badge badge-${esc(kind)}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;
}

/** The honesty badge set: data source, demo/real, update time, model version. */
export function honestyBadges({ source, isDemo, lastUpdate, modelVersion, calibration, verdict }) {
  const out = [];
  out.push(badge(`منبع: ${source || "نامشخص"}`, isDemo ? "warn" : "ok", "منبع داده"));
  out.push(badge(isDemo ? "داده آزمایشی" : "داده واقعی", isDemo ? "warn" : "ok", "نوع داده — داده آزمایشی هرگز با داده واقعی مخلوط نمی‌شود"));
  if (lastUpdate) out.push(badge(`به‌روزرسانی: ${faDate(lastUpdate)}`, "muted", "زمان آخرین به‌روزرسانی"));
  if (modelVersion) out.push(badge(`مدل ${modelVersion}`, "info", "نسخه مدل / مجموعه ویژگی"));
  if (calibration) out.push(badge(`کالیبراسیون: ${calibration}`, "info", "پوشش تجربی بازه اطمینان"));
  if (verdict) out.push(badge(verdict, verdict.includes("significant") && !verdict.includes("not") ? "ok" : "warn", "نتیجه آماری مقایسه با خط پایه"));
  return `<div class="badge-row">${out.join("")}</div>`;
}

export function errorBox(message) {
  return `<div class="error-state" role="alert"><strong>خطا</strong><p>${esc(message)}</p></div>`;
}

export function emptyBox(message) {
  return `<div class="empty-state"><p>${esc(message)}</p></div>`;
}

export function table(headers, rows, opts = {}) {
  const { numeric = [] } = opts;
  let html = '<div class="table-wrap"><table><thead><tr>';
  headers.forEach((h, i) => {
    html += `<th scope="col"${numeric.includes(i) ? ' class="num"' : ""}>${esc(h)}</th>`;
  });
  html += "</tr></thead><tbody>";
  if (!rows.length) {
    html += `<tr><td colspan="${headers.length}" class="empty-cell">داده‌ای موجود نیست</td></tr>`;
  }
  rows.forEach((row) => {
    html += "<tr>";
    row.forEach((cell, i) => {
      const cls = numeric.includes(i) ? ' class="num"' : "";
      html += `<td${cls}>${cell === null || cell === undefined ? "—" : cell}</td>`;
    });
    html += "</tr>";
  });
  return html + "</tbody></table></div>";
}

let toastTimer = null;
export function toast(message, kind = "info") {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.dataset.kind = kind;
  el.classList.add("toast-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("toast-visible"), 4000);
}

export function verbatimNote(text) {
  return `<p class="fine-print">${esc(text)}</p>`;
}
