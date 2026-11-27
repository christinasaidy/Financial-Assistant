import { ScanError, ScanService } from '@/features/scan/application/scanService';
import { ApiScanUploader, UPLOAD_TIMEOUT_MS } from '@/features/scan/data/apiScanUploader';
import { addsUp, checkDraft, checksFor, draftFrom, filedNumbers, parseDate, payloadFrom, readingState } from '@/features/scan/domain';
import { readingRows, saveLabel } from '@/features/scan/ui/scanText';
import { createHttpClient } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';
import { receipt } from '../receipts/fakes';
import { FakeScanRepository, readSpinneys } from './fakes';

const NOV_26 = new Date(2026, 10, 26, 10);
const instant = async () => undefined;

describe('reading a receipt', () => {
  it('knows when it has been read', () => {
    expect(readingState('uploaded')).toBe('reading');
    expect(readingState('processing')).toBe('reading');
    expect(readingState('needs_review')).toBe('ready');
    expect(readingState('failed')).toBe('failed');
  });

  it('lists what was found for the checklist (screen 10)', () => {
    expect(readingRows(readSpinneys())).toEqual([
      { label: 'Store', value: 'Spinneys Achrafieh', mono: false },
      { label: 'Date', value: '18 Nov 2026', mono: true },
      { label: 'Items', value: '9 found', mono: true },
      { label: 'Total', value: '$38.40', mono: true },
    ]);
  });
});

describe('Review’s checks (D051)', () => {
  it('marks CHECK THIS from the backend’s flags: unnamed items, a missing store, date or total', () => {
    expect(checksFor(readSpinneys())).toEqual({ store: false, date: false, total: false, lines: [3] });
    const bare = readSpinneys({ shopName: null, receiptDate: null, total: null, flags: ['missing_vendor', 'missing_date', 'missing_total'] });
    expect(checksFor(bare)).toMatchObject({ store: true, date: true, total: true });
    expect(checksFor(readSpinneys({ flags: ['future_date'] })).date).toBe(true);
  });

  it('reads dates as on Lebanese receipts, and refuses impossible ones', () => {
    expect(parseDate('18/11/2026')).toBe('2026-11-18');
    expect(parseDate('8-1-26')).toBe('2026-01-08');
    expect(parseDate('31/02/2026')).toBeNull();
    expect(parseDate('2026-11-18')).toBeNull();
  });

  it('starts from what was read, today when no date was, dollars by default', () => {
    expect(draftFrom(readSpinneys(), NOV_26)).toMatchObject({ shopName: 'Spinneys Achrafieh', date: '18/11/2026', currency: 'USD', total: '38.40', categoryId: 1 });
    expect(draftFrom(readSpinneys({ receiptDate: null, currency: null, shopName: null }), NOV_26)).toMatchObject({ shopName: '', date: '26/11/2026', currency: 'USD' });
  });

  it('says whether the items add up to the total', () => {
    const draft = draftFrom(readSpinneys(), NOV_26);
    expect(addsUp(draft)).toBe(true);
    expect(addsUp({ ...draft, total: '40.00' })).toBe(false);
    expect(addsUp({ ...draft, lines: [] })).toBeNull();
  });

  it('asks for a store, a real date, a total and a category before saving', () => {
    const draft = draftFrom(readSpinneys(), NOV_26);
    expect(checkDraft(draft)).toEqual({});
    expect(checkDraft({ ...draft, shopName: ' ', date: '40/11/2026', total: '', categoryId: null })).toEqual({
      store: 'Enter the store.',
      date: 'Enter the date like 18/11/2026.',
      total: 'Enter the total.',
      category: 'Choose a category.',
    });
    expect(checkDraft({ ...draft, currency: 'LBP', total: '450000.5' }).total).toBe('Pounds have no decimals.');
    expect(payloadFrom({ ...draft, shopName: ' Spinneys ', total: '1,234.50' })).toMatchObject({ shopName: 'Spinneys', receiptDate: '2026-11-18', total: '1234.50' });
  });

  it('names the invoice the receipt is saved to', () => {
    expect(saveLabel('2026-11-18', NOV_26)).toBe('Save to November invoice');
    expect(saveLabel(null, NOV_26)).toBe('Save to November invoice');
  });
});

describe('the Filed numbers (screen 12)', () => {
  it('works out the budget and total before the receipt from after it: 148.00 -> 186.40, 409.40 -> 447.80', () => {
    const numbers = filedNumbers(readSpinneys(), { name: 'Groceries', currency: 'USD', limit: '250.00', spent: '186.40' }, 447.8, 89500);
    expect(numbers).toEqual({ added: 38.4, budget: { limit: '250.00', currency: 'USD', before: 148, after: 186.4 }, totalBefore: 409.4, totalAfter: 447.8 });
  });

  it('converts a pound receipt for a dollar budget and the dollar total, at the receipt’s rate', () => {
    const zaatar = receipt(30, 'Zaatar w Zeit', '2026-11-17', '450000.00', 'LBP', 2);
    const numbers = filedNumbers(zaatar, { name: 'Eating out', currency: 'USD', limit: '80.00', spent: '71.50' }, 447.8, 89500);
    expect(numbers.added).toBe(5.03);
    expect(numbers.budget?.before).toBe(66.47);
    expect(numbers.totalBefore).toBe(442.77);
  });
});

describe('ScanService', () => {
  it('sends the photo and asks until it has been read', async () => {
    const repository = new FakeScanRepository();
    repository.readAfter = 3;
    const service = new ScanService(repository);
    const id = await service.upload({ uri: 'file:///receipt.jpg', mimeType: 'image/jpeg' });
    const read = await service.waitUntilRead(id, { sleep: instant });
    expect(read.status).toBe('needs_review');
    expect(repository.calls.filter((call) => call.startsWith('receipt'))).toHaveLength(3);
  });

  it('stops when it could not be read, or takes too long', async () => {
    const failing = new FakeScanRepository();
    failing.failReading = true;
    await expect(new ScanService(failing).waitUntilRead(100, { sleep: instant })).rejects.toEqual(new ScanError('failed', 'Fatourati could not read this photo.'));
    const slow = new FakeScanRepository();
    slow.readAfter = 1000;
    await expect(new ScanService(slow).waitUntilRead(100, { sleep: instant, intervalMs: 1000, timeoutMs: 5000 })).rejects.toMatchObject({ code: 'timeout' });
  });

  it('gives Review the receipt, the categories and the invoice it goes into (Nº 0003 from September)', async () => {
    const review = await new ScanService(new FakeScanRepository()).loadReview(100, NOV_26);
    expect(review.invoiceNumber).toBe(3);
    expect(review.categories.map((category) => category.name)).toContain('Groceries');
  });

  it('saves, then shows what changed', async () => {
    const repository = new FakeScanRepository();
    const filed = await new ScanService(repository).save(100, draftFrom(readSpinneys(), NOV_26));
    expect(repository.saved).toMatchObject({ shopName: 'Spinneys Achrafieh', receiptDate: '2026-11-18', categoryId: 1 });
    expect(filed).toMatchObject({ category: 'Groceries', added: 38.4, totalBefore: 409.4, totalAfter: 447.8, invoiceNumber: 3 });
    expect(filed.budget).toMatchObject({ before: 148, after: 186.4 });
  });

  it('deletes an unsaved scan quietly, even when that fails', async () => {
    const repository = new FakeScanRepository();
    await new ScanService(repository).discard(100);
    expect(repository.calls).toContain('remove 100');
    repository.offline = true;
    await expect(new ScanService(repository).discard(100)).resolves.toBeUndefined();
  });
});

describe('ApiScanUploader', () => {
  it('posts the photo as multipart form data, with a longer time limit', async () => {
    const { fetchFn, requests } = fetchMock({ status: 202, body: { id: 55, status: 'uploaded' } });
    const http = createHttpClient({ baseUrl: 'http://192.168.1.23:8000', getToken: () => 'jwt', onUnauthorized: jest.fn(), fetchFn });
    await expect(new ApiScanUploader(http).upload({ uri: 'file:///r.png', mimeType: 'image/png' })).resolves.toBe(55);
    expect(requests[0]).toMatchObject({ url: 'http://192.168.1.23:8000/receipts', method: 'POST' });
    expect(requests[0]?.body).toBeInstanceOf(FormData);
    expect(requests[0]?.headers['Content-Type']).toBeUndefined();
    expect(UPLOAD_TIMEOUT_MS).toBeGreaterThan(15_000);
  });

  it('passes on the backend’s reason for refusing a photo', async () => {
    const { fetchFn } = fetchMock({ status: 415, body: { detail: 'Only JPEG, PNG and WebP photos can be read' } });
    const http = createHttpClient({ baseUrl: 'http://192.168.1.23:8000', getToken: () => 'jwt', onUnauthorized: jest.fn(), fetchFn });
    await expect(new ApiScanUploader(http).upload({ uri: 'file:///r.heic', mimeType: 'image/heic' })).rejects.toMatchObject({
      code: 'refused',
      message: 'Only JPEG, PNG and WebP photos can be read',
    });
  });
});
