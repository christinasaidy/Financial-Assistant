import type { Budget, BudgetCurrency, Category, MonthSpending } from '../domain/types';

/**
 * The port of the Budgets feature: what BudgetsService needs from the backend. The data layer implements it
 * (apiBudgetsRepository.ts); tests use a fake. Implementations throw BudgetsError.
 *
 * `month` is the API's month format, "2026-11".
 */
export interface BudgetsRepository {
  /** Every budget that applies to the month, with how much of it is used. */
  budgets(month: string): Promise<Budget[]>;
  /** The month's spending by category, in dollars. */
  spending(month: string): Promise<MonthSpending>;
  /** The user's categories. */
  categories(): Promise<Category[]>;
  /** Sets the category's limit from `month` onwards (earlier months keep theirs). */
  setBudget(categoryId: number, month: string, currency: BudgetCurrency, limit: string): Promise<void>;
  /** Removes the category's budget, for every month. */
  removeBudget(categoryId: number): Promise<void>;
}
