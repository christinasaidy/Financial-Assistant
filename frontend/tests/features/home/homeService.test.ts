import { HomeService } from '@/features/home/application/homeService';
import { HomeError } from '@/features/home/domain/errors';

import {
  abouRami,
  awaiting,
  eatingOut,
  emptyMonth,
  FakeHomeRepository,
  fuel,
  groceries,
  november,
  septemberReceipt,
  spinneys,
  transport,
  zaatar,
} from './fakes';

const NOVEMBER_18 = new Date(2026, 10, 18, 12, 0);

describe('HomeService.loadOverview', () => {
  it('asks for the given month and puts the overview together', async () => {
    const repository = new FakeHomeRepository();
    repository.budgetList = [fuel, groceries, transport, eatingOut];
    repository.receiptList = [awaiting, spinneys, zaatar, abouRami, septemberReceipt];

    const overview = await new HomeService(repository).loadOverview(NOVEMBER_18);

    expect(repository.calls.slice(0, 4)).toEqual(['summary 2026-11', 'budgets 2026-11', 'receipts', 'categories']);
    expect(overview.spending).toEqual(november);
    expect(overview.budgets.map((budget) => budget.name)).toEqual(['Transport', 'Eating out', 'Groceries', 'Fuel']);
    // Fuel has no spending this month, so Everything else stays the design's $126.90 and the rows add up to $447.80.
    expect(overview.everythingElse).toBe('126.90');
    expect(overview.invoiceNumber).toBe(3);
    expect(overview.olderMonths).toEqual(['2026-09-01', '2026-10-01']);
    expect(overview.recent).toEqual([
      {
        id: 31,
        shopName: 'Spinneys Achrafieh',
        receiptDate: '2026-11-18',
        createdAt: spinneys.createdAt,
        currency: 'USD',
        total: '38.40',
        itemCount: 9,
        category: 'Groceries',
        lbpPerUsd: november.lbpPerUsd,
      },
      {
        id: 30,
        shopName: 'Zaatar w Zeit',
        receiptDate: '2026-11-17',
        createdAt: zaatar.createdAt,
        currency: 'LBP',
        total: '450000.00',
        itemCount: 2,
        category: 'Eating out',
        lbpPerUsd: '89500.00',
      },
      {
        id: 29,
        shopName: 'Abou Rami',
        receiptDate: '2026-11-12',
        createdAt: abouRami.createdAt,
        currency: 'USD',
        total: '6.60',
        itemCount: 1,
        category: null,
        lbpPerUsd: november.lbpPerUsd,
      },
    ]);
  });

  it('only opens the receipts it shows, to count their items', async () => {
    const repository = new FakeHomeRepository();
    repository.receiptList = [awaiting, spinneys, zaatar, abouRami, { ...abouRami, id: 28 }];
    await new HomeService(repository).loadOverview(NOVEMBER_18);
    expect(repository.calls.filter((call) => call.startsWith('receipt '))).toEqual([
      'receipt 31',
      'receipt 30',
      'receipt 29',
    ]);
  });

  it('gives empty parts for a new account', async () => {
    const repository = new FakeHomeRepository();
    repository.spending = emptyMonth;
    repository.budgetList = [];
    repository.receiptList = [];

    const overview = await new HomeService(repository).loadOverview(NOVEMBER_18);

    expect(overview).toEqual({
      spending: emptyMonth,
      invoiceNumber: 1,
      budgets: [],
      everythingElse: '0.00',
      olderMonths: [],
      recent: [],
    });
    expect(repository.calls).not.toContainEqual(expect.stringMatching(/^receipt /));
  });

  it('uses the month in the phone’s calendar, January and December included', async () => {
    const repository = new FakeHomeRepository();
    const service = new HomeService(repository);
    await service.loadOverview(new Date(2027, 0, 1, 0, 30));
    await service.loadOverview(new Date(2026, 11, 31, 23, 30));
    expect(repository.calls.filter((call) => call.startsWith('summary'))).toEqual([
      'summary 2027-01',
      'summary 2026-12',
    ]);
  });

  it('passes on a HomeError, and turns anything else into one', async () => {
    const offline = new FakeHomeRepository();
    offline.offline = true;
    await expect(new HomeService(offline).loadOverview(NOVEMBER_18)).rejects.toMatchObject({ code: 'network' });

    const broken = new FakeHomeRepository();
    broken.itemCount = async () => {
      throw new TypeError('lines is undefined');
    };
    const error = await new HomeService(broken).loadOverview(NOVEMBER_18).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(HomeError);
    expect(error).toMatchObject({ code: 'unexpected', message: 'lines is undefined' });
  });
});
