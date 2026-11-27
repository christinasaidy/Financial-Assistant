/**
 * The Scan flow's types and rules (design/screens/09-12): a photo goes up, the backend reads it, the user checks
 * the details, and the receipt is filed into the month's invoice. Plain TypeScript: no React, no HTTP.
 *
 * A scanned receipt is the same Receipt the Receipts feature shows, so its types are reused.
 */
import type { BudgetLine, Category, ConfirmPayload, Currency, Receipt, ReceiptLine } from '@/features/receipts/domain';

export type { BudgetLine, Category, ConfirmPayload, Currency, Receipt, ReceiptLine };

/** A photo to send: a local file from the camera or the photo library. */
export type Photo = { uri: string; mimeType: string };

/** Where reading a receipt stands: the backend reads it in the background. */
export type ReadingState = 'reading' | 'ready' | 'failed';

export function readingState(status: string): ReadingState {
  if (status === 'needs_review' || status === 'confirmed') return 'ready';
  if (status === 'failed') return 'failed';
  return 'reading';
}

/** The backend's review flags (backend/app/domain/receipts/flags.py). */
export const FLAGS = {
  missingVendor: 'missing_vendor',
  missingDate: 'missing_date',
  futureDate: 'future_date',
  missingCurrency: 'missing_currency',
  missingTotal: 'missing_total',
  totalMismatch: 'total_mismatch',
  lineWithoutName: 'line_without_name',
} as const;

/** What Review marks CHECK THIS (D051): the fields a flag is about, and the items the reader could not name. */
export type Checks = { store: boolean; date: boolean; total: boolean; lines: number[] };

export function checksFor(receipt: Receipt): Checks {
  const has = (flag: string) => receipt.flags.includes(flag);
  return {
    store: has(FLAGS.missingVendor),
    date: has(FLAGS.missingDate) || has(FLAGS.futureDate),
    total: has(FLAGS.missingTotal),
    lines: receipt.lines.flatMap((line, index) => (line.normalizedName === null || !line.description.trim() ? [index] : [])),
  };
}

/** What the user can change on Review, as typed. */
export type Draft = {
  shopName: string;
  /** "18/11/2026", as on Lebanese receipts. */
  date: string;
  currency: Currency;
  /** The total as typed: "38.40". */
  total: string;
  categoryId: number | null;
  lines: ReceiptLine[];
};

function two(value: number): string {
  return String(value).padStart(2, '0');
}

/** "2026-11-18" -> "18/11/2026". */
export function displayDate(apiDate: string): string {
  const [year, month, day] = apiDate.split('-');
  return `${day}/${month}/${year}`;
}

/** "18/11/2026" (or 18-11-2026, 18.11.26) -> "2026-11-18"; null when it is not a real date. */
export function parseDate(typed: string): string | null {
  const match = /^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\s*$/.exec(typed);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = match[3]!.length === 2 ? 2000 + Number(match[3]) : Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return `${year}-${two(month)}-${two(day)}`;
}

/** The draft Review starts from: what the backend read, today's date when it read none, dollars by default. */
export function draftFrom(receipt: Receipt, today: Date): Draft {
  const date = receipt.receiptDate ?? `${today.getFullYear()}-${two(today.getMonth() + 1)}-${two(today.getDate())}`;
  return {
    shopName: receipt.shopName ?? '',
    date: displayDate(date),
    currency: receipt.currency ?? 'USD',
    total: receipt.total ?? '',
    categoryId: receipt.categoryId,
    lines: receipt.lines,
  };
}

function number(value: string): number {
  const parsed = Number.parseFloat(value.replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

/** The items added up: "38.40". */
export function linesTotal(lines: readonly ReceiptLine[]): number {
  return lines.reduce((sum, line) => sum + (Number.parseFloat(line.lineTotal) || 0), 0);
}

/** "✓ Items add up to the total", or a warning (D051); nothing to say for a receipt saved without items. */
export function addsUp(draft: Draft): boolean | null {
  if (draft.lines.length === 0) return null;
  const total = number(draft.total);
  if (Number.isNaN(total)) return false;
  return Math.abs(linesTotal(draft.lines) - total) < (draft.currency === 'USD' ? 0.005 : 0.5);
}

/** An amount converted and written for its currency: dollars with cents, pounds whole. */
function converted(value: string | null, from: Currency, to: Currency, lbpPerUsd: number): string | null {
  if (value === null || value.trim() === '') return value;
  const amount = number(value);
  if (Number.isNaN(amount)) return value;
  const result = convert(amount, from, to, lbpPerUsd);
  return to === 'USD' ? (Math.round(result * 100) / 100).toFixed(2) : String(Math.round(result));
}

/**
 * The USD / LBP switch (D052): the receipt shown and saved in the other currency, the total and every item
 * converted at the rate. If the items added up before, the total becomes the converted items' sum, so rounding
 * never makes them disagree.
 */
export function convertDraft(draft: Draft, to: Currency, lbpPerUsd: number): Draft {
  if (draft.currency === to || lbpPerUsd <= 0) return { ...draft, currency: to };
  const fitted = addsUp(draft) === true;
  const lines = draft.lines.map((line) => ({
    ...line,
    lineTotal: converted(line.lineTotal, draft.currency, to, lbpPerUsd) ?? line.lineTotal,
    unitPrice: converted(line.unitPrice, draft.currency, to, lbpPerUsd),
  }));
  const sum = linesTotal(lines);
  const total = fitted ? (to === 'USD' ? sum.toFixed(2) : String(Math.round(sum))) : (converted(draft.total, draft.currency, to, lbpPerUsd) ?? draft.total);
  return { ...draft, currency: to, lines, total };
}

export type DraftProblems = { store?: string; date?: string; total?: string; category?: string };

/** What must be fixed before saving: a store, a real date, a positive total, a category. */
export function checkDraft(draft: Draft): DraftProblems {
  const problems: DraftProblems = {};
  if (!draft.shopName.trim()) problems.store = 'Enter the store.';
  if (parseDate(draft.date) === null) problems.date = 'Enter the date like 18/11/2026.';
  const total = number(draft.total);
  const decimals = draft.total.replace(/,/g, '').split('.')[1]?.length ?? 0;
  if (Number.isNaN(total) || total <= 0) problems.total = 'Enter the total.';
  else if (decimals > (draft.currency === 'USD' ? 2 : 0)) problems.total = draft.currency === 'USD' ? 'Use at most two decimals.' : 'Pounds have no decimals.';
  if (draft.categoryId === null) problems.category = 'Choose a category.';
  return problems;
}

/** The checked draft as the backend saves it. */
export function payloadFrom(draft: Draft): ConfirmPayload {
  return {
    shopName: draft.shopName.trim(),
    receiptDate: parseDate(draft.date) as string,
    currency: draft.currency,
    total: draft.total.replace(/,/g, '').trim(),
    categoryId: draft.categoryId,
    lines: draft.lines,
  };
}

/** Review shows the first four items, then "+ 5 more items · 13.75" (screen 11). */
export const FIRST_ITEMS = 4;

/** Everything the Filed screen shows (screen 12): the category's line before and after, and the total. */
export type Filed = {
  receipt: Receipt;
  category: string | null;
  /** The receipt's amount in its budget's currency (or its own, with no budget). */
  added: number;
  budget: { limit: string; currency: Currency; before: number; after: number } | null;
  totalBefore: number;
  totalAfter: number;
  invoiceNumber: number;
  /** The first day of the receipt's month. */
  month: Date;
};

/** A receipt's amount in another currency, at its own rate. */
export function convert(amount: number, from: Currency, to: Currency, lbpPerUsd: number): number {
  if (from === to || lbpPerUsd <= 0) return amount;
  return from === 'LBP' ? amount / lbpPerUsd : amount * lbpPerUsd;
}

/**
 * The Filed screen's numbers: what the budget and the month's total were before this receipt, from what they
 * are after it (the backend has already counted it).
 */
export function filedNumbers(
  receipt: Receipt,
  budget: BudgetLine | null,
  monthTotalUsd: number,
  lbpPerUsd: number,
): Pick<Filed, 'added' | 'budget' | 'totalBefore' | 'totalAfter'> {
  const amount = Number.parseFloat(receipt.total ?? '0') || 0;
  const own = receipt.currency ?? 'USD';
  const rate = Number.parseFloat(receipt.lbpPerUsd ?? '') || lbpPerUsd;
  const inUsd = convert(amount, own, 'USD', rate);
  const round = (value: number) => Math.round(value * 100) / 100;
  if (!budget) {
    return { added: amount, budget: null, totalBefore: round(monthTotalUsd - inUsd), totalAfter: monthTotalUsd };
  }
  const added = convert(amount, own, budget.currency, rate);
  const after = Number.parseFloat(budget.spent) || 0;
  return {
    added: round(added),
    budget: { limit: budget.limit, currency: budget.currency, before: round(Math.max(after - added, 0)), after },
    totalBefore: round(monthTotalUsd - inUsd),
    totalAfter: monthTotalUsd,
  };
}
