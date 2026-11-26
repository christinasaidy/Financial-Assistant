/**
 * What the Budgets screen works with (design/screens/06-budgets.png). Plain types: no React, no HTTP.
 * Amounts stay decimal strings exactly as the backend sends them; they become text only on screen.
 */

export type BudgetCurrency = 'USD' | 'LBP';

/** The backend's budget states: ok below 80%, near from 80%, limit_reached at 100% or more. */
export type BudgetState = 'ok' | 'near' | 'limit_reached';

/** One category's budget for a month, from GET /budgets?month=. */
export type Budget = {
  categoryId: number;
  name: string;
  currency: BudgetCurrency;
  limit: string;
  spent: string;
  /** One decimal, as the backend rounds it: "89.4", "105.0". */
  percentUsed: string;
  state: BudgetState;
};

/** A category the user can budget (GET /categories). */
export type Category = { id: number; name: string };

/** The month's spending by category, in dollars (GET /spending/summary), for "Everything else". */
export type MonthSpending = {
  /** Everything converted into dollars. */
  total: string;
  categories: { categoryId: number | null; amount: string }[];
  /** Today's LBP per USD: pound budgets count in the sheet's dollar totals at this rate. */
  lbpPerUsd: string;
};

/** Everything the Budgets screen shows for one month. */
export type BudgetMonth = {
  /** The first day of the month, local: new Date(2026, 10, 1). */
  month: Date;
  budgets: Budget[];
  spending: MonthSpending;
  /** Categories with no budget yet, for a new budget. */
  unbudgeted: Category[];
};

/** What the form sends: a limit for a category, from `month` onwards. */
export type BudgetDraft = {
  categoryId: number;
  month: Date;
  currency: BudgetCurrency;
  /** As typed, already checked: "250", "62.5", "3000000". */
  limit: string;
};
