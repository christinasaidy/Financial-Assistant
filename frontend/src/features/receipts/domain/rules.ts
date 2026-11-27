/**
 * The Receipts tab's and a receipt page's rules, as pure functions.
 */
import type { Category, ConfirmPayload, ListedReceipt, Receipt, ReceiptLine, ReceiptSummary } from './types';

/** A receipt the list shows: confirmed, with its date, currency and total. */
export type Listable = ReceiptSummary & { receiptDate: string; currency: 'USD' | 'LBP'; total: string };

export function isListed(receipt: ReceiptSummary): receipt is Listable {
  return receipt.status === 'confirmed' && receipt.receiptDate !== null && receipt.currency !== null && receipt.total !== null;
}

function monthOf(date: string): string {
  return date.slice(0, 7);
}

/** "2026-11" for a local month start. */
export function monthKey(month: Date): string {
  return `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}`;
}

/** The month's confirmed receipts, newest first (by printed date, then the newest added). */
export function receiptsOfMonth(receipts: readonly ReceiptSummary[], month: Date): Listable[] {
  const key = monthKey(month);
  const listed: Listable[] = receipts.filter(isListed);
  return listed
    .filter((receipt) => monthOf(receipt.receiptDate) === key)
    .sort((a, b) => b.receiptDate.localeCompare(a.receiptDate) || b.createdAt.localeCompare(a.createdAt));
}

/** Whether any confirmed receipt is from before the month ("Older receipts →"). */
export function hasOlderThan(receipts: readonly ReceiptSummary[], month: Date): boolean {
  const key = monthKey(month);
  return receipts.filter(isListed).some((receipt) => monthOf(receipt.receiptDate) < key);
}

/** Monday of the week `today` is in, as "2026-11-23". */
function weekStart(today: Date): string {
  const day = (today.getDay() + 6) % 7;
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - day);
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, '0')}-${String(monday.getDate()).padStart(2, '0')}`;
}

export type ReceiptGroup = { title: string; receipts: ListedReceipt[] };

/**
 * The roll's groups (screen 13): "This week" (since Monday) and "Earlier in November"; a month with nothing this
 * week has one group, "In October".
 */
export function groupReceipts(receipts: readonly ListedReceipt[], monthName: string, today: Date): ReceiptGroup[] {
  const start = weekStart(today);
  const thisWeek = receipts.filter((receipt) => receipt.receiptDate >= start);
  const earlier = receipts.filter((receipt) => receipt.receiptDate < start);
  if (thisWeek.length === 0) return earlier.length > 0 ? [{ title: `In ${monthName}`, receipts: earlier }] : [];
  const groups: ReceiptGroup[] = [{ title: 'This week', receipts: thisWeek }];
  if (earlier.length > 0) groups.push({ title: `Earlier in ${monthName}`, receipts: earlier });
  return groups;
}

/** A filter chip: All, a category, or Other (receipts with no category). */
export type Filter = { key: 'all' } | { key: 'category'; id: number; name: string } | { key: 'other' };

/** The chips (screen 13): All, the month's categories (most receipts first, then by name), then Other if any have none. */
export function filtersFor(receipts: readonly ListedReceipt[]): Filter[] {
  const counts = new Map<number, { name: string; count: number }>();
  for (const receipt of receipts) {
    if (receipt.categoryId === null || receipt.category === null) continue;
    const found = counts.get(receipt.categoryId) ?? { name: receipt.category, count: 0 };
    counts.set(receipt.categoryId, { ...found, count: found.count + 1 });
  }
  const categories = [...counts.entries()]
    .sort(([, a], [, b]) => b.count - a.count || a.name.localeCompare(b.name))
    .map(([id, { name }]): Filter => ({ key: 'category', id, name }));
  const other = receipts.some((receipt) => receipt.categoryId === null) ? [{ key: 'other' } as const] : [];
  return [{ key: 'all' }, ...categories, ...other];
}

export function sameFilter(a: Filter, b: Filter): boolean {
  if (a.key === 'category' && b.key === 'category') return a.id === b.id;
  return a.key === b.key;
}

/** The receipts a chip and the search words keep. Search looks at the shop and the category. */
export function filterReceipts(receipts: readonly ListedReceipt[], filter: Filter, search = ''): ListedReceipt[] {
  const words = search.trim().toLowerCase();
  return receipts.filter((receipt) => {
    if (filter.key === 'category' && receipt.categoryId !== filter.id) return false;
    if (filter.key === 'other' && receipt.categoryId !== null) return false;
    if (!words) return true;
    return `${receipt.shopName ?? ''} ${receipt.category ?? ''}`.toLowerCase().includes(words);
  });
}

function number(value: string | null): number {
  const parsed = Number.parseFloat(value ?? '');
  return Number.isFinite(parsed) ? parsed : 0;
}

function plain(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

/** A size or count printed after a name: "1KG", "1.5 kg", "250G", "1L", "330ML", "X12", "12X". QTY shows it. */
const PRINTED_SIZE = /\s+(?:\d+(?:[.,]\d+)?\s?(?:kg|g|gr|mg|l|lt|ml|cl)|x\s?\d+|\d+\s?x|\d+\s?(?:pcs|pc))(?=\s|$)/gi;

/**
 * An item's name in a table (D053): the text printed on the receipt ("RIM SPARKLING WATER" -> "Rim sparkling
 * water"), in sentence case, without the size QTY already shows ("LABNEH 1KG" -> "Labneh"). Not the reader's
 * clean name ("water"): that one is generic on purpose, for the assistant's questions across shops and brands.
 */
export function itemName(line: ReceiptLine): string {
  const printed = line.description.replace(PRINTED_SIZE, '').replace(/\s+/g, ' ').trim();
  const name = printed || line.description.trim() || line.normalizedName?.trim() || '';
  if (!name) return 'Item';
  // Sentence case only for text printed in capitals; Arabic and mixed-case names stay as printed.
  const shouted = name === name.toUpperCase() && /[A-Z]/.test(name);
  const cased = shouted ? name.toLowerCase() : name;
  return cased.charAt(0).toUpperCase() + cased.slice(1);
}

/** QTY (screen 05): the size when known ("1 kg", "250 g", "1 L"), else the count ("1", "12"). */
export function quantityLabel(line: ReceiptLine): string {
  if (line.sizeAmount !== null && line.sizeUnit) {
    const unit = line.sizeUnit.toLowerCase() === 'l' ? 'L' : line.sizeUnit.toLowerCase();
    const size = `${plain(number(line.sizeAmount))} ${unit}`;
    return number(line.quantity) > 1 ? `${plain(number(line.quantity))} × ${size}` : size;
  }
  return plain(number(line.quantity) || 1);
}

/** Every item's category, as the spending counts it: its own, else the receipt's. */
export function lineCategory(line: ReceiptLine, receipt: Receipt): number | null {
  return line.categoryId ?? receipt.categoryId;
}

/** The receipt as the backend saves it, with nothing changed. */
export function payloadOf(receipt: Receipt): ConfirmPayload {
  return {
    shopName: receipt.shopName,
    receiptDate: receipt.receiptDate as string,
    currency: receipt.currency as 'USD' | 'LBP',
    total: receipt.total as string,
    categoryId: receipt.categoryId,
    lines: receipt.lines,
  };
}

/** Change category: the receipt's category, and every item follows it again (D050). */
export function withCategory(receipt: Receipt, categoryId: number | null): ConfirmPayload {
  return { ...payloadOf(receipt), categoryId, lines: receipt.lines.map((line) => ({ ...line, categoryId: null })) };
}

/**
 * Split items: each item's chosen category. An item in the receipt's own category is saved as following it, so a
 * later Change category moves it too.
 */
export function withItemCategories(receipt: Receipt, chosen: readonly (number | null)[]): ConfirmPayload {
  return {
    ...payloadOf(receipt),
    lines: receipt.lines.map((line, index) => {
      const category = chosen[index] ?? null;
      return { ...line, categoryId: category === receipt.categoryId ? null : category };
    }),
  };
}

/** How many of the receipt's items have a category other than the receipt's. */
export function splitCount(receipt: Receipt): number {
  return receipt.lines.filter((line) => line.categoryId !== null && line.categoryId !== receipt.categoryId).length;
}

/** A category's name, or null. */
export function categoryName(categories: readonly Category[], id: number | null): string | null {
  return id === null ? null : (categories.find((category) => category.id === id)?.name ?? null);
}
