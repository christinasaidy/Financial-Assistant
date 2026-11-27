import { BudgetsService } from '@/features/budgets/application/budgetsService';
import { ApiBudgetsRepository, toBudget } from '@/features/budgets/data/apiBudgetsRepository';
import { BudgetsError } from '@/features/budgets/domain';
import { createHttpClient } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';
import { FakeBudgetsRepository, novemberSpending } from './fakes';

const NOV = new Date(2026, 10, 18);

describe('BudgetsService', () => {
  it('loads the month: budgets closest to their limit first, spending, and categories without a budget', async () => {
    const repository = new FakeBudgetsRepository();
    const month = await new BudgetsService(repository).loadMonth(NOV);
    expect(repository.calls).toEqual(['budgets 2026-11', 'spending 2026-11', 'categories']);
    expect(month.month).toEqual(new Date(2026, 10, 1));
    expect(month.budgets.map((budget) => budget.name)).toEqual(['Transport', 'Eating out', 'Groceries']);
    expect(month.spending).toEqual(novemberSpending);
    expect(month.unbudgeted.map((category) => category.name)).toEqual(['Bills', 'Pharmacy']);
  });

  it('saves a limit from the month onwards, and removes a budget', async () => {
    const repository = new FakeBudgetsRepository();
    const service = new BudgetsService(repository);
    await service.save({ categoryId: 5, month: NOV, currency: 'USD', limit: '120' });
    await service.remove(1);
    expect(repository.calls).toEqual(['set 5 2026-11 USD 120', 'remove 1']);
  });

  it('passes on a BudgetsError and turns anything else into one', async () => {
    const repository = new FakeBudgetsRepository();
    repository.offline = true;
    await expect(new BudgetsService(repository).loadMonth(NOV)).rejects.toMatchObject({ code: 'network' });
    repository.offline = false;
    repository.categories = async () => {
      throw new TypeError('boom');
    };
    await expect(new BudgetsService(repository).loadMonth(NOV)).rejects.toBeInstanceOf(BudgetsError);
  });
});

function repositoryWith(...replies: Parameters<typeof fetchMock>) {
  const { fetchFn, requests } = fetchMock(...replies);
  const http = createHttpClient({ baseUrl: 'http://192.168.1.23:8000', getToken: () => 'jwt', onUnauthorized: jest.fn(), fetchFn });
  return { repository: new ApiBudgetsRepository(http), requests };
}

const budgetDto = {
  category_id: 2,
  category_name: 'Eating out',
  month: '2026-11-01',
  set_in: '2026-10-01',
  currency: 'USD',
  limit_amount: '80.00',
  spent: '71.50',
  remaining: '8.50',
  percent_used: '89.4',
  state: 'near',
  pace: null,
};

describe('ApiBudgetsRepository', () => {
  it('reads the month’s budgets', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: [budgetDto] });
    await expect(repository.budgets('2026-11')).resolves.toEqual([
      { categoryId: 2, name: 'Eating out', currency: 'USD', limit: '80.00', spent: '71.50', percentUsed: '89.4', state: 'near' },
    ]);
    expect(requests[0]?.url).toBe('http://192.168.1.23:8000/budgets?month=2026-11');
    expect(() => toBudget({ ...budgetDto, state: 'over' })).toThrow(BudgetsError);
  });

  it('reads the month’s spending by category, in dollars', async () => {
    const { repository, requests } = repositoryWith({
      status: 200,
      body: {
        combined: { total: '447.80', categories: [{ category_id: 3, name: 'Groceries', amount: '186.40' }] },
        current_lbp_per_usd: '89500.00',
      },
    });
    await expect(repository.spending('2026-11')).resolves.toEqual({
      total: '447.80',
      categories: [{ categoryId: 3, amount: '186.40' }],
      lbpPerUsd: '89500.00',
    });
    expect(requests[0]?.url).toBe('http://192.168.1.23:8000/spending/summary?month=2026-11&currency=USD');
  });

  it('sets a budget with PUT and removes one with DELETE', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: budgetDto }, { status: 204 });
    await repository.setBudget(2, '2026-11', 'LBP', '3000000');
    await repository.removeBudget(2);
    expect(requests[0]).toMatchObject({
      url: 'http://192.168.1.23:8000/budgets/2',
      method: 'PUT',
      body: { month: '2026-11', currency: 'LBP', limit_amount: '3000000' },
    });
    expect(requests[1]).toMatchObject({ url: 'http://192.168.1.23:8000/budgets/2', method: 'DELETE' });
  });

  it('keeps the backend’s message when it refuses a budget, and says when it cannot be reached', async () => {
    const refused = repositoryWith({ status: 422, body: { detail: 'The limit is too large' } });
    await expect(refused.repository.setBudget(2, '2026-11', 'USD', '1e30')).rejects.toMatchObject({
      code: 'rejected',
      message: 'The limit is too large',
    });
    const offline = repositoryWith({ networkError: 'Network request failed' });
    await expect(offline.repository.categories()).rejects.toMatchObject({ code: 'network' });
  });
});
