import { defaultAppearance, type Appearance } from '../domain/appearance';
import type { AppearanceStore } from './interfaces';

/** The app's settings that live on the phone: for now, the appearance (D043). */
export class SettingsService {
  private readonly store: AppearanceStore;

  constructor(store: AppearanceStore) {
    this.store = store;
  }

  /** The saved appearance; following the phone when nothing is saved or the store fails. */
  async loadAppearance(): Promise<Appearance> {
    try {
      return (await this.store.load()) ?? defaultAppearance;
    } catch {
      return defaultAppearance;
    }
  }

  /** Saves the choice. A failed save is not worth an error on screen: the choice still applies until the app closes. */
  async setAppearance(appearance: Appearance): Promise<void> {
    try {
      await this.store.save(appearance);
    } catch {
      // Ignored on purpose (see above).
    }
  }
}
