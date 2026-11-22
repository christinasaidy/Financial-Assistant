import { formatCombinedLine, formatLbp, formatMoney, formatUsd } from '@/shared/format/money';

describe('formatUsd (D034)', () => {
  it.each([
    ['6.6', '$6.60'],
    ['6.60', '$6.60'],
    ['0', '$0.00'],
    ['447.8', '$447.80'],
    ['1250', '$1,250.00'],
    ['1234567.891', '$1,234,567.89'],
    [38.4, '$38.40'],
  ])('%p -> %s', (amount, expected) => {
    expect(formatUsd(amount)).toBe(expected);
  });

  it('rounds half away from zero on the decimal digits, not through floating point', () => {
    expect(formatUsd('0.285')).toBe('$0.29');
    expect(formatUsd('1.005')).toBe('$1.01');
    expect(formatUsd('9.995')).toBe('$10.00');
    expect(formatUsd('999.999')).toBe('$1,000.00');
  });

  it('puts the minus before the dollar sign, and never shows -$0.00', () => {
    expect(formatUsd('-3.1')).toBe('-$3.10');
    expect(formatUsd('-0.001')).toBe('$0.00');
  });
});

describe('formatLbp (D034)', () => {
  it.each([
    ['450000', '450,000 LBP'],
    ['450000.00', '450,000 LBP'],
    ['3150000', '3,150,000 LBP'],
    ['999.5', '1,000 LBP'],
    ['0', '0 LBP'],
    ['-90000', '-90,000 LBP'],
  ])('%p -> %s', (amount, expected) => {
    expect(formatLbp(amount)).toBe(expected);
  });
});

it('formatMoney picks the format by currency', () => {
  expect(formatMoney('6.6', 'USD')).toBe('$6.60');
  expect(formatMoney('450000', 'LBP')).toBe('450,000 LBP');
});

it('formatCombinedLine says how a mixed total was combined (D034)', () => {
  expect(formatCombinedLine('412.6', '3150000', '89500.00')).toBe('$412.60 + 3,150,000 LBP at 89,500 LBP per $');
});

it('refuses text that is not an amount', () => {
  expect(() => formatUsd('abc')).toThrow('Not a decimal amount');
  expect(() => formatUsd(Number.NaN)).toThrow('Not a finite amount');
});
