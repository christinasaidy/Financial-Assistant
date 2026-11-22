/**
 * Home's rules (D035-D037), as pure functions: which budgets and receipts Home shows, and how a budget's
 * state reads. Formatting of money and dates is not here: it belongs to shared/format, used by the UI.
 */
import type { BudgetState, BudgetUse, MonthSpending, ReceiptListing } from './types';

/** Home shows the three budgets closest to their limit (D035). */
export const HOME_BUDGET_COUNT = 3;

/** Home lists the three newest receipts: two fit in the first view, the third is reached by scrolling (D036). */
export const HOME_RECENT_COUNT = 3;

/** "Hello, Christina"; just "Hello" for an account with no first name (D036, D041). */
export function greeting(firstName: string | null | undefined): string {
  const name = firstName?.trim();
  return name ? `Hello, ${name}` : 'Hello';
}

/** Nothing was confirmed this month yet: the total reads $0.00 and Home invites a first scan (D037). */
export function isMonthEmpty(spending: MonthSpending): boolean {
  return spending.receiptCount === 0;
}

function percentValue(percentUsed: string): number {
  const value = Number.parseFloat(percentUsed);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

/**
 * The percentage shown in words, rounded down: "89.6" reads 89%, so a budget that is near its limit never
 * reads 100% before it is reached (the backend's state turns at exactly 100%).
 */
export function wholePercent(percentUsed: string): number {
  return Math.floor(percentValue(percentUsed));
}

/** How much of the bar is filled, 0 to 100: a budget past its limit fills the bar, never more. */
export function barWidthPercent(percentUsed: string): number {
  return Math.min(percentValue(percentUsed), 100);
}

/**
 * The budgets closest to their limit, closest first: highest percent used, then by name. Budgets past their
 * limit come first, as they need attention most.
 */
export function closestToLimit(budgets: readonly BudgetUse[], count: number = HOME_BUDGET_COUNT): BudgetUse[] {
  return [...budgets]
    .sort((a, b) => percentValue(b.percentUsed) - percentValue(a.percentUsed) || a.name.localeCompare(b.name))
    .slice(0, Math.max(count, 0));
}

/** The colour token of a budget's bar and words (D021-D023): fine budgets are plain ink. */
export type BudgetTone = 'ink' | 'near-limit' | 'limit-reached';

export function budgetTone(state: BudgetState): BudgetTone {
  switch (state) {
    case 'near':
      return 'near-limit';
    case 'limit_reached':
      return 'limit-reached';
    case 'ok':
      return 'ink';
  }
}

/**
 * The state in words, so colour is never the only signal (D021, WCAG 1.4.1): "Near limit · 89%",
 * "Limit reached · 105%" (shown in capitals by style). A fine budget has none.
 */
export function budgetStateWords(budget: Pick<BudgetUse, 'state' | 'percentUsed'>): string | null {
  const percent = `${wholePercent(budget.percentUsed)}%`;
  switch (budget.state) {
    case 'near':
      return `Near limit · ${percent}`;
    case 'limit_reached':
      return `Limit reached · ${percent}`;
    case 'ok':
      return null;
  }
}

/** A receipt Home can list: confirmed (so it is counted in the totals), with its date, currency and total. */
export type ConfirmedListing = ReceiptListing & {
  receiptDate: string;
  currency: NonNullable<ReceiptListing['currency']>;
  total: string;
};

export function isListedOnHome(receipt: ReceiptListing): receipt is ConfirmedListing {
  return (
    receipt.status === 'confirmed' &&
    receipt.receiptDate !== null &&
    receipt.currency !== null &&
    receipt.total !== null
  );
}

/**
 * The receipts for Recent, from the backend's list (already newest first: by the printed date, then the
 * newest added). Only confirmed receipts, the ones the month total counts.
 */
export function newestConfirmed(
  receipts: readonly ReceiptListing[],
  count: number = HOME_RECENT_COUNT,
): ConfirmedListing[] {
  return receipts.filter(isListedOnHome).slice(0, Math.max(count, 0));
}

/** "1 item", "9 items"; nothing for a receipt saved without lines. */
export function itemCountWords(count: number): string | null {
  if (count <= 0) return null;
  return count === 1 ? '1 item' : `${count} items`;
}
