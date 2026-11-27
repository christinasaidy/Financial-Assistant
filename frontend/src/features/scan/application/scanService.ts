import { invoiceNumber } from '@/features/home/domain/rules';
import { toApiMonth } from '@/shared/format/dates';

import { categoryName } from '@/features/receipts/domain';

import { filedNumbers, payloadFrom, readingState, type Category, type Draft, type Filed, type Photo, type Receipt } from '../domain';
import type { ScanRepository } from './interfaces';

/** Why a scan stopped: the backend could not read the photo, or took too long. Other failures pass through. */
export class ScanError extends Error {
  readonly code: 'failed' | 'timeout';

  constructor(code: 'failed' | 'timeout', message: string) {
    super(message);
    this.name = 'ScanError';
    this.code = code;
  }
}

export type WaitOptions = {
  /** How often to ask whether it has been read. */
  intervalMs?: number;
  /** When to give up. The backend's model takes a few seconds; a minute and a half covers its retries. */
  timeoutMs?: number;
  /** Stops waiting (leaving the Reading screen). */
  signal?: { aborted: boolean };
  /** For tests: how to wait between checks. */
  sleep?: (ms: number) => Promise<void>;
};

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function firstOfMonth(apiDate: string): Date {
  return new Date(Number(apiDate.slice(0, 4)), Number(apiDate.slice(5, 7)) - 1, 1);
}

/**
 * The Scan use cases (design/screens/09-12): send a photo, wait until the backend has read it, give Review what it
 * needs, and save the checked receipt, returning what the Filed screen shows.
 */
export class ScanService {
  private readonly repository: ScanRepository;

  constructor(repository: ScanRepository) {
    this.repository = repository;
  }

  upload(photo: Photo): Promise<number> {
    return this.repository.upload(photo);
  }

  /** Asks until the receipt has been read. Throws ScanError('failed') if it could not be, ('timeout') after the limit. */
  async waitUntilRead(id: number, options: WaitOptions = {}): Promise<Receipt> {
    const { intervalMs = 1500, timeoutMs = 90_000, signal, sleep = pause } = options;
    const started = Date.now();
    for (let checks = 0; ; checks += 1) {
      const receipt = await this.repository.receipt(id);
      const state = readingState(receipt.status);
      if (state === 'ready') return receipt;
      if (state === 'failed') throw new ScanError('failed', 'Fatourati could not read this photo.');
      if (signal?.aborted) throw new ScanError('timeout', 'Stopped');
      if (Date.now() - started >= timeoutMs || checks * intervalMs >= timeoutMs) {
        throw new ScanError('timeout', 'Reading this receipt is taking too long.');
      }
      await sleep(intervalMs);
    }
  }

  /** Review's receipt, the categories to choose from, and the invoice it goes into. */
  async loadReview(id: number, today: Date): Promise<{ receipt: Receipt; categories: Category[]; invoiceNumber: number }> {
    const [receipt, categories, all] = await Promise.all([this.repository.receipt(id), this.repository.categories(), this.repository.receipts()]);
    const month = receipt.receiptDate ? firstOfMonth(receipt.receiptDate) : today;
    return { receipt, categories, invoiceNumber: invoiceNumber(month, all) };
  }

  /** Deletes a scanned receipt that was not saved; a failure here is not worth an error on screen. */
  async discard(id: number): Promise<void> {
    try {
      await this.repository.remove(id);
    } catch {
      // The draft stays "needs review" and is never counted; nothing else to do.
    }
  }

  /** Saves the checked draft (the caller has checked it), then reads back what changed for the Filed screen. */
  async save(id: number, draft: Draft): Promise<Filed> {
    return this.filedFrom(await this.repository.confirm(id, payloadFrom(draft)));
  }

  /** The Filed screen for a saved receipt. */
  async filed(id: number): Promise<Filed> {
    return this.filedFrom(await this.repository.receipt(id));
  }

  private async filedFrom(saved: Receipt): Promise<Filed> {
    const month = firstOfMonth(saved.receiptDate as string);
    const apiMonth = toApiMonth(month);
    const [budgets, { total, lbpPerUsd }, categories, all] = await Promise.all([
      this.repository.budgets(apiMonth),
      this.repository.monthTotal(apiMonth),
      this.repository.categories(),
      this.repository.receipts(),
    ]);
    const budget = saved.categoryId === null ? null : (budgets.get(saved.categoryId) ?? null);
    return {
      receipt: saved,
      category: categoryName(categories, saved.categoryId),
      ...filedNumbers(saved, budget, Number.parseFloat(total) || 0, Number.parseFloat(lbpPerUsd) || 0),
      invoiceNumber: invoiceNumber(month, all),
      month,
    };
  }
}
