/**
 * What the Home screen shows (D035-D037). Plain types: no React, no HTTP.
 *
 * Amounts stay decimal strings exactly as the backend sends them ("412.60", "3150000.00"); they are only
 * turned into text on screen, through shared/format.
 */

export type HomeCurrency = 'USD' | 'LBP';

/** This month's spending, from GET /spending/summary in dollars. Only confirmed receipts count. */
export type MonthSpending = {
  /** The first day of the month, "2026-11-01". */
  month: string;
  /** Everything converted into dollars, each receipt at its own saved rate. */
  total: string;
  /** Confirmed receipts counted in the total. 0 means nothing this month yet. */
  receiptCount: number;
  /** The exact dollar part, or null when no receipt this month is in dollars. */
  usdPart: string | null;
  /** The exact pound part, or null when no receipt this month is in pounds. */
  lbpPart: string | null;
  /** Today's LBP per USD, for the combined-currency line (D034). */
  lbpPerUsd: string;
  /** Receipts read but not confirmed yet; not counted in the total. */
  awaitingReview: number;
};

/** The backend's budget states: ok below 80%, near from 80%, limit_reached at 100% or more. */
export type BudgetState = 'ok' | 'near' | 'limit_reached';

/** One category budget for the month, from GET /budgets. */
export type BudgetUse = {
  categoryId: number;
  name: string;
  currency: HomeCurrency;
  limit: string;
  spent: string;
  /** One decimal, as the backend rounds it: "89.4", "105.0". */
  percentUsed: string;
  state: BudgetState;
};

/** A receipt as GET /receipts lists it (newest first, without its lines). */
export type ReceiptListing = {
  id: number;
  status: string;
  shopName: string | null;
  /** The date printed on the receipt, "2026-11-18". */
  receiptDate: string | null;
  currency: HomeCurrency | null;
  total: string | null;
  /** When it was added to the app (a date-time). */
  createdAt: string;
};

/** A row of Recent: a confirmed receipt with its item count. */
export type RecentReceipt = {
  id: number;
  shopName: string | null;
  receiptDate: string;
  createdAt: string;
  currency: HomeCurrency;
  total: string;
  /** Lines on the receipt. */
  itemCount: number;
};

/** Everything Home needs for one month. */
export type HomeOverview = {
  spending: MonthSpending;
  /** The budgets closest to their limit, closest first (at most three). */
  budgets: BudgetUse[];
  /** The newest confirmed receipts, newest first. */
  recent: RecentReceipt[];
};
