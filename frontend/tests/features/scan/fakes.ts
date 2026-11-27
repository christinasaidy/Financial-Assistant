import type { ScanRepository } from '@/features/scan/application/interfaces';
import type { BudgetLine, ConfirmPayload, Photo, Receipt } from '@/features/scan/domain';
import { ReceiptsError } from '@/features/receipts/domain';

import { categories, line, receipt } from '../receipts/fakes';

/** What the backend read from the design's Spinneys photo (screen 11): the olive oil's name was not read. */
export function readSpinneys(extra: Partial<Receipt> = {}): Receipt {
  return receipt(
    100,
    'Spinneys Achrafieh',
    '2026-11-18',
    '38.40',
    'USD',
    1,
    [
      line('LABNEH 1KG', '6.20', { normalizedName: 'labneh', sizeAmount: '1', sizeUnit: 'kg' }),
      line('KHUBZ ARABI', '1.10', { normalizedName: 'khubz arabi' }),
      line('TOMATOES 1.5KG', '2.85', { normalizedName: 'tomatoes', sizeAmount: '1.5', sizeUnit: 'kg' }),
      line('OLIVE OIL 1L', '14.50', { normalizedName: null, sizeAmount: '1', sizeUnit: 'L' }),
      line('CUCUMBERS 1KG', '1.90', { normalizedName: 'cucumbers' }),
      line('HALLOUMI 250G', '5.40', { normalizedName: 'halloumi' }),
      line('EGGS X12', '3.95', { normalizedName: 'eggs' }),
      line('LEMONS 1KG', '1.60', { normalizedName: 'lemons' }),
      line('MINT BUNCH', '0.90', { normalizedName: 'mint' }),
    ],
    { status: 'needs_review', flags: ['line_without_name'], ...extra },
  );
}

/** An in-memory backend for the scan flow. The photo is "read" after `readAfter` checks. */
export class FakeScanRepository implements ScanRepository {
  read: Receipt = readSpinneys();
  readAfter = 2;
  failReading = false;
  offline = false;
  checks = 0;
  calls: string[] = [];
  saved: ConfirmPayload | null = null;
  /** After saving: Groceries' budget and the month's total in dollars, as the backend counts them. */
  budget: BudgetLine | null = { name: 'Groceries', currency: 'USD', limit: '250.00', spent: '186.40' };
  monthTotalUsd = '447.80';
  /** Older confirmed receipts, for the invoice number. */
  older: Receipt[] = [receipt(1, 'Malik’s', '2026-09-03', '14.00', 'USD', null)];

  async upload(photo: Photo) {
    this.record(`upload ${photo.mimeType}`);
    return this.read.id;
  }

  async remove(id: number) {
    this.record(`remove ${id}`);
  }

  async receipt(id: number) {
    this.record(`receipt ${id}`);
    if (this.saved) return { ...this.read, status: 'confirmed', categoryId: this.saved.categoryId, total: this.saved.total, currency: this.saved.currency, receiptDate: this.saved.receiptDate };
    this.checks += 1;
    if (this.failReading) return { ...this.read, status: 'failed' };
    return this.checks >= this.readAfter ? this.read : { ...this.read, status: 'processing' };
  }

  async receipts() {
    this.record('receipts');
    return [...this.older, ...(this.saved ? [{ ...this.read, status: 'confirmed' }] : [])];
  }

  async categories() {
    this.record('categories');
    return categories;
  }

  async confirm(id: number, payload: ConfirmPayload) {
    this.record(`confirm ${id}`);
    this.saved = payload;
    return { ...this.read, status: 'confirmed', shopName: payload.shopName, receiptDate: payload.receiptDate, currency: payload.currency, total: payload.total, categoryId: payload.categoryId };
  }

  async budgets(month: string) {
    this.record(`budgets ${month}`);
    return new Map(this.budget ? [[1, this.budget]] : []);
  }

  async monthTotal(month: string) {
    this.record(`total ${month}`);
    return { total: this.monthTotalUsd, lbpPerUsd: '89500.00' };
  }

  private record(call: string) {
    this.calls.push(call);
    if (this.offline) throw new ReceiptsError('network', 'Could not reach the server');
  }
}
