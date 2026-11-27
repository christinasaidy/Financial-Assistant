import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import type { ReceiptsRepository } from '../application/interfaces';
import { ReceiptsError, type BudgetLine, type Category, type ConfirmPayload, type Currency, type Receipt, type ReceiptLine, type ReceiptSummary } from '../domain';

/** The backend's shapes (backend/app/api/receipts/schemas.py), snake_case; decimals as strings. */
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

export type LineDto = {
  id: number | null;
  description: string;
  line_total: string;
  quantity: string;
  unit_price: string | null;
  normalized_name: string | null;
  size_amount: string | null;
  size_unit: string | null;
  category_id: number | null;
  brand: string | null;
};

export type ReceiptDto = ReceiptSummaryDto & { lines: LineDto[]; lines_total: string; flags: string[] };

function decimal(value: string | number): string {
  return typeof value === 'number' ? String(value) : value;
}

function currency(value: string | null): Currency | null {
  return value === 'USD' || value === 'LBP' ? value : null;
}

export function toSummary(dto: ReceiptSummaryDto): ReceiptSummary {
  return {
    id: dto.id,
    status: dto.status,
    shopName: dto.vendor_name?.trim() ? dto.vendor_name : null,
    receiptDate: dto.receipt_date,
    currency: currency(dto.currency),
    total: dto.total === null ? null : decimal(dto.total),
    categoryId: dto.primary_category_id,
    lbpPerUsd: dto.lbp_per_usd === null ? null : decimal(dto.lbp_per_usd),
    createdAt: dto.created_at,
  };
}

export function toLine(dto: LineDto): ReceiptLine {
  const optional = (value: string | number | null) => (value === null ? null : decimal(value));
  return {
    id: dto.id,
    description: dto.description,
    lineTotal: decimal(dto.line_total),
    quantity: decimal(dto.quantity),
    unitPrice: optional(dto.unit_price),
    normalizedName: dto.normalized_name,
    sizeAmount: optional(dto.size_amount),
    sizeUnit: dto.size_unit,
    categoryId: dto.category_id,
    brand: dto.brand,
  };
}

export function toReceipt(dto: ReceiptDto): Receipt {
  return { ...toSummary(dto), lines: dto.lines.map(toLine), flags: dto.flags };
}

/** The confirm body: every value, and every item with all its fields; the saved rate is kept (left out). */
export function toConfirmBody(payload: ConfirmPayload) {
  return {
    vendor_name: payload.shopName,
    receipt_date: payload.receiptDate,
    currency: payload.currency,
    total: payload.total,
    primary_category_id: payload.categoryId,
    lines: payload.lines.map((line) => ({
      description: line.description,
      line_total: line.lineTotal,
      quantity: line.quantity,
      unit_price: line.unitPrice,
      normalized_name: line.normalizedName,
      size_amount: line.sizeAmount,
      size_unit: line.sizeUnit,
      category_id: line.categoryId,
      brand: line.brand,
    })),
  };
}

export function toReceiptsError(error: unknown): ReceiptsError {
  if (error instanceof ReceiptsError) return error;
  if (error instanceof NetworkError) return new ReceiptsError('network', error.message);
  if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401) {
    return new ReceiptsError('refused', error.detail);
  }
  if (error instanceof ApiError) return new ReceiptsError('unexpected', error.detail);
  return new ReceiptsError('unexpected', error instanceof Error ? error.message : String(error));
}

/**
 * ReceiptsRepository against the Fatourati backend: GET /receipts(/{id}), GET /categories,
 * GET /spending/summary, GET /budgets and POST /receipts/{id}/confirm.
 */
export class ApiReceiptsRepository implements ReceiptsRepository {
  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  receipts(): Promise<ReceiptSummary[]> {
    return this.call(async () => (await this.http.request<ReceiptSummaryDto[]>('/receipts')).map(toSummary));
  }

  receipt(id: number): Promise<Receipt> {
    return this.call(async () => toReceipt(await this.http.request<ReceiptDto>(`/receipts/${id}`)));
  }

  categories(): Promise<Category[]> {
    return this.call(async () =>
      (await this.http.request<{ id: number; name: string }[]>('/categories')).map(({ id, name }) => ({ id, name })),
    );
  }

  monthTotal(month: string): Promise<{ total: string; lbpPerUsd: string }> {
    return this.call(async () => {
      const dto = await this.http.request<{ combined: { total: string }; current_lbp_per_usd: string }>('/spending/summary', {
        query: { month, currency: 'USD' },
      });
      return { total: decimal(dto.combined.total), lbpPerUsd: decimal(dto.current_lbp_per_usd) };
    });
  }

  budgets(month: string): Promise<Map<number, BudgetLine>> {
    return this.call(async () => {
      const dtos = await this.http.request<{ category_id: number; category_name: string; currency: string; limit_amount: string; spent: string }[]>(
        '/budgets',
        { query: { month } },
      );
      return new Map(
        dtos.map((dto) => [
          dto.category_id,
          { name: dto.category_name, currency: dto.currency === 'LBP' ? 'LBP' : 'USD', limit: decimal(dto.limit_amount), spent: decimal(dto.spent) },
        ]),
      );
    });
  }

  confirm(id: number, payload: ConfirmPayload): Promise<Receipt> {
    return this.call(async () => toReceipt(await this.http.request<ReceiptDto>(`/receipts/${id}/confirm`, { method: 'POST', body: toConfirmBody(payload) })));
  }

  private async call<T>(run: () => Promise<T>): Promise<T> {
    try {
      return await run();
    } catch (error) {
      throw toReceiptsError(error);
    }
  }
}
