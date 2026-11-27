import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import { ReceiptsError } from '@/features/receipts/domain';

import type { Photo } from '../domain';

/** A photo upload can take a while on mobile data: longer than the client's usual 15 s. */
export const UPLOAD_TIMEOUT_MS = 60_000;

/**
 * Photos are shrunk to this many pixels on their short side before they are sent. Measured on 2026-11-27 with
 * Christina's receipt: Gemini took 42-62 s for the full 4032 x 2868 photo (1.5 MB) and 6 s for a 1600 px copy
 * (174 KB), reading it as well or better; it uses the same image tokens either way, so the time was the size.
 */
export const SHORT_SIDE_PX = 1200;

/** Makes a smaller JPEG copy of a photo when it is bigger than SHORT_SIDE_PX; returns it unchanged otherwise. */
export type Shrink = (photo: Photo) => Promise<Photo>;

export const shrinkPhoto: Shrink = async (photo) => {
  const context = ImageManipulator.manipulate(photo.uri);
  const original = await context.renderAsync();
  const short = Math.min(original.width, original.height);
  if (short <= SHORT_SIDE_PX) return photo;
  context.reset();
  const scale = SHORT_SIDE_PX / short;
  context.resize({ width: Math.round(original.width * scale), height: Math.round(original.height * scale) });
  const smaller = await (await context.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: 0.8 });
  return { uri: smaller.uri, mimeType: 'image/jpeg' };
};

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
  private readonly shrink: Shrink;

  constructor(http: HttpClient, shrink: Shrink = shrinkPhoto) {
    this.http = http;
    this.shrink = shrink;
  }

  async remove(id: number): Promise<void> {
    await this.http.request(`/receipts/${id}`, { method: 'DELETE' });
  }

  async upload(original: Photo): Promise<number> {
    // If shrinking fails for any reason, the full photo still goes: slower, but it still works.
    const photo = await this.shrink(original).catch(() => original);
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
