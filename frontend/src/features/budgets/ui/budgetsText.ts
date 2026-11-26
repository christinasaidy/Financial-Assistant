/**
 * The Budgets screen's numbers and dates as text, always through shared/format (DESIGN.md §5). Written in
 * normal case: the cap style adds capitals.
 */
import { monthName, shortMonthName } from '@/shared/format/dates';
import { formatCell, formatLimitCell, formatMoney, formatUsd } from '@/shared/format/money';

import { perDay, remainder, type SheetSummary } from '../domain/rules';
import type { Budget, BudgetsError } from '../domain';

/** "Nov 2026". */
export function monthLabel(month: Date): string {
  return `${shortMonthName(month)} ${month.getFullYear()}`;
}

/** "November 2026", for sentences. */
export function longMonthLabel(month: Date): string {
  return `${monthName(month)} ${month.getFullYear()}`;
}

/** "4 days left", "1 day left", "Last day"; "Month ended" for a past month. */
export function daysLeftLabel(days: number | null): string {
  if (days === null) return 'Month ended';
  if (days === 0) return 'Last day';
  return days === 1 ? '1 day left' : `${days} days left`;
}

/** Whole dollars without cents, as limits are usually round: "$390"; "$390.50" otherwise. */
export function roundDollars(amount: string): string {
  const text = formatUsd(amount);
  return text.endsWith('.00') ? text.slice(0, -3) : text;
}

/** "$69.10 left across 3 budgets". */
export function leftAcross(summary: SheetSummary): string {
  return `${formatUsd(summary.left)} left across ${summary.count} ${summary.count === 1 ? 'budget' : 'budgets'}`;
}

/** A slip's "63.00 / 60": spent and limit, as table cells. */
export function spentOfLimit(budget: Budget): { spent: string; limit: string } {
  return { spent: formatCell(budget.spent, budget.currency), limit: formatLimitCell(budget.limit, budget.currency) };
}

/** "$8.50 left" or "Over by $3.00". */
export function remainderLine(budget: Budget): { text: string; over: boolean } {
  const { kind, amount } = remainder(budget);
  const money = formatMoney(amount, budget.currency);
  return kind === 'over' ? { text: `Over by ${money}`, over: true } : { text: `${money} left`, over: false };
}

/** "$2.13 a day"; null outside the current month. */
export function perDayLine(budget: Budget, days: number | null): string | null {
  const amount = perDay(budget, days);
  return amount === null ? null : `${formatMoney(amount, budget.currency)} a day`;
}

/** What to say when the month could not load or a budget could not be saved. */
export function errorSentence(error: BudgetsError, doing: 'load' | 'save' | 'remove'): string {
  if (error.code === 'network') return "Can't reach Fatourati. Check your connection and try again.";
  if (error.code === 'rejected') return error.message;
  return doing === 'load'
    ? 'The server could not send this month’s budgets.'
    : `Fatourati could not ${doing} this budget. Try again in a moment.`;
}
