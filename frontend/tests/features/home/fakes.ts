import type { HomeRepository } from '@/features/home/application/interfaces';
import { HomeError } from '@/features/home/domain/errors';
import type { BudgetUse, MonthSpending, ReceiptListing } from '@/features/home/domain/types';

/** November 2026 as in the Home mockup: $412.60 + 3,150,000 LBP at 89,500 LBP per $ = $447.80. */
export const november: MonthSpending = {
  month: '2026-11-01',
  total: '447.80',
  receiptCount: 14,
  usdPart: '412.60',
  lbpPart: '3150000.00',
  lbpPerUsd: '89500.00',
  awaitingReview: 0,
};

export const emptyMonth: MonthSpending = {
  month: '2026-11-01',
  total: '0.00',
  receiptCount: 0,
  usdPart: null,
  lbpPart: null,
  lbpPerUsd: '89500.00',
  awaitingReview: 0,
};

export function budget(
  categoryId: number,
  name: string,
  spent: string,
  limit: string,
  percentUsed: string,
  state: BudgetUse['state'],
): BudgetUse {
  return { categoryId, name, currency: 'USD', limit, spent, percentUsed, state };
}

export const transport = budget(1, 'Transport', '63.00', '60.00', '105.0', 'limit_reached');
export const eatingOut = budget(2, 'Eating out', '71.50', '80.00', '89.4', 'near');
export const groceries = budget(3, 'Groceries', '186.40', '250.00', '74.6', 'ok');
export const fuel = budget(4, 'Fuel', '20.00', '100.00', '20.0', 'ok');

export function listing(
  id: number,
  shopName: string | null,
  receiptDate: string,
  total: string,
  currency: 'USD' | 'LBP',
  createdAt: string,
  status = 'confirmed',
): ReceiptListing {
  return { id, status, shopName, receiptDate, currency, total, createdAt };
}

/** Added on the day printed on them, at a local wall-clock time, so the tests pass in any time zone. */
export const spinneys = listing(31, 'Spinneys Achrafieh', '2026-11-18', '38.40', 'USD', localIso(2026, 11, 18, 18, 42));
export const zaatar = listing(30, 'Zaatar w Zeit', '2026-11-17', '450000.00', 'LBP', localIso(2026, 11, 17, 13, 5));
export const abouRami = listing(29, 'Abou Rami', '2026-11-12', '6.60', 'USD', localIso(2026, 11, 12, 9, 15));
export const awaiting = listing(
  32,
  'Charcutier Aoun',
  '2026-11-19',
  '24.10',
  'USD',
  localIso(2026, 11, 19, 10, 0),
  'needs_review',
);

/** A date-time string for a wall-clock time in the phone's own time zone. */
export function localIso(year: number, month: number, day: number, hour: number, minute: number): string {
  return new Date(year, month - 1, day, hour, minute).toISOString();
}

/** An in-memory backend for Home. */
export class FakeHomeRepository implements HomeRepository {
  spending: MonthSpending = november;
  budgetList: BudgetUse[] = [transport, eatingOut, groceries];
  receiptList: ReceiptListing[] = [spinneys, zaatar];
  itemCounts = new Map<number, number>([
    [31, 9],
    [30, 2],
    [29, 1],
  ]);
  /** Set to make every call fail as if the phone were offline. */
  offline = false;
  calls: string[] = [];

  async monthSpending(month: string): Promise<MonthSpending> {
    this.record(`summary ${month}`);
    return this.spending;
  }

  async budgets(month: string): Promise<BudgetUse[]> {
    this.record(`budgets ${month}`);
    return this.budgetList;
  }

  async receipts(): Promise<ReceiptListing[]> {
    this.record('receipts');
    return this.receiptList;
  }

  async itemCount(receiptId: number): Promise<number> {
    this.record(`receipt ${receiptId}`);
    return this.itemCounts.get(receiptId) ?? 0;
  }

  private record(call: string): void {
    this.calls.push(call);
    if (this.offline) throw new HomeError('network', 'Could not reach the server');
  }
}
