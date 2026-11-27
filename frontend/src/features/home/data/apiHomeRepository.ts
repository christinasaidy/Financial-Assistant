import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import type { HomeRepository } from '../application/interfaces';
import { HomeError } from '../domain/errors';
import type { BudgetState, BudgetUse, HomeCurrency, MonthSpending, ReceiptListing } from '../domain/types';

/**
 * The backend's shapes, snake_case as sent over HTTP. Decimals arrive as JSON strings
 * (backend/app/api/spending/schemas.py, budgets/schemas.py, receipts/schemas.py).
 */
export type CurrencySummaryDto = {
  currency: string;
  total: string;
  categories: { category_id: number | null; name: string; amount: string }[];
  adjustments: string;
  receipt_count: number;
};

export type MonthlySummaryDto = {
  month: string;
  combined: CurrencySummaryDto;
  by_currency: CurrencySummaryDto[];
  awaiting_review: number;
  converted_at_current_rate: number;
  current_lbp_per_usd: string;
};

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
  pace: { projected: string; low_confidence: boolean; projected_over: boolean } | null;
};

export type ReceiptSummaryDto = {
  id: number;
  status: string;
  vendor_name: string | null;
  receipt_date: string | null;
  currency: string | null;
  total: string | null;
  primary_category_id: number | null;
  lbp_per_usd: string | null;
  has_file: boolean;
  created_at: string;
};

export type CategoryDto = { id: number; name: string; is_shared: boolean };

export type ReceiptDto = ReceiptSummaryDto & {
  lines: unknown[];
  lines_total: string;
  flags: string[];
};

const BUDGET_STATES: readonly BudgetState[] = ['ok', 'near', 'limit_reached'];

function toCurrency(value: string | null): HomeCurrency | null {
  return value === 'USD' || value === 'LBP' ? value : null;
}

/** Decimals are strings; a number (from an older backend or a test) is kept exactly as JSON gave it. */
function decimal(value: string | number): string {
  return typeof value === 'number' ? String(value) : value;
}

function unreadable(what: string): HomeError {
  return new HomeError('unexpected', `The server sent ${what} that Home cannot read`);
}

export function toMonthSpending(dto: MonthlySummaryDto): MonthSpending {
  const part = (currency: HomeCurrency) => {
    const found = dto.by_currency.find((item) => item.currency === currency);
    return found && found.receipt_count > 0 ? decimal(found.total) : null;
  };
  return {
    month: dto.month,
    total: decimal(dto.combined.total),
    receiptCount: dto.combined.receipt_count,
    usdPart: part('USD'),
    lbpPart: part('LBP'),
    lbpPerUsd: decimal(dto.current_lbp_per_usd),
    awaitingReview: dto.awaiting_review,
    categories: dto.combined.categories.map((item) => ({
      categoryId: item.category_id,
      name: item.name,
      amount: decimal(item.amount),
    })),
  };
}

export function toBudgetUse(dto: BudgetStatusDto): BudgetUse {
  const currency = toCurrency(dto.currency);
  const state = BUDGET_STATES.find((candidate) => candidate === dto.state);
  if (!currency || !state) throw unreadable('a budget');
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

export function toReceiptListing(dto: ReceiptSummaryDto): ReceiptListing {
  return {
    id: dto.id,
    status: dto.status,
    shopName: dto.vendor_name?.trim() ? dto.vendor_name : null,
    receiptDate: dto.receipt_date,
    currency: toCurrency(dto.currency),
    total: dto.total === null ? null : decimal(dto.total),
    categoryId: dto.primary_category_id,
    lbpPerUsd: dto.lbp_per_usd === null ? null : decimal(dto.lbp_per_usd),
    createdAt: dto.created_at,
  };
}

/** HTTP failure -> the Home error the screen understands. A 401 has already signed the user out. */
export function toHomeError(error: unknown): HomeError {
  if (error instanceof HomeError) return error;
  if (error instanceof NetworkError) return new HomeError('network', error.message);
  if (error instanceof ApiError) return new HomeError('unexpected', error.detail);
  // A shape Home cannot read (a missing field) shows up as a TypeError while mapping.
  return new HomeError('unexpected', error instanceof Error ? error.message : String(error));
}

/**
 * HomeRepository against the Fatourati backend: GET /spending/summary, GET /budgets, GET /receipts,
 * GET /categories (the receipts' category names) and GET /receipts/{id} (for the item count, which the list
 * leaves out).
 */
export class ApiHomeRepository implements HomeRepository {
  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  monthSpending(month: string): Promise<MonthSpending> {
    return this.get('/spending/summary', { month, currency: 'USD' }, (dto: MonthlySummaryDto) => toMonthSpending(dto));
  }

  budgets(month: string): Promise<BudgetUse[]> {
    return this.get('/budgets', { month }, (dtos: BudgetStatusDto[]) => dtos.map(toBudgetUse));
  }

  receipts(): Promise<ReceiptListing[]> {
    return this.get('/receipts', undefined, (dtos: ReceiptSummaryDto[]) => dtos.map(toReceiptListing));
  }

  categoryNames(): Promise<Map<number, string>> {
    return this.get('/categories', undefined, (dtos: CategoryDto[]) => new Map(dtos.map((dto) => [dto.id, dto.name])));
  }

  itemCount(receiptId: number): Promise<number> {
    return this.get(`/receipts/${receiptId}`, undefined, (dto: ReceiptDto) => {
      if (!Array.isArray(dto.lines)) throw unreadable('a receipt');
      return dto.lines.length;
    });
  }

  private async get<Dto, Result>(
    path: string,
    query: Record<string, string> | undefined,
    map: (dto: Dto) => Result,
  ): Promise<Result> {
    try {
      return map(await this.http.request<Dto>(path, { query }));
    } catch (error) {
      throw toHomeError(error);
    }
  }
}
