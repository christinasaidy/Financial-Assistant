/**
 * The Scan flow's words and numbers, always through shared/format (DESIGN.md §5).
 */
import { monthName, parseApiDate, shortMonthName } from '@/shared/format/dates';
import { formatCell, formatLimitCell, formatMoney } from '@/shared/format/money';

import type { Currency, Receipt } from '../domain';

/** Anything that went wrong, as one sentence: no connection, the backend's own reason, or a plain fallback. */
export function scanErrorSentence(error: unknown): string {
  const code = typeof error === 'object' && error && 'code' in error ? (error as { code: string }).code : null;
  const message = error instanceof Error ? error.message : '';
  if (code === 'network') return "Can't reach Fatourati. Check your connection and try again.";
  if (code === 'failed') return 'Fatourati could not read this photo. Retake it with the whole receipt inside the corners, or fill it in by hand.';
  if (code === 'timeout') return 'Reading this receipt is taking too long. Try again in a moment.';
  if (code === 'refused' && message) return message;
  return 'Something went wrong. Try again in a moment.';
}

/** The checklist on Reading (screen 10): what was found, once the backend has read it. */
export function readingRows(receipt: Receipt): { label: string; value: string; mono: boolean }[] {
  const date = receipt.receiptDate ? parseApiDate(receipt.receiptDate) : null;
  const items = receipt.lines.length;
  return [
    { label: 'Store', value: receipt.shopName ?? 'Not found', mono: false },
    { label: 'Date', value: date ? `${date.getDate()} ${shortMonthName(date)} ${date.getFullYear()}` : 'Not found', mono: true },
    { label: 'Items', value: items === 1 ? '1 found' : `${items} found`, mono: true },
    { label: 'Total', value: receipt.total && receipt.currency ? formatMoney(receipt.total, receipt.currency) : 'Not found', mono: true },
  ];
}

/** "Checking the total…": the row still being checked. */
export function checkingLabel(label: string): string {
  return `Checking the ${label.toLowerCase()}…`;
}

/** "Save to November invoice", from the date typed (the current month while it is not a date). */
export function saveLabel(apiDate: string | null, today: Date): string {
  const month = apiDate ? parseApiDate(apiDate) : today;
  return `Save to ${monthName(month)} invoice`;
}

/** "New receipt · for Nº 0447". */
export function newReceiptLabel(invoiceNumber: number): string {
  return `New receipt · for Nº ${String(invoiceNumber).padStart(4, '0')}`;
}

/** A table cell in the receipt's currency. */
export function cell(amount: number | string, currency: Currency): string {
  return formatCell(typeof amount === 'number' ? amount.toFixed(2) : amount, currency);
}

/** "Invoice Nº 0447" and "Nov 2026" for the Filed screen. */
export function filedCaps(invoiceNumber: number, month: Date): { invoice: string; month: string } {
  return { invoice: `Invoice Nº ${String(invoiceNumber).padStart(4, '0')}`, month: `${shortMonthName(month)} ${month.getFullYear()}` };
}

export function limitCell(limit: string, currency: Currency): string {
  return formatLimitCell(limit, currency);
}

export function money(amount: number | string, currency: Currency): string {
  return formatMoney(typeof amount === 'number' ? amount.toFixed(2) : amount, currency);
}
