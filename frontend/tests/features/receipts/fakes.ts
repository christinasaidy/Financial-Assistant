import type { ReceiptsRepository } from '@/features/receipts/application/interfaces';
import { ReceiptsError, type BudgetLine, type Category, type ConfirmPayload, type Receipt, type ReceiptLine } from '@/features/receipts/domain';

export function line(description: string, lineTotal: string, extra: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: null,
    description,
    lineTotal,
    quantity: '1',
    unitPrice: null,
    normalizedName: null,
    sizeAmount: null,
    sizeUnit: null,
    categoryId: null,
    brand: null,
    ...extra,
  };
}

export function receipt(id: number, shopName: string, receiptDate: string, total: string, currency: 'USD' | 'LBP', categoryId: number | null, lines: ReceiptLine[] = [], extra: Partial<Receipt> = {}): Receipt {
  return {
    id,
    status: 'confirmed',
    shopName,
    receiptDate,
    currency,
    total,
    categoryId,
    lbpPerUsd: currency === 'LBP' ? '89500.00' : null,
    createdAt: `${receiptDate}T16:42:00Z`,
    lines,
    flags: [],
    ...extra,
  };
}

export const categories: Category[] = [
  { id: 1, name: 'Groceries' },
  { id: 2, name: 'Eating out' },
  { id: 3, name: 'Transport' },
  { id: 4, name: 'Pharmacy' },
];

/** The design's Spinneys receipt (screen 05). */
export const spinneys = receipt(31, 'Spinneys Achrafieh', '2026-11-18', '38.40', 'USD', 1, [
  line('LABNEH 1KG', '6.20', { id: 1, normalizedName: 'labneh', sizeAmount: '1', sizeUnit: 'kg' }),
  line('KHUBZ ARABI', '1.10', { id: 2, normalizedName: 'khubz arabi' }),
  line('TOMATOES 1.5KG', '2.85', { id: 3, normalizedName: 'tomatoes', sizeAmount: '1.5', sizeUnit: 'kg' }),
  line('OLIVE OIL 1L', '14.50', { id: 4, normalizedName: 'olive oil', sizeAmount: '1', sizeUnit: 'L' }),
  line('EGGS X12', '3.95', { id: 5, normalizedName: 'eggs', quantity: '12' }),
]);
export const zaatar = receipt(30, 'Zaatar w Zeit', '2026-11-17', '450000.00', 'LBP', 2, [line('Manakish', '300000'), line('Ayran', '150000')]);
export const barbar = receipt(40, 'Barbar Hamra', '2026-11-25', '620000.00', 'LBP', 2, [line('Shawarma', '620000')]);
export const bolt = receipt(41, 'Bolt', '2026-11-24', '4.50', 'USD', 3);
export const unsorted = receipt(42, 'Kiosk', '2026-11-23', '2.00', 'USD', null);
export const october = receipt(20, 'Medco station', '2026-10-15', '30.00', 'USD', 3);
export const processing = receipt(43, 'Still reading', '2026-11-25', '1.00', 'USD', 1, [], { status: 'processing' });

/** An in-memory receipts backend. */
export class FakeReceiptsRepository implements ReceiptsRepository {
  byId = new Map<number, Receipt>([spinneys, zaatar, barbar, bolt, unsorted, october, processing].map((item) => [item.id, structuredClone(item)]));
  categoryList = categories;
  budgetsByMonth = new Map<string, Map<number, BudgetLine>>([
    ['2026-11', new Map([[1, { name: 'Groceries', currency: 'USD', limit: '250.00', spent: '186.40' }]])],
  ]);
  offline = false;
  calls: string[] = [];
  saved: { id: number; payload: ConfirmPayload }[] = [];

  async receipts() {
    this.record('receipts');
    return [...this.byId.values()].map(({ lines: _lines, flags: _flags, ...summary }) => summary);
  }

  async receipt(id: number) {
    this.record(`receipt ${id}`);
    const found = this.byId.get(id);
    if (!found) throw new ReceiptsError('refused', 'Receipt not found');
    return structuredClone(found);
  }

  async categories() {
    this.record('categories');
    return this.categoryList;
  }

  async monthTotal(month: string) {
    this.record(`total ${month}`);
    return { total: month === '2026-11' ? '447.80' : '30.00', lbpPerUsd: '89500.00' };
  }

  async budgets(month: string) {
    this.record(`budgets ${month}`);
    return this.budgetsByMonth.get(month) ?? new Map();
  }

  async confirm(id: number, payload: ConfirmPayload) {
    this.record(`confirm ${id}`);
    this.saved.push({ id, payload });
    const found = this.byId.get(id) as Receipt;
    const updated = { ...found, categoryId: payload.categoryId, lines: payload.lines };
    this.byId.set(id, updated);
    return structuredClone(updated);
  }

  private record(call: string) {
    this.calls.push(call);
    if (this.offline) throw new ReceiptsError('network', 'Could not reach the server');
  }
}
