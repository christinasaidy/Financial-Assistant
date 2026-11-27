import {
  barWidthPercent,
  checkLimit,
  daysLeft,
  everythingElse,
  isCurrentMonth,
  isOver,
  perDay,
  remainder,
  sheetSummary,
  shiftMonth,
  unbudgetedCategories,
} from '@/features/budgets/domain';
import { daysLeftLabel, leftAcross, perDayLine, remainderLine, roundDollars, spentOfLimit } from '@/features/budgets/ui/budgetsText';

import { budget, categories, eatingOut, groceries, novemberSpending, transport } from './fakes';

const NOV_26 = new Date(2026, 10, 26, 10, 0);
const november = new Date(2026, 10, 1);

describe('the budget sheet (design/screens/06-budgets.png)', () => {
  it('adds up the design’s sample: $320.90 of $390, $69.10 left across 3 budgets, 82%', () => {
    const summary = sheetSummary([transport, eatingOut, groceries], '89500');
    expect(summary).toEqual({ spent: '320.90', budgeted: '390.00', left: '69.10', count: 3, percent: 82 });
    expect(roundDollars(summary.budgeted)).toBe('$390');
    expect(leftAcross(summary)).toBe('$69.10 left across 3 budgets');
  });

  it('counts pound budgets in dollars at today’s rate', () => {
    const bakery = budget(9, 'Bakery', '895000', '1790000', '50.0', 'ok', 'LBP');
    expect(sheetSummary([bakery], '89500')).toMatchObject({ spent: '10.00', budgeted: '20.00', percent: 50 });
  });

  it('is blank with no budgets', () => {
    expect(sheetSummary([], '89500')).toEqual({ spent: '0.00', budgeted: '0.00', left: '0.00', count: 0, percent: 0 });
  });

  it('counts the days after today in the current month only', () => {
    expect(daysLeft(november, NOV_26)).toBe(4);
    expect(daysLeft(november, new Date(2026, 10, 30))).toBe(0);
    expect(daysLeft(new Date(2026, 9, 1), NOV_26)).toBeNull();
    expect(daysLeftLabel(4)).toBe('4 days left');
    expect(daysLeftLabel(1)).toBe('1 day left');
    expect(daysLeftLabel(0)).toBe('Last day');
    expect(daysLeftLabel(null)).toBe('Month ended');
    expect(isCurrentMonth(november, NOV_26)).toBe(true);
  });
});

describe('a budget slip', () => {
  it('shows spent / limit, what is left or over, and the pace (DESIGN.md §5)', () => {
    expect(spentOfLimit(transport)).toEqual({ spent: '63.00', limit: '60' });
    expect(isOver(transport)).toBe(true);
    expect(remainderLine(transport)).toEqual({ text: 'Over by $3.00', over: true });
    expect(perDayLine(transport, 4)).toBe('$0.00 a day');
    expect(remainderLine(eatingOut)).toEqual({ text: '$8.50 left', over: false });
    expect(perDayLine(eatingOut, 4)).toBe('$2.13 a day');
    expect(perDayLine(groceries, 4)).toBe('$15.90 a day');
    expect(perDayLine(groceries, null)).toBeNull();
  });

  it('spends what is left on the last day, and fills the bar up to the limit only', () => {
    expect(perDay(eatingOut, 0)).toBe('8.50');
    expect(remainder(groceries)).toEqual({ kind: 'left', amount: '63.60' });
    expect(barWidthPercent('63.00', '60.00')).toBe(100);
    expect(barWidthPercent('0', '0')).toBe(0);
  });

  it('writes pound budgets in pounds', () => {
    const bakery = budget(9, 'Bakery', '1250000', '3000000', '41.7', 'ok', 'LBP');
    expect(spentOfLimit(bakery)).toEqual({ spent: '1,250,000', limit: '3,000,000' });
    expect(remainderLine(bakery).text).toBe('1,750,000 LBP left');
    expect(perDayLine(bakery, 4)).toBe('437,500 LBP a day');
  });
});

describe('everything else and new budgets', () => {
  it('is the month’s spending outside every budget: $126.90 in the design', () => {
    expect(everythingElse(novemberSpending, [transport, eatingOut, groceries])).toBe('126.90');
    expect(everythingElse(novemberSpending, [])).toBe('447.80');
  });

  it('offers only the categories without a budget, by name', () => {
    expect(unbudgetedCategories(categories, [transport, eatingOut, groceries]).map((category) => category.name)).toEqual(['Bills', 'Pharmacy']);
  });

  it('moves a month back and forward, across years', () => {
    expect(shiftMonth(new Date(2026, 0, 1), -1)).toEqual(new Date(2025, 11, 1));
    expect(shiftMonth(new Date(2026, 11, 1), 1)).toEqual(new Date(2027, 0, 1));
  });
});

describe('checking a typed limit', () => {
  it('takes positive dollars with up to two decimals, and whole pounds with commas', () => {
    expect(checkLimit(' 250 ', 'USD')).toEqual({ limit: '250' });
    expect(checkLimit('62.50', 'USD')).toEqual({ limit: '62.50' });
    expect(checkLimit('3,000,000', 'LBP')).toEqual({ limit: '3000000' });
  });

  it('names what is wrong', () => {
    expect(checkLimit('', 'USD')).toEqual({ problem: 'limit-missing' });
    expect(checkLimit('abc', 'USD')).toEqual({ problem: 'limit-not-a-number' });
    expect(checkLimit('-5', 'USD')).toEqual({ problem: 'limit-not-a-number' });
    expect(checkLimit('0', 'USD')).toEqual({ problem: 'limit-not-positive' });
    expect(checkLimit('1.234', 'USD')).toEqual({ problem: 'limit-too-precise' });
    expect(checkLimit('1000.5', 'LBP')).toEqual({ problem: 'limit-too-precise' });
  });
});
