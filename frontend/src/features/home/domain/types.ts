/**
 * What the Home screen shows: this month's invoice (design/screens/03-home.png). Plain types: no React, no HTTP.
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
  /** The total split by category, in dollars; `categoryId` null is spending with no category. */
  categories: CategoryAmount[];
};

export type CategoryAmount = { categoryId: number | null; name: string; amount: string };

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
  /** The receipt's main category, or null. */
  categoryId: number | null;
  /** LBP per USD saved with the receipt, or null. */
  lbpPerUsd: string | null;
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
  /** The receipt's category name ("Groceries"), or null. */
  category: string | null;
  /** The rate for "≈ $5.03" under a pound amount: the receipt's own, else today's. */
  lbpPerUsd: string;
};

/** Everything Home needs for one month. */
export type HomeOverview = {
  spending: MonthSpending;
  /** The invoice's number: the month's place since the user's first receipt (0001 is the first month). */
  invoiceNumber: number;
  /** The budgets closest to their limit, closest first (at most three). */
  budgets: BudgetUse[];
  /** The rest of the month's spending in dollars: the total minus the budgets shown ("Everything else"). */
  everythingElse: string;
  /** The older months peeking behind the invoice, oldest first ("2026-09-01", "2026-10-01"); empty for a new user. */
  olderMonths: string[];
  /** The newest confirmed receipts, newest first. */
  recent: RecentReceipt[];
};
