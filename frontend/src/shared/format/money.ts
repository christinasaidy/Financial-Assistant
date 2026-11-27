/**
 * Money on screen (D034): dollars as "$6.60", pounds as "450,000 LBP" (comma thousands, no decimals).
 *
 * The backend sends amounts as JSON strings ("6.6", "450000.00") so they stay exact. Formatting works on the
 * decimal digits as text, never through floating point, so "0.285" rounds to "$0.29" and not "$0.28".
 * Numbers are accepted too, for amounts the app computes itself.
 */
export type Currency = 'USD' | 'LBP';

export type Amount = string | number;

const DECIMAL = /^([+-])?(\d+)(?:\.(\d*))?$/;

/** Rounds a decimal (half away from zero) to `places` digits and returns its sign, whole part and fraction. */
function roundDecimal(amount: Amount, places: number): { negative: boolean; whole: string; fraction: string } {
  const text = typeof amount === 'number' ? numberToPlainString(amount) : amount.trim();
  const match = DECIMAL.exec(text);
  if (!match) {
    throw new Error(`Not a decimal amount: "${text}"`);
  }
  const [, sign, wholeDigits, fractionDigits = ''] = match;
  const padded = fractionDigits.padEnd(places + 1, '0');
  const kept = padded.slice(0, places);
  const roundUp = Number(padded[places]) >= 5;

  // Add 1 at the last kept place, carrying through the digits as text.
  const digits = (wholeDigits + kept).split('').map(Number);
  if (roundUp) {
    let index = digits.length - 1;
    while (index >= 0) {
      const digit = digits[index] as number;
      if (digit === 9) {
        digits[index] = 0;
        index -= 1;
      } else {
        digits[index] = digit + 1;
        break;
      }
    }
    if (index < 0) digits.unshift(1);
  }
  const all = digits.join('');
  const whole = all.slice(0, all.length - places).replace(/^0+(?=\d)/, '') || '0';
  const fraction = places > 0 ? all.slice(all.length - places) : '';
  const isZero = /^0*$/.test(whole + fraction);
  return { negative: sign === '-' && !isZero, whole, fraction };
}

function numberToPlainString(value: number): string {
  if (!Number.isFinite(value)) {
    throw new Error(`Not a finite amount: ${value}`);
  }
  // toFixed avoids exponent notation (1e21 and above are not money this app sees).
  return value.toFixed(10);
}

function groupThousands(whole: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** "$6.60", "$1,250.00", "-$3.10". */
export function formatUsd(amount: Amount): string {
  const { negative, whole, fraction } = roundDecimal(amount, 2);
  return `${negative ? '-' : ''}$${groupThousands(whole)}.${fraction}`;
}

/** "450,000 LBP", "-90,000 LBP". */
export function formatLbp(amount: Amount): string {
  const { negative, whole } = roundDecimal(amount, 0);
  return `${negative ? '-' : ''}${groupThousands(whole)} LBP`;
}

export function formatMoney(amount: Amount, currency: Currency): string {
  return currency === 'USD' ? formatUsd(amount) : formatLbp(amount);
}

/**
 * The line under a mixed total that says how it was combined (D034):
 * "$412.60 + 3,150,000 LBP at 89,500 LBP per $".
 */
export function formatCombinedLine(usdPart: Amount, lbpPart: Amount, lbpPerUsd: Amount): string {
  const rate = roundDecimal(lbpPerUsd, 0);
  return `${formatUsd(usdPart)} + ${formatLbp(lbpPart)} at ${groupThousands(rate.whole)} LBP per $`;
}

/**
 * A table cell of the invoice (DESIGN.md §5): no currency sign. Dollars with two decimals ("63.00",
 * "1,250.00"), pounds grouped without decimals ("450,000").
 */
export function formatCell(amount: Amount, currency: Currency): string {
  const { negative, whole, fraction } = roundDecimal(amount, currency === 'USD' ? 2 : 0);
  return `${negative ? '-' : ''}${groupThousands(whole)}${currency === 'USD' ? `.${fraction}` : ''}`;
}

/** A budget's limit in the invoice table: whole dollars without decimals ("60"), else like a cell ("62.50"). */
export function formatLimitCell(amount: Amount, currency: Currency): string {
  const cents = roundDecimal(amount, 2);
  if (currency === 'USD' && cents.fraction !== '00') return formatCell(amount, currency);
  return `${cents.negative ? '-' : ''}${groupThousands(roundDecimal(amount, 0).whole)}`;
}

/** The line under a mixed invoice total (DESIGN.md §4): "$412.60 + 3,150,000 LBP · 89,500". */
export function formatInvoiceLine(usdPart: Amount, lbpPart: Amount, lbpPerUsd: Amount): string {
  return `${formatUsd(usdPart)} + ${formatLbp(lbpPart)} · ${groupThousands(roundDecimal(lbpPerUsd, 0).whole)}`;
}

/** Under a pound amount, its dollar value at the receipt's rate (DESIGN.md §5): "≈ $5.03". */
export function formatApproxUsd(lbpAmount: Amount, lbpPerUsd: Amount): string {
  const usd = Number(lbpAmount) / Number(lbpPerUsd);
  return `≈ ${formatUsd(Number.isFinite(usd) ? usd : 0)}`;
}

/**
 * A pound amount short enough for the invoice's narrow columns (D049): from a million up, millions with at most
 * two decimals ("150M", "1.25M"), from a billion up, billions ("2.5B"); below a million, exact ("450,000").
 */
export function formatCompactLbp(amount: Amount): string {
  const { negative, whole } = roundDecimal(amount, 0);
  const value = Number(whole);
  const sign = negative ? '-' : '';
  const short = (divisor: number, unit: string) => {
    const scaled = Math.round((value / divisor) * 100) / 100;
    return `${sign}${String(scaled)}${unit}`;
  };
  if (value >= 1_000_000_000) return short(1_000_000_000, 'B');
  if (value >= 1_000_000) return short(1_000_000, 'M');
  return `${sign}${groupThousands(whole)}`;
}
