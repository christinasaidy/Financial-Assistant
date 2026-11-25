import type { Appearance } from '../domain/appearance';

/** Where the appearance choice is kept on the phone. */
export interface AppearanceStore {
  /** The saved choice, or null when none is saved or it cannot be read. */
  load(): Promise<Appearance | null>;
  save(appearance: Appearance): Promise<void>;
}
