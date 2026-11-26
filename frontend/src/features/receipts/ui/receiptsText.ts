/**
 * Receipts as text, always through shared/format (DESIGN.md §5). Written in normal case: the cap style adds
 * capitals.
 */
import { formatTime, monthName, parseApiDate, shortMonthName } from '@/shared/format/dates';
import { formatApproxUsd, formatCell, formatLimitCell, formatMoney, formatUsd } from '@/shared/format/money';

import type { BudgetLine, ListedReceipt, Receipt, ReceiptsError } from '../domain';

/** "November 2026". */
export function monthTitle(month: Date): string {
  return `${monthName(month)} ${month.getFullYear()}`;
}

/** "Total $447.80", or "3 receipts shown" while a chip or a search narrows the list (DESIGN.md §6, screen 13). */
export function totalOrShown(total: string, shown: number | null): string {
  if (shown === null) return `Total ${formatUsd(total)}`;
  return shown === 1 ? '1 receipt shown' : `${shown} receipts shown`;
}

/** The date block: "18" over "Nov". */
export function dayBlock(receiptDate: string): { day: string; month: string } {
  const date = parseApiDate(receiptDate);
  return { day: String(date.getDate()), month: shortMonthName(date) };
}

/** "Groceries · 9 items", or only what is known. */
export function listSubline(receipt: Pick<ListedReceipt, 'category' | 'itemCount'>): string | null {
  const items = receipt.itemCount <= 0 ? null : receipt.itemCount === 1 ? '1 item' : `${receipt.itemCount} items`;
  const parts = [receipt.category, items].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(' · ') : null;
}

export function listAmount(receipt: Pick<ListedReceipt, 'total' | 'currency'>): string {
  return formatMoney(receipt.total, receipt.currency);
}

/** "≈ $5.03" under a pound amount, at the receipt's rate. */
export function listApprox(receipt: Pick<ListedReceipt, 'total' | 'currency' | 'lbpPerUsd'>): string | null {
  return receipt.currency === 'LBP' ? formatApproxUsd(receipt.total, receipt.lbpPerUsd) : null;
}

/** The receipt page's corner (screen 05): "18 Nov · 18:42", the printed date and the time it was added. */
export function receiptWhen(receipt: Receipt): string {
  const day = receipt.receiptDate ? parseApiDate(receipt.receiptDate) : new Date(receipt.createdAt);
  return `${day.getDate()} ${shortMonthName(day)} · ${formatTime(receipt.createdAt)}`;
}

/** "Receipt · Groceries", or just "Receipt". */
export function receiptLabel(category: string | null): string {
  return category ? `Receipt · ${category}` : 'Receipt';
}

/** "Total · 9 items". */
export function totalLabel(receipt: Receipt): string {
  const count = receipt.lines.length;
  return count === 0 ? 'Total' : `Total · ${count === 1 ? '1 item' : `${count} items`}`;
}

/** An item's amount, as a table cell in the receipt's currency ("6.20", "450,000"). */
export function lineAmount(lineTotal: string, receipt: Receipt): string {
  return formatCell(lineTotal, receipt.currency ?? 'USD');
}

/** "Groceries after this" (screen 05): spent / limit, the bar's fill, and what is left. */
export function budgetAfter(budget: BudgetLine): { amounts: string; percent: number; left: string; over: boolean } {
  const spent = Number.parseFloat(budget.spent) || 0;
  const limit = Number.parseFloat(budget.limit) || 0;
  const rest = limit - spent;
  const money = (value: number) => formatMoney(Math.abs(value).toFixed(2), budget.currency);
  return {
    amounts: `${formatCell(budget.spent, budget.currency)} / ${formatLimitCell(budget.limit, budget.currency)}`,
    percent: limit > 0 ? Math.min(Math.max((spent / limit) * 100, 0), 100) : 0,
    left: rest < 0 ? `${money(rest)} over this month` : `${money(rest)} left this month`,
    over: rest < 0,
  };
}

/** A text to share a receipt (the share button). */
export function shareText(receipt: Receipt, category: string | null): string {
  const head = [receipt.shopName ?? 'Receipt', category, receipt.receiptDate].filter(Boolean).join(' · ');
  const lines = receipt.lines.map((line) => `${(line.normalizedName ?? line.description).trim()}  ${lineAmount(line.lineTotal, receipt)}`);
  const total = receipt.total && receipt.currency ? formatMoney(receipt.total, receipt.currency) : '';
  return [head, ...lines, `Total ${total}`].join('\n');
}

export function errorSentence(error: ReceiptsError, doing: 'load' | 'save'): string {
  if (error.code === 'network') return "Can't reach Fatourati. Check your connection and try again.";
  if (error.code === 'refused') return error.message;
  return doing === 'load' ? 'The server could not send the receipts.' : 'Fatourati could not save this. Try again in a moment.';
}
