/** Persian formatting: digits, dates (Jalali), numbers, honesty badges data. */
import { gregorianToJalali, MONTHS_FA } from "./jalali.js";

export function faDigits(text) {
  return String(text).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
}

export function faNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const s = Number(value).toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  return faDigits(s);
}

export function faPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return faDigits(Number(value).toFixed(digits)) + "٪";
}

export function faDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const [jy, jm, jd] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
  return faDigits(`${jy}/${String(jm).padStart(2, "0")}/${String(jd).padStart(2, "0")}`);
}

export function faDateLong(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const [jy, jm, jd] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
  return faDigits(`${jd} ${MONTHS_FA[jm - 1]} ${jy}`);
}

export function faDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${faDate(iso)} — ${faDigits(hh)}:${faDigits(mm)}`;
}
