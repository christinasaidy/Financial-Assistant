import type { RecentReceipt } from '@/features/home/domain/types';
import {
  invoiceLabel,
  invoiceLine,
  limitCell,
  monthLabel,
  monthTotal,
  olderMonthLabel,
  receiptAmount,
  receiptApproxUsd,
  receiptDay,
  remainderText,
  spentCell,
} from '@/features/home/ui/homeText';

import { budget, eatingOut, emptyMonth, november, transport } from './fakes';

function recent(overrides: Partial<RecentReceipt>): RecentReceipt {
  return {
    id: 1,
    shopName: 'Zaatar w Zeit',
    receiptDate: '2026-11-17',
    createdAt: '2026-11-17T11:05:00Z',
    currency: 'LBP',
    total: '450000.00',
    itemCount: 2,
    category: 'Eating out',
    lbpPerUsd: '89500.00',
    ...overrides,
  };
}

describe('the invoice in words (design/screens/03-home.png)', () => {
  it('numbers and dates the invoice', () => {
    expect(invoiceLabel(447)).toBe('Invoice Nº 0447');
    expect(invoiceLabel(1)).toBe('Invoice Nº 0001');
    expect(monthLabel(november)).toBe('Nov 2026');
    expect(olderMonthLabel('2026-09-01')).toBe('Sep');
    expect(monthTotal(november)).toBe('$447.80');
  });

  it('writes the line under the total with only the parts that exist', () => {
    expect(invoiceLine(november)).toEqual({ text: '$412.60 + 3,150,000 LBP · 89,500', blank: false });
    expect(invoiceLine({ ...november, usdPart: null })).toEqual({ text: '3,150,000 LBP · 89,500', blank: false });
    expect(invoiceLine({ ...november, lbpPart: null })).toBeNull();
    expect(invoiceLine(emptyMonth)).toEqual({ text: 'A blank invoice. It fills itself in as you scan.', blank: true });
  });

  it('fills the table cells without a currency sign', () => {
    expect(limitCell(transport)).toBe('60');
    expect(limitCell(budget(9, 'Coffee', '10.00', '62.50', '16.0', 'ok'))).toBe('62.50');
    expect(spentCell(eatingOut)).toBe('71.50');
    expect(remainderText(eatingOut)).toBe('8.50 left');
    expect(remainderText(transport)).toBe('+3.00 over');
    const pounds = { ...budget(9, 'Bakery', '1250000.00', '3000000.00', '41.7', 'ok' as const), currency: 'LBP' as const };
    expect(limitCell(pounds)).toBe('3,000,000');
    expect(remainderText(pounds)).toBe('1,750,000 left');
  });
});

describe('a recent receipt in words', () => {
  it('splits the date into the day and the month', () => {
    expect(receiptDay(recent({}))).toEqual({ day: '17', month: 'Nov' });
  });

  it('shows pounds with their dollar value at the receipt’s rate, and dollars alone', () => {
    expect(receiptAmount(recent({}))).toBe('450,000 LBP');
    expect(receiptApproxUsd(recent({}))).toBe('≈ $5.03');
    expect(receiptAmount(recent({ currency: 'USD', total: '38.40' }))).toBe('$38.40');
    expect(receiptApproxUsd(recent({ currency: 'USD', total: '38.40' }))).toBeNull();
  });
});
