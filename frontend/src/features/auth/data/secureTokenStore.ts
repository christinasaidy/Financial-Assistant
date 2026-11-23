import type { SecureValue } from '@/shared/storage/tokenStore';

import type { TokenStore } from '../application/interfaces';
import { isGender, type Session } from '../domain/types';

/**
 * TokenStore on the Keychain: the session is saved as JSON in one secure value. Anything unreadable (an
 * older format, a half-written value) counts as no session, so a bad value can never lock the app.
 */
export class SecureTokenStore implements TokenStore {
  private readonly value: SecureValue;

  constructor(value: SecureValue) {
    this.value = value;
  }

  async load(): Promise<Session | null> {
    const text = await this.value.read();
    if (!text) return null;
    try {
      return parseSession(JSON.parse(text));
    } catch {
      return null;
    }
  }

  async save(session: Session): Promise<void> {
    await this.value.write(JSON.stringify(session));
  }

  async clear(): Promise<void> {
    await this.value.remove();
  }
}

function parseSession(raw: unknown): Session | null {
  if (!raw || typeof raw !== 'object') return null;
  const { accessToken, expiresAt, user } = raw as Record<string, unknown>;
  if (typeof accessToken !== 'string' || typeof expiresAt !== 'number' || !user || typeof user !== 'object') {
    return null;
  }
  const { id, email, firstName, gender } = user as Record<string, unknown>;
  if (typeof id !== 'number' || typeof email !== 'string') return null;
  return {
    accessToken,
    expiresAt,
    user: {
      id,
      email,
      firstName: typeof firstName === 'string' ? firstName : null,
      gender: isGender(gender) ? gender : null,
    },
  };
}
