/**
 * What the Receipts tab and a receipt's page work with (design/screens/13-receipts.png, 05-receipt-detail.png).
 * Plain types: no React, no HTTP. Amounts stay decimal strings as the backend sends them.
 */

export type Currency = 'USD' | 'LBP';

/** One item on a receipt, with everything the backend keeps, so saving a change never loses a field. */
export type ReceiptLine = {
  id: number | null;
  description: string;
  lineTotal: string;
  quantity: string;
  unitPrice: string | null;
  normalizedName: string | null;
  sizeAmount: string | null;
  sizeUnit: string | null;
  /** The item's own category; null follows the receipt's. */
  categoryId: number | null;
  brand: string | null;
};

/** A receipt as the list gives it (GET /receipts). */
export type ReceiptSummary = {
  id: number;
  status: string;
  shopName: string | null;
  /** The date printed on it, "2026-11-18". */
  receiptDate: string | null;
  currency: Currency | null;
  total: string | null;
  categoryId: number | null;
  /** LBP per USD saved with it. */
  lbpPerUsd: string | null;
  /** When it was added (a date-time). */
  createdAt: string;
};

/** A receipt with its items (GET /receipts/{id}). */
export type Receipt = ReceiptSummary & { lines: ReceiptLine[]; flags: string[] };

export type Category = { id: number; name: string };

/** A confirmed receipt in the list, ready to show. */
export type ListedReceipt = {
  id: number;
  shopName: string | null;
  receiptDate: string;
  currency: Currency;
  total: string;
  categoryId: number | null;
  category: string | null;
  itemCount: number;
  /** The rate for "≈ $": the receipt's own, else today's. */
  lbpPerUsd: string;
};

/** A month of receipts for the Receipts tab. */
export type ReceiptMonth = {
  /** The first day of the month, local. */
  month: Date;
  /** The month's total in dollars (GET /spending/summary). */
  total: string;
  /** Newest first. */
  receipts: ListedReceipt[];
  /** The month before has receipts: the roll ends with "Older receipts →". */
  hasOlder: boolean;
};

/** A budget as "Groceries after this" shows it. */
export type BudgetLine = { name: string; currency: Currency; limit: string; spent: string };

/** Everything a receipt's page shows. */
export type ReceiptPage = {
  receipt: Receipt;
  categories: Category[];
  /** The budget of the receipt's category in the receipt's month, if there is one. */
  budget: BudgetLine | null;
};

/** What saving a receipt sends (POST /receipts/{id}/confirm), every field kept. */
export type ConfirmPayload = {
  shopName: string | null;
  receiptDate: string;
  currency: Currency;
  total: string;
  categoryId: number | null;
  lines: ReceiptLine[];
};
