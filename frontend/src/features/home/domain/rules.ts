/**
 * Home's rules, as pure functions: what the month's invoice shows (design/screens/03-home.png, DESIGN.md
 * §4-§5). Formatting of money and dates is not here: it belongs to shared/format, used by the UI.
 */
import type { BudgetUse, CategoryAmount, MonthSpending, ReceiptListing } from './types';

/** Home lists the three newest receipts under the invoice. */
export const HOME_RECENT_COUNT = 3;

/** "Billed to Christina"; "Billed to you" for an account with no first name. */
export function billedTo(firstName: string | null | undefined): string {
  const name = firstName?.trim();
  return `Billed to ${name || 'you'}`;
}

/** Nothing was confirmed this month yet: the blank invoice (design/screens/04-home-empty.png). */
export function isMonthEmpty(spending: MonthSpending): boolean {
  return spending.receiptCount === 0;
}

function number(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** An amount rounded to cents, as a decimal string ("8.50"). */
function cents(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

/** How much of the bar is filled, 0 to 100: a budget past its limit fills the bar, never more. */
export function barWidthPercent(percentUsed: string): number {
  return Math.min(Math.max(number(percentUsed), 0), 100);
}

/** Spent more than the limit: the amount, its bar and "+3.00 over" turn red (DESIGN.md §4). */
export function isOver(budget: Pick<BudgetUse, 'spent' | 'limit'>): boolean {
  return number(budget.spent) > number(budget.limit);
}

/** What the line under a budget's spent amount says: "8.50 left" or "+3.00 over" (the amount only). */
export function budgetRemainder(budget: Pick<BudgetUse, 'spent' | 'limit'>): { kind: 'left' | 'over'; amount: string } {
  const difference = number(budget.limit) - number(budget.spent);
  return difference < 0 ? { kind: 'over', amount: cents(-difference) } : { kind: 'left', amount: cents(difference) };
}

/**
 * Every budget, closest to its limit first: highest percent used, then by name. The invoice lists them all
 * (D048), so budgets past their limit lead, as they need attention most.
 */
export function closestToLimit(budgets: readonly BudgetUse[]): BudgetUse[] {
  return [...budgets].sort((a, b) => number(b.percentUsed) - number(a.percentUsed) || a.name.localeCompare(b.name));
}

/**
 * "Everything else": the month's dollar total minus what the budgets' categories spent, so the table's rows add
 * up to TOTAL. Spending with no budget or no category falls in here. Never below zero.
 */
export function everythingElse(total: string, categories: readonly CategoryAmount[], shown: readonly BudgetUse[]): string {
  const budgeted = new Set(shown.map((budget) => budget.categoryId));
  const inBudgets = categories
    .filter((category) => category.categoryId !== null && budgeted.has(category.categoryId))
    .reduce((sum, category) => sum + number(category.amount), 0);
  return cents(Math.max(number(total) - inBudgets, 0));
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
export function newestConfirmed(receipts: readonly ReceiptListing[], count: number = HOME_RECENT_COUNT): ConfirmedListing[] {
  return receipts.filter(isListedOnHome).slice(0, Math.max(count, 0));
}

/** Months since year 0, so two months can be subtracted. */
function monthIndex(year: number, month: number): number {
  return year * 12 + month;
}

function indexOfDate(date: string): number {
  return monthIndex(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1);
}

function firstOfMonth(index: number): string {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, '0')}-01`;
}

/**
 * The invoice's number: one invoice a month, counted from the month of the user's first receipt, so the
 * first month is Nº 0001. A user with no receipts yet is on Nº 0001.
 */
export function invoiceNumber(month: Date, receipts: readonly ReceiptListing[]): number {
  const dates = receipts.filter(isListedOnHome).map((receipt) => indexOfDate(receipt.receiptDate));
  if (dates.length === 0) return 1;
  const first = Math.min(...dates);
  return Math.max(monthIndex(month.getFullYear(), month.getMonth()) - first + 1, 1);
}

/**
 * The two months before this one, oldest first, peeking behind the invoice (DESIGN.md §4), once the user has
 * receipts from before this month. A new user has none (design/screens/04-home-empty.png).
 */
export function olderMonths(month: Date, receipts: readonly ReceiptListing[]): string[] {
  const current = monthIndex(month.getFullYear(), month.getMonth());
  const hasOlder = receipts.filter(isListedOnHome).some((receipt) => indexOfDate(receipt.receiptDate) < current);
  return hasOlder ? [firstOfMonth(current - 2), firstOfMonth(current - 1)] : [];
}

/** "1 item", "9 items"; nothing for a receipt saved without lines. */
export function itemCountWords(count: number): string | null {
  if (count <= 0) return null;
  return count === 1 ? '1 item' : `${count} items`;
}

/** "Groceries · 9 items", "Groceries", "9 items", or nothing. */
export function receiptSubline(category: string | null, itemCount: number): string | null {
  const parts = [category, itemCountWords(itemCount)].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(' · ') : null;
}
