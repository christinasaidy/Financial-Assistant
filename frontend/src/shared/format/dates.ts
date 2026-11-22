/**
 * Dates and times on screen: dd/mm/yyyy and a 24-hour clock ("18/11/2026 · 18:42", Home mockup D035),
 * always in the phone's own time zone.
 */

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

/**
 * Reads a date from the API. A plain date ("2026-11-18", e.g. receipt_date) is that calendar day here, not
 * midnight UTC (which would show the day before in some time zones). A date-time ("2026-11-18T16:42:00Z",
 * e.g. created_at) is an instant.
 */
export function parseApiDate(value: string): Date {
  const dateOnly = DATE_ONLY.exec(value);
  if (dateOnly) {
    const [, year, month, day] = dateOnly;
    return new Date(Number(year), Number(month) - 1, Number(day));
  }
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) {
    throw new Error(`Not a date: "${value}"`);
  }
  return instant;
}

function asDate(value: Date | string): Date {
  return typeof value === 'string' ? parseApiDate(value) : value;
}

function twoDigits(value: number): string {
  return String(value).padStart(2, '0');
}

/** "18/11/2026". */
export function formatDate(value: Date | string): string {
  const date = asDate(value);
  return `${twoDigits(date.getDate())}/${twoDigits(date.getMonth() + 1)}/${date.getFullYear()}`;
}

/** "18:42" (24-hour). */
export function formatTime(value: Date | string): string {
  const date = asDate(value);
  return `${twoDigits(date.getHours())}:${twoDigits(date.getMinutes())}`;
}

/** "November". Shown in capitals by the section-label style, never typed in capitals (D012). */
export function monthName(value: Date | string): string {
  return MONTH_NAMES[asDate(value).getMonth()] as string;
}

/** "2026-11": the month format the API's `month` query parameter takes. */
export function toApiMonth(value: Date): string {
  return `${value.getFullYear()}-${twoDigits(value.getMonth() + 1)}`;
}
