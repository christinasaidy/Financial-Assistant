import {
  barWidthPercent,
  billedTo,
  budgetRemainder,
  closestToLimit,
  everythingElse,
  invoiceNumber,
  isMonthEmpty,
  isOver,
  itemCountWords,
  newestConfirmed,
  olderMonths,
  receiptSubline,
} from '@/features/home/domain/rules';

import { awaiting, eatingOut, emptyMonth, fuel, groceries, november, septemberReceipt, spinneys, transport, zaatar } from './fakes';

const nov = new Date(2026, 10, 25);

describe('the invoice header', () => {
  it('bills the user by first name, or "you"', () => {
    expect(billedTo('Christina')).toBe('Billed to Christina');
    expect(billedTo('  ')).toBe('Billed to you');
    expect(billedTo(null)).toBe('Billed to you');
  });

  it('numbers one invoice a month from the first receipt: Nº 0001 for a new user', () => {
    expect(invoiceNumber(nov, [])).toBe(1);
    expect(invoiceNumber(nov, [spinneys, zaatar])).toBe(1);
    expect(invoiceNumber(nov, [spinneys, septemberReceipt])).toBe(3);
    // A receipt still being checked does not count.
    expect(invoiceNumber(nov, [{ ...septemberReceipt, status: 'needs_review' }, spinneys])).toBe(1);
  });

  it('peeks the two months before once there are older receipts, and none for a new user', () => {
    expect(olderMonths(nov, [spinneys, septemberReceipt])).toEqual(['2026-09-01', '2026-10-01']);
    expect(olderMonths(nov, [spinneys, zaatar])).toEqual([]);
    expect(olderMonths(new Date(2027, 0, 5), [spinneys])).toEqual(['2026-11-01', '2026-12-01']);
  });

  it('knows a month with nothing confirmed is blank', () => {
    expect(isMonthEmpty(emptyMonth)).toBe(true);
    expect(isMonthEmpty(november)).toBe(false);
  });
});

describe('the budget table', () => {
  it('lists every budget, over-budget first, then by % used, then by name (D048)', () => {
    expect(closestToLimit([groceries, fuel, transport, eatingOut]).map((budget) => budget.name)).toEqual([
      'Transport',
      'Eating out',
      'Groceries',
      'Fuel',
    ]);
    // Untouched budgets tie at 0% and keep every one of them, in name order (Transport is no longer left out).
    const unused = (id: number, name: string) => ({ ...fuel, categoryId: id, name, spent: '0.00', percentUsed: '0.0' });
    expect(closestToLimit([unused(1, 'Transport'), unused(2, 'Dining'), unused(3, 'Shopping'), unused(4, 'Health')]).map((budget) => budget.name)).toEqual([
      'Dining',
      'Health',
      'Shopping',
      'Transport',
    ]);
  });

  it('says what is left, or by how much a budget is over (DESIGN.md §4)', () => {
    expect(budgetRemainder(eatingOut)).toEqual({ kind: 'left', amount: '8.50' });
    expect(budgetRemainder(transport)).toEqual({ kind: 'over', amount: '3.00' });
    expect(isOver(transport)).toBe(true);
    expect(isOver(eatingOut)).toBe(false);
    expect(isOver({ spent: '60.00', limit: '60.00' })).toBe(false);
  });

  it('fills the bar up to its limit, never past it', () => {
    expect(barWidthPercent('89.4')).toBe(89.4);
    expect(barWidthPercent('105.0')).toBe(100);
    expect(barWidthPercent('nonsense')).toBe(0);
  });

  it('puts the rest of the total under "Everything else", so the rows add up to TOTAL', () => {
    const shown = [transport, eatingOut, groceries];
    expect(everythingElse(november.total, november.categories, shown)).toBe('126.90');
    // With fewer budgets, more of the total is Everything else.
    expect(everythingElse(november.total, november.categories, [transport])).toBe('384.80');
    expect(everythingElse('0.00', [], [])).toBe('0.00');
  });
});

describe('recent receipts', () => {
  it('lists only confirmed receipts, newest first', () => {
    expect(newestConfirmed([awaiting, spinneys, zaatar]).map((receipt) => receipt.id)).toEqual([31, 30]);
  });

  it('writes "Groceries · 9 items", with only the parts it knows', () => {
    expect(receiptSubline('Groceries', 9)).toBe('Groceries · 9 items');
    expect(receiptSubline(null, 1)).toBe('1 item');
    expect(receiptSubline('Groceries', 0)).toBe('Groceries');
    expect(receiptSubline(null, 0)).toBeNull();
    expect(itemCountWords(2)).toBe('2 items');
  });
});
