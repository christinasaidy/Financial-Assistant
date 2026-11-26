import type { BudgetsRepository } from '@/features/budgets/application/interfaces';
import { BudgetsError, type Budget, type BudgetCurrency, type Category, type MonthSpending } from '@/features/budgets/domain';

export function budget(
  categoryId: number,
  name: string,
  spent: string,
  limit: string,
  percentUsed: string,
  state: Budget['state'] = 'ok',
  currency: BudgetCurrency = 'USD',
): Budget {
  return { categoryId, name, currency, limit, spent, percentUsed, state };
}

/** The design's sample (DESIGN.md §5): Transport 63.00 / 60, Eating out 71.50 / 80, Groceries 186.40 / 250. */
export const transport = budget(1, 'Transport', '63.00', '60.00', '105.0', 'limit_reached');
export const eatingOut = budget(2, 'Eating out', '71.50', '80.00', '89.4', 'near');
export const groceries = budget(3, 'Groceries', '186.40', '250.00', '74.6');

/** November's spending: $447.80, of which $126.90 is outside the three budgets. */
export const novemberSpending: MonthSpending = {
  total: '447.80',
  categories: [
    { categoryId: 3, amount: '186.40' },
    { categoryId: 5, amount: '96.90' },
    { categoryId: 2, amount: '71.50' },
    { categoryId: 1, amount: '63.00' },
    { categoryId: null, amount: '30.00' },
  ],
  lbpPerUsd: '89500.00',
};

export const categories: Category[] = [
  { id: 1, name: 'Transport' },
  { id: 2, name: 'Eating out' },
  { id: 3, name: 'Groceries' },
  { id: 5, name: 'Pharmacy' },
  { id: 6, name: 'Bills' },
];

/** An in-memory backend for Budgets. */
export class FakeBudgetsRepository implements BudgetsRepository {
  byMonth = new Map<string, Budget[]>([['2026-11', [groceries, transport, eatingOut]]]);
  spendingByMonth = new Map<string, MonthSpending>([['2026-11', novemberSpending]]);
  categoryList: Category[] = categories;
  offline = false;
  /** Set to make saving fail with the backend's own message. */
  rejectWith: string | null = null;
  calls: string[] = [];

  async budgets(month: string): Promise<Budget[]> {
    this.record(`budgets ${month}`);
    return this.byMonth.get(month) ?? [];
  }

  async spending(month: string): Promise<MonthSpending> {
    this.record(`spending ${month}`);
    return this.spendingByMonth.get(month) ?? { total: '0.00', categories: [], lbpPerUsd: '89500.00' };
  }

  async categories(): Promise<Category[]> {
    this.record('categories');
    return this.categoryList;
  }

  async setBudget(categoryId: number, month: string, currency: BudgetCurrency, limit: string): Promise<void> {
    this.record(`set ${categoryId} ${month} ${currency} ${limit}`);
    if (this.rejectWith) throw new BudgetsError('rejected', this.rejectWith);
    const name = this.categoryList.find((category) => category.id === categoryId)?.name ?? '?';
    const list = (this.byMonth.get(month) ?? []).filter((item) => item.categoryId !== categoryId);
    this.byMonth.set(month, [...list, budget(categoryId, name, '0.00', limit, '0.0', 'ok', currency)]);
  }

  async removeBudget(categoryId: number): Promise<void> {
    this.record(`remove ${categoryId}`);
    for (const [month, list] of this.byMonth) {
      this.byMonth.set(month, list.filter((item) => item.categoryId !== categoryId));
    }
  }

  private record(call: string): void {
    this.calls.push(call);
    if (this.offline) throw new BudgetsError('network', 'Could not reach the server');
  }
}
