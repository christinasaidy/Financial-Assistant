/**
 * Home's numbers and dates as text, always through shared/format (DESIGN.md §5). Written in normal case:
 * the cap style adds capitals.
 */
import { parseApiDate, shortMonthName } from '@/shared/format/dates';
import { formatApproxUsd, formatCell, formatCompactLbp, formatInvoiceLine, formatLbp, formatLimitCell, formatMoney, formatUsd } from '@/shared/format/money';

import { budgetRemainder, isMonthEmpty } from '../domain/rules';
import type { BudgetUse, MonthSpending, RecentReceipt } from '../domain/types';

/** "Invoice Nº 0447". */
export function invoiceLabel(invoiceNumber: number): string {
  return `Invoice Nº ${String(invoiceNumber).padStart(4, '0')}`;
}

/** "Nov 2026", from the month the backend summed. */
export function monthLabel(spending: MonthSpending): string {
  const month = parseApiDate(spending.month);
  return `${shortMonthName(month)} ${month.getFullYear()}`;
}

/** "Sep", for a sheet peeking behind the invoice. */
export function olderMonthLabel(firstOfMonth: string): string {
  return shortMonthName(parseApiDate(firstOfMonth));
}

/** The total in dollars: "$447.80", "$0.00". */
export function monthTotal(spending: MonthSpending): string {
  return formatUsd(spending.total);
}

/**
 * The line under the total, with only the parts that exist (DESIGN.md §4, screen 04):
 * - nothing confirmed this month: the blank invoice's sentence;
 * - dollars and pounds: "$412.60 + 3,150,000 LBP · 89,500";
 * - pounds only: "3,150,000 LBP · 89,500";
 * - dollars only: no line (the total already is the dollar amount).
 */
export function invoiceLine(spending: MonthSpending): { text: string; blank: boolean } | null {
  if (isMonthEmpty(spending)) return { text: 'A blank invoice. It fills itself in as you scan.', blank: true };
  const { usdPart, lbpPart, lbpPerUsd } = spending;
  if (lbpPart === null) return null;
  if (usdPart === null) return { text: `${formatLbp(lbpPart)} · ${formatCell(lbpPerUsd, 'LBP')}`, blank: false };
  return { text: formatInvoiceLine(usdPart, lbpPart, lbpPerUsd), blank: false };
}

/** A table cell in the budget's currency: dollars as cells ("63.00"), pounds short (D049: "150M", "450,000"). */
function cell(amount: string, budget: BudgetUse): string {
  return budget.currency === 'LBP' ? formatCompactLbp(amount) : formatCell(amount, 'USD');
}

/** A budget's LIMIT cell: "60", "62.50", "150M". */
export function limitCell(budget: BudgetUse): string {
  return budget.currency === 'LBP' ? formatCompactLbp(budget.limit) : formatLimitCell(budget.limit, 'USD');
}

/** "LBP" under a pound budget's limit, so a short amount is never mistaken for dollars (D049); nothing for dollars. */
export function limitCurrency(budget: BudgetUse): string | null {
  return budget.currency === 'LBP' ? 'LBP' : null;
}

/** A budget's SPENT cell: "63.00", "1.2M". */
export function spentCell(budget: BudgetUse): string {
  return cell(budget.spent, budget);
}

/** Under the spent amount: "8.50 left", "+3.00 over", "150M left". */
export function remainderText(budget: BudgetUse): string {
  const { kind, amount } = budgetRemainder(budget);
  return kind === 'over' ? `+${cell(amount, budget)} over` : `${cell(amount, budget)} left`;
}

/** The date block of a receipt row: "18" over "Nov". */
export function receiptDay(receipt: RecentReceipt): { day: string; month: string } {
  const date = parseApiDate(receipt.receiptDate);
  return { day: String(date.getDate()), month: shortMonthName(date) };
}

/** A receipt's amount: "$38.40", "450,000 LBP". */
export function receiptAmount(receipt: RecentReceipt): string {
  return formatMoney(receipt.total, receipt.currency);
}

/** Under a pound amount: "≈ $5.03" at the receipt's rate; nothing for dollars. */
export function receiptApproxUsd(receipt: RecentReceipt): string | null {
  return receipt.currency === 'LBP' ? formatApproxUsd(receipt.total, receipt.lbpPerUsd) : null;
}
