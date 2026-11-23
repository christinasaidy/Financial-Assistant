import { toApiMonth } from '@/shared/format/dates';

import { HomeError } from '../domain/errors';
import { closestToLimit, HOME_BUDGET_COUNT, HOME_RECENT_COUNT, newestConfirmed } from '../domain/rules';
import type { HomeOverview, RecentReceipt } from '../domain/types';
import type { HomeRepository } from './interfaces';

/**
 * The Home use case: everything the screen shows for one month, in one call. It depends only on the
 * HomeRepository interface, so it runs the same against the backend or a fake.
 */
export class HomeService {
  private readonly repository: HomeRepository;

  constructor(repository: HomeRepository) {
    this.repository = repository;
  }

  /**
   * The month's spending, the three budgets closest to their limit and the newest confirmed receipts
   * (D035, D036). The three lists are fetched at the same time; the item counts of the shown receipts
   * follow, because the receipt list does not include lines. Throws HomeError.
   */
  async loadOverview(month: Date): Promise<HomeOverview> {
    const apiMonth = toApiMonth(month);
    try {
      const [spending, budgets, receipts] = await Promise.all([
        this.repository.monthSpending(apiMonth),
        this.repository.budgets(apiMonth),
        this.repository.receipts(),
      ]);
      const shown = newestConfirmed(receipts, HOME_RECENT_COUNT);
      const recent = await Promise.all(
        shown.map(
          async (receipt): Promise<RecentReceipt> => ({
            id: receipt.id,
            shopName: receipt.shopName,
            receiptDate: receipt.receiptDate,
            createdAt: receipt.createdAt,
            currency: receipt.currency,
            total: receipt.total,
            itemCount: await this.repository.itemCount(receipt.id),
          }),
        ),
      );
      return { spending, budgets: closestToLimit(budgets, HOME_BUDGET_COUNT), recent };
    } catch (error) {
      if (error instanceof HomeError) throw error;
      throw new HomeError('unexpected', error instanceof Error ? error.message : String(error));
    }
  }
}
