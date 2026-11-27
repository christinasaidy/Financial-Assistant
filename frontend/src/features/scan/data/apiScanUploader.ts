import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import { ReceiptsError } from '@/features/receipts/domain';

import type { Photo } from '../domain';

/** A photo upload can take a while on mobile data: longer than the client's usual 15 s. */
export const UPLOAD_TIMEOUT_MS = 60_000;

function extension(mimeType: string): string {
  if (mimeType === 'image/png') return 'png';
  if (mimeType === 'image/webp') return 'webp';
  return 'jpg';
}

/**
 * Sends a receipt photo to POST /receipts, and deletes an unsaved scan with DELETE /receipts/{id}. The photo goes
 * as multipart form data (field "file"); the backend stores it, answers at once with the new receipt (status
 * "uploaded"), and reads it in the background.
 */
export class ApiScanUploader {
  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  async remove(id: number): Promise<void> {
    await this.http.request(`/receipts/${id}`, { method: 'DELETE' });
  }

  async upload(photo: Photo): Promise<number> {
    const form = new FormData();
    // React Native's FormData takes a file as { uri, name, type }.
    form.append('file', { uri: photo.uri, name: `receipt.${extension(photo.mimeType)}`, type: photo.mimeType } as unknown as Blob);
    try {
      const receipt = await this.http.request<{ id: number }>('/receipts', { method: 'POST', body: form, timeoutMs: UPLOAD_TIMEOUT_MS });
      return receipt.id;
    } catch (error) {
      if (error instanceof NetworkError) throw new ReceiptsError('network', error.message);
      if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401) throw new ReceiptsError('refused', error.detail);
      if (error instanceof ApiError) throw new ReceiptsError('unexpected', error.detail);
      throw error;
    }
  }
}
