/**
 * "1:30", "1.5", "1,5", "90m", "2h" or "2h 15m" -> minutes. A bare number means hours.
 * Returns null when the text is not a duration between one minute and 24 hours.
 */
export function parseDuration(text: string): number | null {
  const s = text.trim().toLowerCase();
  let minutes: number | null = null;
  let m: RegExpMatchArray | null;
  if ((m = s.match(/^(\d{1,2}):([0-5]\d)$/))) {
    minutes = Number(m[1]) * 60 + Number(m[2]);
  } else if ((m = s.match(/^(?:(\d{1,2})\s*h)?\s*(?:(\d{1,4})\s*m(?:in)?)?$/)) && (m[1] || m[2])) {
    minutes = Number(m[1] ?? 0) * 60 + Number(m[2] ?? 0);
  } else if ((m = s.match(/^(\d{1,2})(?:[.,](\d{1,2}))?$/))) {
    const hundredths = Number(m[1]) * 100 + Number(((m[2] ?? "") + "00").slice(0, 2));
    minutes = Math.round((hundredths * 60) / 100);
  }
  return minutes !== null && minutes >= 1 && minutes <= 24 * 60 ? minutes : null;
}

/** 135 -> "2h 15m", 45 -> "45m", 120 -> "2h" */
export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/** 135 -> "2:15": the form used in the duration input. */
export function durationToInput(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

/** Seconds -> "01:02:03" for the running timer. */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

/** Local calendar date as YYYY-MM-DD (toISOString would shift it to UTC). */
export function isoDate(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

/** Days back from today, in whole pages of `page` days, for a list to reach back to `iso`. */
export function daysToCover(iso: string, page: number, today: string = isoDate()): number {
  const days = Math.round((Date.parse(today) - Date.parse(iso)) / 86_400_000);
  return Math.max(1, Math.ceil(days / page)) * page;
}

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });

/** "2026-03-09" -> "9 Mar 2026" */
export function formatDate(iso: string): string {
  return DAY.format(new Date(`${iso}T00:00:00`));
}

/** "2026-03-09" -> "Monday 9 March" */
export function formatWeekday(iso: string): string {
  return WEEKDAY.format(new Date(`${iso}T00:00:00`));
}
