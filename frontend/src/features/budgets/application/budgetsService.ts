import { toApiMonth } from '@/shared/format/dates';

import { BudgetsError } from '../domain/errors';
import { unbudgetedCategories } from '../domain/rules';
import type { BudgetDraft, BudgetMonth } from '../domain/types';
import type { BudgetsRepository } from './interfaces';

function asBudgetsError(error: unknown): BudgetsError {
  if (error instanceof BudgetsError) return error;
  return new BudgetsError('unexpected', error instanceof Error ? error.message : String(error));
}

/**
 * The Budgets use cases: a month's budgets with the spending around them, and setting or removing a budget.
 * Depends only on the BudgetsRepository interface. Throws BudgetsError.
 */
export class BudgetsService {
  private readonly repository: BudgetsRepository;

  constructor(repository: BudgetsRepository) {
    this.repository = repository;
  }

  /** The month's budgets (closest to their limit first), its spending, and the categories without a budget. */
  async loadMonth(month: Date): Promise<BudgetMonth> {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const apiMonth = toApiMonth(first);
    try {
      const [budgets, spending, categories] = await Promise.all([
        this.repository.budgets(apiMonth),
        this.repository.spending(apiMonth),
        this.repository.categories(),
      ]);
      const ordered = [...budgets].sort(
        (a, b) => Number.parseFloat(b.percentUsed) - Number.parseFloat(a.percentUsed) || a.name.localeCompare(b.name),
      );
      return { month: first, budgets: ordered, spending, unbudgeted: unbudgetedCategories(categories, budgets) };
    } catch (error) {
      throw asBudgetsError(error);
    }
  }

  /** Sets the limit from the draft's month onwards. */
  async save(draft: BudgetDraft): Promise<void> {
    try {
      await this.repository.setBudget(draft.categoryId, toApiMonth(draft.month), draft.currency, draft.limit);
    } catch (error) {
      throw asBudgetsError(error);
    }
  }

  /** Removes the category's budget, for every month. */
  async remove(categoryId: number): Promise<void> {
    try {
      await this.repository.removeBudget(categoryId);
    } catch (error) {
      throw asBudgetsError(error);
    }
  }
}
