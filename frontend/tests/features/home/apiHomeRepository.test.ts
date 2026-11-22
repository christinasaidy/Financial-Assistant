import {
  ApiHomeRepository,
  toBudgetUse,
  toMonthSpending,
  toReceiptListing,
  type BudgetStatusDto,
  type MonthlySummaryDto,
  type ReceiptSummaryDto,
} from '@/features/home/data/apiHomeRepository';
import { HomeError } from '@/features/home/domain/errors';
import { createHttpClient } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';

function repositoryWith(...replies: Parameters<typeof fetchMock>) {
  const { fetchFn, requests } = fetchMock(...replies);
  const onUnauthorized = jest.fn();
  const http = createHttpClient({
    baseUrl: 'http://192.168.1.23:8000',
    getToken: () => 'jwt',
    onUnauthorized,
    fetchFn,
  });
  return { repository: new ApiHomeRepository(http), requests, onUnauthorized };
}

function currencySummary(currency: string, total: string, receiptCount: number) {
  return { currency, total, categories: [], adjustments: '0.00', receipt_count: receiptCount };
}

/** GET /spending/summary?month=2026-11&currency=USD, as backend/app/api/spending/schemas.py sends it. */
const summaryDto: MonthlySummaryDto = {
  month: '2026-11-01',
  combined: {
    currency: 'USD',
    total: '447.80',
    categories: [{ category_id: 1, name: 'Groceries', amount: '186.40' }],
    adjustments: '1.20',
    receipt_count: 14,
  },
  by_currency: [currencySummary('USD', '412.60', 11), currencySummary('LBP', '3150000.00', 3)],
  awaiting_review: 2,
  converted_at_current_rate: 0,
  current_lbp_per_usd: '89500.00',
};

const budgetDto: BudgetStatusDto = {
  category_id: 4,
  category_name: 'Eating out',
  month: '2026-11-01',
  set_in: '2026-10-01',
  currency: 'USD',
  limit_amount: '80.00',
  spent: '71.50',
  remaining: '8.50',
  percent_used: '89.4',
  state: 'near',
  pace: { projected: '95.33', low_confidence: false, projected_over: true },
};

const receiptDto: ReceiptSummaryDto = {
  id: 31,
  status: 'confirmed',
  vendor_name: 'Spinneys Achrafieh',
  receipt_date: '2026-11-18',
  currency: 'USD',
  total: '38.40',
  primary_category_id: 1,
  lbp_per_usd: '89500.00',
  has_file: true,
  created_at: '2026-11-18T16:42:10.123456Z',
};

describe('DTO mapping', () => {
  it('maps the month summary, keeping amounts as exact strings', () => {
    expect(toMonthSpending(summaryDto)).toEqual({
      month: '2026-11-01',
      total: '447.80',
      receiptCount: 14,
      usdPart: '412.60',
      lbpPart: '3150000.00',
      lbpPerUsd: '89500.00',
      awaitingReview: 2,
    });
  });

  it('leaves out a currency the month has no receipts in', () => {
    const dollarsOnly = { ...summaryDto, by_currency: [currencySummary('USD', '412.60', 11)] };
    expect(toMonthSpending(dollarsOnly)).toMatchObject({ usdPart: '412.60', lbpPart: null });
    const empty = { ...summaryDto, combined: currencySummary('USD', '0.00', 0), by_currency: [] };
    expect(toMonthSpending(empty)).toMatchObject({ total: '0.00', receiptCount: 0, usdPart: null, lbpPart: null });
  });

  it('maps a budget and refuses a state or currency it does not know', () => {
    expect(toBudgetUse(budgetDto)).toEqual({
      categoryId: 4,
      name: 'Eating out',
      currency: 'USD',
      limit: '80.00',
      spent: '71.50',
      percentUsed: '89.4',
      state: 'near',
    });
    expect(toBudgetUse({ ...budgetDto, state: 'limit_reached' }).state).toBe('limit_reached');
    expect(() => toBudgetUse({ ...budgetDto, state: 'over' })).toThrow(HomeError);
    expect(() => toBudgetUse({ ...budgetDto, currency: 'EUR' })).toThrow(HomeError);
  });

  it('maps a receipt summary, with no shop name for a blank one', () => {
    expect(toReceiptListing(receiptDto)).toEqual({
      id: 31,
      status: 'confirmed',
      shopName: 'Spinneys Achrafieh',
      receiptDate: '2026-11-18',
      currency: 'USD',
      total: '38.40',
      createdAt: '2026-11-18T16:42:10.123456Z',
    });
    const blank = {
      ...receiptDto,
      status: 'processing',
      vendor_name: '  ',
      receipt_date: null,
      currency: null,
      total: null,
    };
    expect(toReceiptListing(blank)).toMatchObject({ shopName: null, receiptDate: null, currency: null, total: null });
  });
});

describe('ApiHomeRepository', () => {
  it('asks for the month summary in dollars, with the session token', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: summaryDto });
    await expect(repository.monthSpending('2026-11')).resolves.toMatchObject({ total: '447.80' });
    expect(requests[0]).toMatchObject({
      url: 'http://192.168.1.23:8000/spending/summary?month=2026-11&currency=USD',
      method: 'GET',
      headers: { Authorization: 'Bearer jwt' },
    });
  });

  it('asks for the month’s budgets', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: [budgetDto] });
    await expect(repository.budgets('2026-11')).resolves.toHaveLength(1);
    expect(requests[0]?.url).toBe('http://192.168.1.23:8000/budgets?month=2026-11');
  });

  it('lists the receipts and counts a receipt’s lines', async () => {
    const { repository, requests } = repositoryWith(
      { status: 200, body: [receiptDto] },
      { status: 200, body: { ...receiptDto, lines: [{}, {}, {}], lines_total: '38.40', flags: [] } },
    );
    await expect(repository.receipts()).resolves.toEqual([toReceiptListing(receiptDto)]);
    await expect(repository.itemCount(31)).resolves.toBe(3);
    expect(requests.map((request) => request.url)).toEqual([
      'http://192.168.1.23:8000/receipts',
      'http://192.168.1.23:8000/receipts/31',
    ]);
  });

  it('turns an unreachable server into a network error', async () => {
    const { repository } = repositoryWith({ networkError: 'Network request failed' });
    await expect(repository.monthSpending('2026-11')).rejects.toMatchObject({ name: 'HomeError', code: 'network' });
  });

  it('turns a server error or an unreadable answer into an unexpected error', async () => {
    const { repository } = repositoryWith(
      { status: 500, body: { detail: 'Internal Server Error' } },
      { status: 200, body: { detail: 'not a list' } },
    );
    await expect(repository.budgets('2026-11')).rejects.toMatchObject({
      code: 'unexpected',
      message: 'Internal Server Error',
    });
    await expect(repository.budgets('2026-11')).rejects.toMatchObject({ code: 'unexpected' });
  });

  it('lets a rejected token end the session', async () => {
    const { repository, onUnauthorized } = repositoryWith({ status: 401, body: { detail: 'Invalid token' } });
    await expect(repository.receipts()).rejects.toBeInstanceOf(HomeError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
