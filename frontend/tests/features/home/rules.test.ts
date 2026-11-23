import {
  barWidthPercent,
  budgetStateWords,
  budgetTone,
  closestToLimit,
  greeting,
  isMonthEmpty,
  itemCountWords,
  newestConfirmed,
  wholePercent,
} from '@/features/home/domain/rules';

import {
  abouRami,
  awaiting,
  budget,
  eatingOut,
  emptyMonth,
  fuel,
  groceries,
  listing,
  november,
  spinneys,
  transport,
  zaatar,
} from './fakes';

describe('greeting', () => {
  it('greets by first name, or just Hello when there is none', () => {
    expect(greeting('Christina')).toBe('Hello, Christina');
    expect(greeting('  Maya ')).toBe('Hello, Maya');
    expect(greeting(null)).toBe('Hello');
    expect(greeting(undefined)).toBe('Hello');
    expect(greeting('   ')).toBe('Hello');
  });
});

describe('isMonthEmpty', () => {
  it('is empty only when no receipt was counted this month', () => {
    expect(isMonthEmpty(emptyMonth)).toBe(true);
    expect(isMonthEmpty(november)).toBe(false);
    // Receipts awaiting review are not counted, so the month still reads empty.
    expect(isMonthEmpty({ ...emptyMonth, awaitingReview: 2 })).toBe(true);
  });
});

describe('closestToLimit', () => {
  it('keeps the three with the highest percent used, closest first', () => {
    expect(closestToLimit([fuel, groceries, transport, eatingOut]).map((b) => b.name)).toEqual([
      'Transport',
      'Eating out',
      'Groceries',
    ]);
  });

  it('compares percentages as numbers, not as text', () => {
    const nine = budget(5, 'Gifts', '9.00', '100.00', '9.0', 'ok');
    const eighty = budget(6, 'Pharmacy', '80.00', '100.00', '80.0', 'near');
    const hundredTen = budget(7, 'Phone', '110.00', '100.00', '110.0', 'limit_reached');
    expect(closestToLimit([nine, eighty, hundredTen]).map((b) => b.name)).toEqual(['Phone', 'Pharmacy', 'Gifts']);
  });

  it('breaks ties by name and does not change the list it is given', () => {
    const a = budget(5, 'Water', '50.00', '100.00', '50.0', 'ok');
    const b = budget(6, 'Bakery', '25.00', '50.00', '50.0', 'ok');
    const input = [a, b];
    expect(closestToLimit(input).map((item) => item.name)).toEqual(['Bakery', 'Water']);
    expect(input).toEqual([a, b]);
  });

  it('returns fewer when there are fewer, and nothing for no budgets', () => {
    expect(closestToLimit([groceries])).toEqual([groceries]);
    expect(closestToLimit([])).toEqual([]);
    expect(closestToLimit([groceries, fuel], 0)).toEqual([]);
  });
});

describe('percentages and bars', () => {
  it('rounds the shown percentage down, so near never reads 100%', () => {
    expect(wholePercent('89.4')).toBe(89);
    expect(wholePercent('99.9')).toBe(99);
    expect(wholePercent('105.0')).toBe(105);
    expect(wholePercent('0.0')).toBe(0);
    expect(wholePercent('not a number')).toBe(0);
  });

  it('fills the bar up to 100% and never past it', () => {
    expect(barWidthPercent('74.6')).toBe(74.6);
    expect(barWidthPercent('100.0')).toBe(100);
    expect(barWidthPercent('250.0')).toBe(100);
    expect(barWidthPercent('0.0')).toBe(0);
    expect(barWidthPercent('-3')).toBe(0);
  });
});

describe('budget states', () => {
  it('colours fine budgets ink, near ochre and reached red', () => {
    expect(budgetTone('ok')).toBe('ink');
    expect(budgetTone('near')).toBe('near-limit');
    expect(budgetTone('limit_reached')).toBe('limit-reached');
  });

  it('says the state in words when it needs attention', () => {
    expect(budgetStateWords(eatingOut)).toBe('Near limit · 89%');
    expect(budgetStateWords(transport)).toBe('Limit reached · 105%');
    expect(budgetStateWords(groceries)).toBeNull();
    expect(budgetStateWords({ state: 'near', percentUsed: '99.9' })).toBe('Near limit · 99%');
  });
});

describe('newestConfirmed', () => {
  it('keeps the backend order and only confirmed receipts with a date and total', () => {
    const processing = listing(33, null, '2026-11-20', '0', 'USD', spinneys.createdAt, 'processing');
    const noTotal = { ...listing(34, 'Bliss House', '2026-11-20', '0', 'USD', spinneys.createdAt), total: null };
    const older = { ...abouRami, id: 28, receiptDate: '2026-11-02' };
    const all = [awaiting, processing, noTotal, spinneys, zaatar, abouRami, older];
    expect(newestConfirmed(all).map((receipt) => receipt.id)).toEqual([31, 30, 29]);
  });

  it('returns what there is', () => {
    expect(newestConfirmed([zaatar])).toEqual([zaatar]);
    expect(newestConfirmed([])).toEqual([]);
    expect(newestConfirmed([awaiting])).toEqual([]);
  });
});

describe('itemCountWords', () => {
  it('counts items, singular for one, nothing for none', () => {
    expect(itemCountWords(9)).toBe('9 items');
    expect(itemCountWords(1)).toBe('1 item');
    expect(itemCountWords(0)).toBeNull();
  });
});
