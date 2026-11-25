import type { SecureValue } from '@/shared/storage/tokenStore';

import type { AppearanceStore } from '../application/interfaces';
import { isAppearance, type Appearance } from '../domain/appearance';

/**
 * AppearanceStore on one value in the phone's Keychain, the only storage the app has (expo-secure-store,
 * which works in Expo Go). The value is not secret; the Keychain is just where small values are kept.
 * Anything unreadable counts as nothing saved.
 */
export class StoredAppearanceStore implements AppearanceStore {
  private readonly value: SecureValue;

  constructor(value: SecureValue) {
    this.value = value;
  }

  async load(): Promise<Appearance | null> {
    const text = await this.value.read();
    return isAppearance(text) ? text : null;
  }

  async save(appearance: Appearance): Promise<void> {
    await this.value.write(appearance);
  }
}
