import type { AppearanceStore } from '@/features/settings/application/interfaces';
import type { Appearance } from '@/features/settings/domain/appearance';

/** An appearance store in memory; set `fail` to make the Keychain unavailable. */
export class FakeAppearanceStore implements AppearanceStore {
  saved: Appearance | null = null;
  fail = false;

  async load() {
    if (this.fail) throw new Error('Keychain unavailable');
    return this.saved;
  }

  async save(appearance: Appearance) {
    if (this.fail) throw new Error('Keychain unavailable');
    this.saved = appearance;
  }
}
