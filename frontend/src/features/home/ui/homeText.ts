/**
 * Home's numbers and dates as text, always through shared/format (D034 money, dd/mm/yyyy and 24 h dates).
 * Written in normal case: the text styles add capitals (D012).
 */
import { formatDate, formatTime, monthName, parseApiDate } from '@/shared/format/dates';
import { formatCombinedLine, formatLbp, formatMoney, formatUsd } from '@/shared/format/money';

import { budgetStateWords, isMonthEmpty, itemCountWords } from '../domain/rules';
import type { BudgetUse, HomeCurrency, MonthSpending, RecentReceipt } from '../domain/types';

/** "This month · November" (D035), from the month the backend summed. */
export function monthLabel(spending: MonthSpending): string {
  return `This month · ${monthName(parseApiDate(spending.month))}`;
}

/** The month total in dollars: "$447.80", "$0.00". */
export function monthTotal(spending: MonthSpending): string {
  return formatUsd(spending.total);
}

/**
 * The line under the total (D034, D037), with only the parts that exist:
 * - nothing confirmed this month: "No receipts yet this month";
 * - dollars and pounds: "$412.60 + 3,150,000 LBP at 89,500 LBP per $";
 * - pounds only: "3,150,000 LBP at 89,500 LBP per $";
 * - dollars only: no line (the total already is the dollar amount).
 */
export function monthCaption(spending: MonthSpending): string | null {
  if (isMonthEmpty(spending)) return 'No receipts yet this month';
  const { usdPart, lbpPart, lbpPerUsd } = spending;
  if (lbpPart === null) return null;
  if (usdPart === null) return `${formatLbp(lbpPart)} at ${formatLbp(lbpPerUsd)} per $`;
  return formatCombinedLine(usdPart, lbpPart, lbpPerUsd);
}

/**
 * A budget's limit. Limits are round numbers people choose, so a whole dollar limit reads "$60" as in the
 * Home mockup; one with cents keeps them ("$62.50"). Pounds never have decimals anyway.
 */
export function formatLimit(amount: string, currency: HomeCurrency): string {
  const text = formatMoney(amount, currency);
  return currency === 'USD' ? text.replace(/\.00$/, '') : text;
}

/** "$63.00 / $60". */
export function budgetAmounts(budget: BudgetUse): string {
  return `${formatMoney(budget.spent, budget.currency)} / ${formatLimit(budget.limit, budget.currency)}`;
}

/** What VoiceOver reads for a budget row: "Transport, $63.00 of $60, Limit reached · 105%". */
export function budgetAccessibilityLabel(budget: BudgetUse): string {
  const words = budgetStateWords(budget);
  const amounts = `${formatMoney(budget.spent, budget.currency)} of ${formatLimit(budget.limit, budget.currency)}`;
  return [budget.name, amounts, words].filter(Boolean).join(', ');
}

/** The shop as printed, or a plain stand-in for a receipt confirmed without one. */
export function shopName(receipt: RecentReceipt): string {
  return receipt.shopName ?? 'Shop not named';
}

/** "$38.40", "450,000 LBP". */
export function receiptTotal(receipt: RecentReceipt): string {
  return formatMoney(receipt.total, receipt.currency);
}

/**
 * "18/11/2026 · 18:42 · 9 items". The date is the one printed on the receipt. The backend keeps no printed
 * time, so the time is when the receipt was added, shown only when that was the same day (otherwise it would
 * pair one day's date with another day's time). The item count is left out for a receipt without lines.
 */
export function receiptMeta(receipt: RecentReceipt): string {
  const date = formatDate(receipt.receiptDate);
  const addedSameDay = formatDate(receipt.createdAt) === date;
  return [date, addedSameDay ? formatTime(receipt.createdAt) : null, itemCountWords(receipt.itemCount)]
    .filter(Boolean)
    .join(' · ');
}
