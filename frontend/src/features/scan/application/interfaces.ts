import type { ReceiptSummary } from '@/features/receipts/domain';

import type { BudgetLine, Category, ConfirmPayload, Photo, Receipt } from '../domain';

/**
 * The port of the Scan feature: what ScanService needs from the backend. The container builds it from the
 * uploader (data/apiScanUploader.ts) and the Receipts repository. Implementations throw errors the UI
 * turns into sentences (ReceiptsError, ScanError).
 *
 * `month` is the API's month format, "2026-11".
 */
export interface ScanRepository {
  /** Sends the photo; the backend reads it in the background. Returns the new receipt's id. */
  upload(photo: Photo): Promise<number>;
  /** Deletes a receipt that was never saved (Retake, or leaving while it is read). */
  remove(id: number): Promise<void>;
  /** The receipt as it stands (its status says whether it has been read). */
  receipt(id: number): Promise<Receipt>;
  /** All receipts without their items, for the invoice number. */
  receipts(): Promise<ReceiptSummary[]>;
  categories(): Promise<Category[]>;
  confirm(id: number, payload: ConfirmPayload): Promise<Receipt>;
  budgets(month: string): Promise<Map<number, BudgetLine>>;
  monthTotal(month: string): Promise<{ total: string; lbpPerUsd: string }>;
}
