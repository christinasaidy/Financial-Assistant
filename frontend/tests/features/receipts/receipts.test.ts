import { ReceiptsService } from '@/features/receipts/application/receiptsService';
import { ApiReceiptsRepository, toConfirmBody } from '@/features/receipts/data/apiReceiptsRepository';
import {
  filterReceipts,
  filtersFor,
  groupReceipts,
  itemName,
  quantityLabel,
  withCategory,
  withItemCategories,
  type ListedReceipt,
} from '@/features/receipts/domain';
import { listApprox, listSubline, receiptWhen, totalOrShown } from '@/features/receipts/ui/receiptsText';
import { createHttpClient } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';
import { FakeReceiptsRepository, line, spinneys } from './fakes';

const NOV_26 = new Date(2026, 10, 26, 10);

function listed(id: number, receiptDate: string, categoryId: number | null, category: string | null, shopName = 'Shop'): ListedReceipt {
  return { id, shopName, receiptDate, currency: 'USD', total: '1.00', categoryId, category, itemCount: 1, lbpPerUsd: '89500' };
}

describe('the Receipts roll (design/screens/13-receipts.png)', () => {
  it('groups this week (since Monday) apart from earlier in the month', () => {
    const groups = groupReceipts([listed(1, '2026-11-25', 1, 'Groceries'), listed(2, '2026-11-23', 1, 'Groceries'), listed(3, '2026-11-18', 2, 'Eating out')], 'November', NOV_26);
    expect(groups.map((group) => [group.title, group.receipts.map((item) => item.id)])).toEqual([
      ['This week', [1, 2]],
      ['Earlier in November', [3]],
    ]);
    expect(groupReceipts([listed(4, '2026-10-15', 3, 'Transport')], 'October', NOV_26).map((group) => group.title)).toEqual(['In October']);
  });

  it('offers All, the month’s categories (most receipts first) and Other', () => {
    const receipts = [listed(1, '2026-11-25', 2, 'Eating out'), listed(2, '2026-11-24', 1, 'Groceries'), listed(3, '2026-11-23', 1, 'Groceries'), listed(4, '2026-11-22', null, null)];
    expect(filtersFor(receipts).map((filter) => (filter.key === 'category' ? filter.name : filter.key))).toEqual(['all', 'Groceries', 'Eating out', 'other']);
    expect(filterReceipts(receipts, { key: 'category', id: 1, name: 'Groceries' }).map((item) => item.id)).toEqual([2, 3]);
    expect(filterReceipts(receipts, { key: 'other' }).map((item) => item.id)).toEqual([4]);
    expect(filterReceipts([listed(5, '2026-11-20', 1, 'Groceries', 'Spinneys Achrafieh'), listed(6, '2026-11-20', 2, 'Eating out', 'Barbar')], { key: 'all' }, 'spin').map((item) => item.id)).toEqual([5]);
  });

  it('writes the totals, the rows and the receipt’s corner like the design', () => {
    expect(totalOrShown('447.80', null)).toBe('Total $447.80');
    expect(totalOrShown('447.80', 2)).toBe('2 receipts shown');
    expect(listSubline({ category: 'Groceries', itemCount: 9 })).toBe('Groceries · 9 items');
    expect(listApprox({ total: '450000', currency: 'LBP', lbpPerUsd: '89500' })).toBe('≈ $5.03');
    const local = { ...spinneys, createdAt: new Date(2026, 10, 18, 18, 42).toISOString() };
    expect(receiptWhen(local)).toBe('18 Nov · 18:42');
  });
});

describe('a receipt’s items', () => {
  it('names them cleanly and shows sizes as QTY', () => {
    // The printed name, not the generic clean name the assistant uses (D053).
    expect(itemName(line('RIM SPARKLING WATER', '0.60', { normalizedName: 'water' }))).toBe('Rim sparkling water');
    expect(itemName(line('TEREA', '5.00', { normalizedName: 'tobacco' }))).toBe('Terea');
    expect(itemName(line('LABNEH 1KG', '6.20', { normalizedName: 'labneh' }))).toBe('Labneh');
    expect(itemName(line('TOMATOES 1.5KG', '2.85'))).toBe('Tomatoes');
    expect(itemName(line('EGGS X12', '3.95'))).toBe('Eggs');
    expect(itemName(line('PEPSI 330ML', '0.80'))).toBe('Pepsi');
    expect(itemName(line('MINT BUNCH', '0.90'))).toBe('Mint bunch');
    expect(itemName(line('Pain au chocolat', '1.20'))).toBe('Pain au chocolat');
    expect(itemName(line('خبز عربي', '1.10', { normalizedName: 'bread' }))).toBe('خبز عربي');
    expect(itemName(line('7UP', '0.50'))).toBe('7up');
    expect(itemName(line('', '1.00', { normalizedName: 'bread' }))).toBe('Bread');
    expect(quantityLabel(line('x', '1', { sizeAmount: '1.500', sizeUnit: 'kg' }))).toBe('1.5 kg');
    expect(quantityLabel(line('x', '1', { sizeAmount: '1', sizeUnit: 'l' }))).toBe('1 L');
    expect(quantityLabel(line('x', '1', { quantity: '12.000' }))).toBe('12');
    expect(quantityLabel(line('x', '1', { quantity: '2', sizeAmount: '250', sizeUnit: 'g' }))).toBe('2 × 250 g');
  });

  it('changes the category with every item following it, keeping every other value (D050)', () => {
    const split = { ...spinneys, lines: spinneys.lines.map((item, index) => (index === 0 ? { ...item, categoryId: 4 } : item)) };
    const payload = withCategory(split, 2);
    expect(payload.categoryId).toBe(2);
    expect(payload.lines.map((item) => item.categoryId)).toEqual([null, null, null, null, null]);
    expect(payload.lines[0]?.normalizedName).toBe('labneh');
    expect(payload.total).toBe('38.40');
  });

  it('splits items, saving those in the receipt’s own category as following it', () => {
    const payload = withItemCategories(spinneys, [4, 1, 1, 2, 1]);
    expect(payload.categoryId).toBe(1);
    expect(payload.lines.map((item) => item.categoryId)).toEqual([4, null, null, 2, null]);
  });

  it('sends every field to the backend, and keeps the saved rate by leaving it out', () => {
    const body = toConfirmBody(withCategory(spinneys, 2));
    expect(body).toMatchObject({ vendor_name: 'Spinneys Achrafieh', receipt_date: '2026-11-18', currency: 'USD', total: '38.40', primary_category_id: 2 });
    expect(body.lines[0]).toEqual({
      description: 'LABNEH 1KG',
      line_total: '6.20',
      quantity: '1',
      unit_price: null,
      normalized_name: 'labneh',
      size_amount: '1',
      size_unit: 'kg',
      category_id: null,
      brand: null,
    });
    expect(body).not.toHaveProperty('lbp_per_usd');
  });
});

describe('ReceiptsService', () => {
  it('loads a month: confirmed receipts only, newest first, with category names and item counts', async () => {
    const month = await new ReceiptsService(new FakeReceiptsRepository()).loadMonth(new Date(2026, 10, 1));
    expect(month.total).toBe('447.80');
    expect(month.receipts.map((item) => [item.shopName, item.category, item.itemCount])).toEqual([
      ['Barbar Hamra', 'Eating out', 1],
      ['Bolt', 'Transport', 0],
      ['Kiosk', null, 0],
      ['Spinneys Achrafieh', 'Groceries', 5],
      ['Zaatar w Zeit', 'Eating out', 2],
    ]);
    expect(month.hasOlder).toBe(true);
    const october = await new ReceiptsService(new FakeReceiptsRepository()).loadMonth(new Date(2026, 9, 1));
    expect(october.hasOlder).toBe(false);
  });

  it('loads a receipt with its category’s budget for that month', async () => {
    const page = await new ReceiptsService(new FakeReceiptsRepository()).loadReceipt(31);
    expect(page.receipt.shopName).toBe('Spinneys Achrafieh');
    expect(page.budget).toEqual({ name: 'Groceries', currency: 'USD', limit: '250.00', spent: '186.40' });
    const none = await new ReceiptsService(new FakeReceiptsRepository()).loadReceipt(41);
    expect(none.budget).toBeNull();
  });

  it('saves a new category through confirm', async () => {
    const repository = new FakeReceiptsRepository();
    await new ReceiptsService(repository).changeCategory(spinneys, 2);
    expect(repository.saved[0]?.payload.categoryId).toBe(2);
  });
});

describe('ApiReceiptsRepository', () => {
  it('posts the corrected receipt to confirm', async () => {
    const { fetchFn, requests } = fetchMock({
      status: 200,
      body: {
        id: 31,
        status: 'confirmed',
        vendor_name: 'Spinneys Achrafieh',
        receipt_date: '2026-11-18',
        currency: 'USD',
        total: '38.40',
        primary_category_id: 2,
        lbp_per_usd: null,
        has_file: true,
        created_at: '2026-11-18T16:42:00Z',
        lines: [],
        lines_total: '0',
        flags: [],
      },
    });
    const http = createHttpClient({ baseUrl: 'http://192.168.1.23:8000', getToken: () => 'jwt', onUnauthorized: jest.fn(), fetchFn });
    const saved = await new ApiReceiptsRepository(http).confirm(31, withCategory(spinneys, 2));
    expect(requests[0]).toMatchObject({ url: 'http://192.168.1.23:8000/receipts/31/confirm', method: 'POST' });
    expect(saved.categoryId).toBe(2);
  });
});
