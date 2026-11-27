/**
 * The Budgets screen's rules, as pure functions (design/screens/06-budgets.png, DESIGN.md §5). Formatting of
 * money and dates is not here: it belongs to shared/format, used by the UI.
 */
import type { Budget, BudgetCurrency, Category, MonthSpending } from './types';

function number(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** An amount rounded to cents, as a decimal string ("8.50"). */
function cents(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

/** A budget's amounts in dollars: pound budgets at today's rate, so the sheet can add them up. */
function inDollars(amount: string, currency: BudgetCurrency, lbpPerUsd: string): number {
  if (currency === 'USD') return number(amount);
  const rate = number(lbpPerUsd);
  return rate > 0 ? number(amount) / rate : 0;
}

export type SheetSummary = {
  /** Spent across the budgets, in dollars: "$320.90". */
  spent: string;
  /** Their limits added up, in dollars: "of $390 budgeted". */
  budgeted: string;
  /** What is left across them, never below zero: "$69.10 left across 3 budgets". */
  left: string;
  count: number;
  /** Spent ÷ budgeted, rounded down, 0 with no budgets: "82%". */
  percent: number;
};

/** The budget sheet at the top (DESIGN.md §6, screen 06): the budgets added up in dollars. */
export function sheetSummary(budgets: readonly Budget[], lbpPerUsd: string): SheetSummary {
  const spent = budgets.reduce((sum, budget) => sum + inDollars(budget.spent, budget.currency, lbpPerUsd), 0);
  const budgeted = budgets.reduce((sum, budget) => sum + inDollars(budget.limit, budget.currency, lbpPerUsd), 0);
  return {
    spent: cents(spent),
    budgeted: cents(budgeted),
    left: cents(Math.max(budgeted - spent, 0)),
    count: budgets.length,
    percent: budgeted > 0 ? Math.floor((spent / budgeted) * 100) : 0,
  };
}

/** Spent more than the limit: the amount, its bar and "Over by" turn red. */
export function isOver(budget: Pick<Budget, 'spent' | 'limit'>): boolean {
  return number(budget.spent) > number(budget.limit);
}

/** "$8.50 left" or "Over by $3.00": the amount only, in the budget's currency. */
export function remainder(budget: Pick<Budget, 'spent' | 'limit'>): { kind: 'left' | 'over'; amount: string } {
  const difference = number(budget.limit) - number(budget.spent);
  return difference < 0 ? { kind: 'over', amount: cents(-difference) } : { kind: 'left', amount: cents(difference) };
}

/** How much of the bar is filled, 0 to 100. */
export function barWidthPercent(spent: string | number, limit: string | number): number {
  const total = typeof limit === 'number' ? limit : number(limit);
  if (total <= 0) return 0;
  const used = typeof spent === 'number' ? spent : number(spent);
  return Math.min(Math.max((used / total) * 100, 0), 100);
}

function isSameMonth(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
}

/** The current month: its days left are counted and Next is disabled. */
export function isCurrentMonth(month: Date, today: Date): boolean {
  return isSameMonth(month, today);
}

/** Days after today until the month ends ("4 days left" on 26 November); null for any other month. */
export function daysLeft(month: Date, today: Date): number | null {
  if (!isSameMonth(month, today)) return null;
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  return lastDay - today.getDate();
}

/**
 * How much can still be spent a day (DESIGN.md §5): left ÷ days remaining; "$0.00 a day" when over. On the
 * month's last day, all that is left. Null outside the current month.
 */
export function perDay(budget: Pick<Budget, 'spent' | 'limit'>, days: number | null): string | null {
  if (days === null) return null;
  const { kind, amount } = remainder(budget);
  if (kind === 'over') return '0.00';
  return cents(number(amount) / Math.max(days, 1));
}

/** The month's dollar spending outside every budget: "Everything else · $126.90". Never below zero. */
export function everythingElse(spending: MonthSpending, budgets: readonly Budget[]): string {
  const budgeted = new Set(budgets.map((budget) => budget.categoryId));
  const inBudgets = spending.categories
    .filter((category) => category.categoryId !== null && budgeted.has(category.categoryId))
    .reduce((sum, category) => sum + number(category.amount), 0);
  return cents(Math.max(number(spending.total) - inBudgets, 0));
}

/** Categories that have no budget yet, by name, for a new budget. */
export function unbudgetedCategories(categories: readonly Category[], budgets: readonly Budget[]): Category[] {
  const budgeted = new Set(budgets.map((budget) => budget.categoryId));
  return categories.filter((category) => !budgeted.has(category.id)).sort((a, b) => a.name.localeCompare(b.name));
}

/** The first day of the month before or after. */
export function shiftMonth(month: Date, by: number): Date {
  return new Date(month.getFullYear(), month.getMonth() + by, 1);
}

export type LimitProblem = 'limit-missing' | 'limit-not-a-number' | 'limit-not-positive' | 'limit-too-precise';

/**
 * Checks a typed limit: a positive amount, dollars with at most two decimals, pounds whole. Commas typed as
 * thousands separators are fine ("3,000,000"). Returns the cleaned amount, or the problem.
 */
export function checkLimit(typed: string, currency: BudgetCurrency): { limit: string } | { problem: LimitProblem } {
  const cleaned = typed.trim().replace(/,/g, '');
  if (cleaned === '') return { problem: 'limit-missing' };
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return { problem: 'limit-not-a-number' };
  if (Number.parseFloat(cleaned) <= 0) return { problem: 'limit-not-positive' };
  const decimals = cleaned.split('.')[1]?.length ?? 0;
  if (decimals > (currency === 'USD' ? 2 : 0)) return { problem: 'limit-too-precise' };
  return { limit: cleaned };
}
