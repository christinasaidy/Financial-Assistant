import * as SecureStore from 'expo-secure-store';

/**
 * One secret string kept in the iPhone's Keychain through expo-secure-store (works in Expo Go).
 * Features build on this: auth keeps its session token here (features/auth/data/secureTokenStore.ts).
 */
export type SecureValue = {
  read(): Promise<string | null>;
  write(value: string): Promise<void>;
  remove(): Promise<void>;
};

/** Keys may only contain letters, digits, ".", "-" and "_" (expo-secure-store's rule). */
export function secureValue(key: string): SecureValue {
  return {
    read: () => SecureStore.getItemAsync(key),
    write: (value) => SecureStore.setItemAsync(key, value),
    remove: () => SecureStore.deleteItemAsync(key),
  };
}

/** The key the signed-in session is kept under. */
export const SESSION_KEY = 'fatourati.session';

/** The key the appearance setting is kept under (D043). */
export const APPEARANCE_KEY = 'fatourati.appearance';
