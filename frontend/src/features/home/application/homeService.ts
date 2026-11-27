import { toApiMonth } from '@/shared/format/dates';

import { HomeError } from '../domain/errors';
import {
  closestToLimit,
  everythingElse,
  HOME_RECENT_COUNT,
  invoiceNumber,
  newestConfirmed,
  olderMonths,
} from '../domain/rules';
import type { HomeOverview, RecentReceipt } from '../domain/types';
import type { HomeRepository } from './interfaces';

/**
 * The Home use case: the month's invoice and the newest receipts, in one call. It depends only on the
 * HomeRepository interface, so it runs the same against the backend or a fake.
 */
export class HomeService {
  private readonly repository: HomeRepository;

  constructor(repository: HomeRepository) {
    this.repository = repository;
  }

  /**
   * The month's spending, every budget (closest to its limit first) and "Everything else", the invoice's
   * number, the older months behind it, and the newest confirmed receipts with their category and item
   * count. The lists are fetched at the same time; the item counts follow, because the receipt list does not
   * include lines. Throws HomeError.
   */
  async loadOverview(month: Date): Promise<HomeOverview> {
    const apiMonth = toApiMonth(month);
    try {
      const [spending, budgets, receipts, categoryNames] = await Promise.all([
        this.repository.monthSpending(apiMonth),
        this.repository.budgets(apiMonth),
        this.repository.receipts(),
        this.repository.categoryNames(),
      ]);
      const shownBudgets = closestToLimit(budgets);
      const recent = await Promise.all(
        newestConfirmed(receipts, HOME_RECENT_COUNT).map(
          async (receipt): Promise<RecentReceipt> => ({
            id: receipt.id,
            shopName: receipt.shopName,
            receiptDate: receipt.receiptDate,
            createdAt: receipt.createdAt,
            currency: receipt.currency,
            total: receipt.total,
            itemCount: await this.repository.itemCount(receipt.id),
            category: receipt.categoryId === null ? null : (categoryNames.get(receipt.categoryId) ?? null),
            lbpPerUsd: receipt.lbpPerUsd ?? spending.lbpPerUsd,
          }),
        ),
      );
      return {
        spending,
        invoiceNumber: invoiceNumber(month, receipts),
        budgets: shownBudgets,
        everythingElse: everythingElse(spending.total, spending.categories, shownBudgets),
        olderMonths: olderMonths(month, receipts),
        recent,
      };
    } catch (error) {
      if (error instanceof HomeError) throw error;
      throw new HomeError('unexpected', error instanceof Error ? error.message : String(error));
    }
  }
}
