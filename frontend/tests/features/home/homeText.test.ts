import type { RecentReceipt } from '@/features/home/domain/types';
import {
  budgetAccessibilityLabel,
  budgetAmounts,
  formatLimit,
  monthCaption,
  monthLabel,
  monthTotal,
  receiptMeta,
  receiptTotal,
  shopName,
} from '@/features/home/ui/homeText';

import { budget, emptyMonth, groceries, localIso, november, transport } from './fakes';

function recent(overrides: Partial<RecentReceipt> = {}): RecentReceipt {
  return {
    id: 31,
    shopName: 'Spinneys Achrafieh',
    receiptDate: '2026-11-18',
    createdAt: localIso(2026, 11, 18, 18, 42),
    currency: 'USD',
    total: '38.40',
    itemCount: 9,
    ...overrides,
  };
}

describe('the month', () => {
  it('names the month the backend summed and shows the total in dollars', () => {
    expect(monthLabel(november)).toBe('This month · November');
    expect(monthTotal(november)).toBe('$447.80');
    expect(monthTotal(emptyMonth)).toBe('$0.00');
  });

  it('says how dollars and pounds were combined, with only the parts that exist (D034)', () => {
    expect(monthCaption(november)).toBe('$412.60 + 3,150,000 LBP at 89,500 LBP per $');
    expect(monthCaption({ ...november, total: '35.20', usdPart: null })).toBe('3,150,000 LBP at 89,500 LBP per $');
    expect(monthCaption({ ...november, total: '412.60', lbpPart: null })).toBeNull();
  });

  it('says there is nothing yet before the first receipt (D037)', () => {
    expect(monthCaption(emptyMonth)).toBe('No receipts yet this month');
  });
});

describe('budgets', () => {
  it('shows spent and limit, dropping .00 from a whole dollar limit', () => {
    expect(budgetAmounts(transport)).toBe('$63.00 / $60');
    expect(budgetAmounts(groceries)).toBe('$186.40 / $250');
    expect(formatLimit('62.50', 'USD')).toBe('$62.50');
    expect(formatLimit('1000.00', 'USD')).toBe('$1,000');
  });

  it('shows pound budgets in pounds', () => {
    const gas = { ...budget(9, 'Fuel', '1350000.00', '2000000.00', '67.5', 'ok'), currency: 'LBP' as const };
    expect(budgetAmounts(gas)).toBe('1,350,000 LBP / 2,000,000 LBP');
  });

  it('reads a budget row to VoiceOver without the slash', () => {
    expect(budgetAccessibilityLabel(transport)).toBe('Transport, $63.00 of $60, Limit reached · 105%');
    expect(budgetAccessibilityLabel(groceries)).toBe('Groceries, $186.40 of $250');
  });
});

describe('recent receipts', () => {
  it('shows the total in its own currency', () => {
    expect(receiptTotal(recent())).toBe('$38.40');
    expect(receiptTotal(recent({ currency: 'LBP', total: '450000.00' }))).toBe('450,000 LBP');
  });

  it('shows date, time and items when the receipt was added the day it is dated', () => {
    expect(receiptMeta(recent())).toBe('18/11/2026 · 18:42 · 9 items');
    expect(receiptMeta(recent({ itemCount: 1 }))).toBe('18/11/2026 · 18:42 · 1 item');
  });

  it('leaves out a time from another day and a count of no items', () => {
    expect(receiptMeta(recent({ createdAt: localIso(2026, 11, 20, 9, 0) }))).toBe('18/11/2026 · 9 items');
    expect(receiptMeta(recent({ itemCount: 0 }))).toBe('18/11/2026 · 18:42');
  });

  it('has a plain stand-in for a receipt confirmed without a shop name', () => {
    expect(shopName(recent())).toBe('Spinneys Achrafieh');
    expect(shopName(recent({ shopName: null }))).toBe('Shop not named');
  });
});
