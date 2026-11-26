import type { BudgetLine, Category, ConfirmPayload, Receipt, ReceiptSummary } from '../domain';

/**
 * The port of the Receipts feature: what ReceiptsService needs from the backend. The data layer implements it
 * (apiReceiptsRepository.ts); tests use a fake. Implementations throw ReceiptsError.
 *
 * `month` is the API's month format, "2026-11".
 */
export interface ReceiptsRepository {
  /** All the user's receipts, without their items. */
  receipts(): Promise<ReceiptSummary[]>;
  /** One receipt with its items and review flags. */
  receipt(id: number): Promise<Receipt>;
  categories(): Promise<Category[]>;
  /** The month's total in dollars and today's LBP per USD. */
  monthTotal(month: string): Promise<{ total: string; lbpPerUsd: string }>;
  /** The month's budgets, by category id. */
  budgets(month: string): Promise<Map<number, BudgetLine>>;
  /** Saves the receipt's values (also corrects a confirmed receipt). */
  confirm(id: number, payload: ConfirmPayload): Promise<Receipt>;
}
