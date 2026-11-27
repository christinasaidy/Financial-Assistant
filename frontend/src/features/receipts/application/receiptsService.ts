import { toApiMonth } from '@/shared/format/dates';

import {
  hasOlderThan,
  ReceiptsError,
  receiptsOfMonth,
  withCategory,
  withItemCategories,
  type ListedReceipt,
  type Receipt,
  type ReceiptMonth,
  type ReceiptPage,
} from '../domain';
import type { ReceiptsRepository } from './interfaces';

function asReceiptsError(error: unknown): ReceiptsError {
  if (error instanceof ReceiptsError) return error;
  return new ReceiptsError('unexpected', error instanceof Error ? error.message : String(error));
}

/**
 * The Receipts use cases: a month's receipts for the tab, one receipt's page, changing its category and
 * splitting its items. Depends only on the ReceiptsRepository interface. Throws ReceiptsError.
 */
export class ReceiptsService {
  private readonly repository: ReceiptsRepository;

  constructor(repository: ReceiptsRepository) {
    this.repository = repository;
  }

  /**
   * The month's confirmed receipts, newest first, each with its category name and item count, the month's total,
   * and whether older receipts exist. The item counts need each receipt (the list leaves items out).
   */
  async loadMonth(month: Date): Promise<ReceiptMonth> {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    try {
      const [all, categories, { total, lbpPerUsd }] = await Promise.all([
        this.repository.receipts(),
        this.repository.categories(),
        this.repository.monthTotal(toApiMonth(first)),
      ]);
      const names = new Map(categories.map((category) => [category.id, category.name]));
      const receipts = await Promise.all(
        receiptsOfMonth(all, first).map(async (summary): Promise<ListedReceipt> => {
          const full = await this.repository.receipt(summary.id);
          return {
            id: summary.id,
            shopName: summary.shopName,
            receiptDate: summary.receiptDate,
            currency: summary.currency,
            total: summary.total,
            categoryId: summary.categoryId,
            category: summary.categoryId === null ? null : (names.get(summary.categoryId) ?? null),
            itemCount: full.lines.length,
            lbpPerUsd: summary.lbpPerUsd ?? lbpPerUsd,
          };
        }),
      );
      return { month: first, total, receipts, hasOlder: hasOlderThan(all, first) };
    } catch (error) {
      throw asReceiptsError(error);
    }
  }

  /** One receipt, the categories, and the budget of its category in its month. */
  async loadReceipt(id: number): Promise<ReceiptPage> {
    try {
      const [receipt, categories] = await Promise.all([this.repository.receipt(id), this.repository.categories()]);
      let budget = null;
      if (receipt.categoryId !== null && receipt.receiptDate) {
        const budgets = await this.repository.budgets(receipt.receiptDate.slice(0, 7));
        budget = budgets.get(receipt.categoryId) ?? null;
      }
      return { receipt, categories, budget };
    } catch (error) {
      throw asReceiptsError(error);
    }
  }

  /** Change category: the receipt and all its items move to it (D050). */
  async changeCategory(receipt: Receipt, categoryId: number | null): Promise<Receipt> {
    return this.save(receipt.id, () => withCategory(receipt, categoryId));
  }

  /** Split items: each item's own category (one per item, in order). */
  async splitItems(receipt: Receipt, categories: readonly (number | null)[]): Promise<Receipt> {
    return this.save(receipt.id, () => withItemCategories(receipt, categories));
  }

  private async save(id: number, payload: () => ReturnType<typeof withCategory>): Promise<Receipt> {
    try {
      return await this.repository.confirm(id, payload());
    } catch (error) {
      throw asReceiptsError(error);
    }
  }
}
