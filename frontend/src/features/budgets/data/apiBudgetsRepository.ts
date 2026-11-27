import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import type { BudgetsRepository } from '../application/interfaces';
import { BudgetsError } from '../domain/errors';
import type { Budget, BudgetCurrency, BudgetState, Category, MonthSpending } from '../domain/types';

/** The backend's shapes, snake_case; decimals arrive as JSON strings (backend/app/api/budgets, spending, categories). */
export type BudgetStatusDto = {
  category_id: number;
  category_name: string;
  month: string;
  set_in: string;
  currency: string;
  limit_amount: string;
  spent: string;
  remaining: string;
  percent_used: string;
  state: string;
  pace: unknown;
};

export type SummaryDto = {
  combined: { total: string; categories: { category_id: number | null; name: string; amount: string }[] };
  current_lbp_per_usd: string;
};

export type CategoryDto = { id: number; name: string; is_shared: boolean };

const STATES: readonly BudgetState[] = ['ok', 'near', 'limit_reached'];

function decimal(value: string | number): string {
  return typeof value === 'number' ? String(value) : value;
}

export function toBudget(dto: BudgetStatusDto): Budget {
  const currency = dto.currency === 'USD' || dto.currency === 'LBP' ? dto.currency : null;
  const state = STATES.find((candidate) => candidate === dto.state);
  if (!currency || !state) throw new BudgetsError('unexpected', 'The server sent a budget the app cannot read');
  return {
    categoryId: dto.category_id,
    name: dto.category_name,
    currency,
    limit: decimal(dto.limit_amount),
    spent: decimal(dto.spent),
    percentUsed: decimal(dto.percent_used),
    state,
  };
}

export function toSpending(dto: SummaryDto): MonthSpending {
  return {
    total: decimal(dto.combined.total),
    categories: dto.combined.categories.map((item) => ({ categoryId: item.category_id, amount: decimal(item.amount) })),
    lbpPerUsd: decimal(dto.current_lbp_per_usd),
  };
}

/** HTTP failure -> the error the screen understands. A 4xx on saving carries the backend's own message. */
export function toBudgetsError(error: unknown): BudgetsError {
  if (error instanceof BudgetsError) return error;
  if (error instanceof NetworkError) return new BudgetsError('network', error.message);
  if (error instanceof ApiError) {
    return error.status >= 400 && error.status < 500 && error.status !== 401
      ? new BudgetsError('rejected', error.detail)
      : new BudgetsError('unexpected', error.detail);
  }
  return new BudgetsError('unexpected', error instanceof Error ? error.message : String(error));
}

/**
 * BudgetsRepository against the Fatourati backend: GET /budgets, GET /spending/summary, GET /categories,
 * PUT /budgets/{category_id} and DELETE /budgets/{category_id}.
 */
export class ApiBudgetsRepository implements BudgetsRepository {
  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  budgets(month: string): Promise<Budget[]> {
    return this.call(async () => (await this.http.request<BudgetStatusDto[]>('/budgets', { query: { month } })).map(toBudget));
  }

  spending(month: string): Promise<MonthSpending> {
    return this.call(async () => toSpending(await this.http.request<SummaryDto>('/spending/summary', { query: { month, currency: 'USD' } })));
  }

  categories(): Promise<Category[]> {
    return this.call(async () =>
      (await this.http.request<CategoryDto[]>('/categories')).map((dto) => ({ id: dto.id, name: dto.name })),
    );
  }

  setBudget(categoryId: number, month: string, currency: BudgetCurrency, limit: string): Promise<void> {
    return this.call(async () => {
      await this.http.request(`/budgets/${categoryId}`, {
        method: 'PUT',
        body: { month, currency, limit_amount: limit },
      });
    });
  }

  removeBudget(categoryId: number): Promise<void> {
    return this.call(async () => {
      await this.http.request(`/budgets/${categoryId}`, { method: 'DELETE' });
    });
  }

  private async call<T>(run: () => Promise<T>): Promise<T> {
    try {
      return await run();
    } catch (error) {
      throw toBudgetsError(error);
    }
  }
}
