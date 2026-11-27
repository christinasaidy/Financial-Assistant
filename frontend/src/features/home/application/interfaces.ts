import type { BudgetUse, MonthSpending, ReceiptListing } from '../domain/types';

/**
 * The port of the Home feature: what HomeService needs from the backend, from its point of view. The data
 * layer implements it (apiHomeRepository.ts); tests use a fake. Implementations throw HomeError.
 *
 * `month` is the API's month format, "2026-11".
 */
export interface HomeRepository {
  /** The month's spending in dollars (only confirmed receipts count). */
  monthSpending(month: string): Promise<MonthSpending>;
  /** Every budget that applies to the month, with how much of it is used. */
  budgets(month: string): Promise<BudgetUse[]>;
  /** All the user's receipts, newest first, without their lines. */
  receipts(): Promise<ReceiptListing[]>;
  /** The user's categories by id, for the names under the receipts. */
  categoryNames(): Promise<Map<number, string>>;
  /** How many lines (items) a receipt has. */
  itemCount(receiptId: number): Promise<number>;
}
