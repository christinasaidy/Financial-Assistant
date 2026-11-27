import type { AuthRepository, SignInResult, TokenStore } from '@/features/auth/application/interfaces';
import { AuthError } from '@/features/auth/domain/errors';
import type { Session, SignUpDetails, User } from '@/features/auth/domain/types';

export const christina: User = { id: 7, email: 'christina@example.com', firstName: 'Christina', gender: 'female' };

/** An in-memory backend: accounts by email, tokens by value. */
export class FakeAuthRepository implements AuthRepository {
  readonly accounts = new Map<string, { password: string; user: User }>();
  readonly validTokens = new Map<string, User>();
  /** Set to make every call fail as if the phone were offline. */
  offline = false;
  calls: string[] = [];
  private nextId = 1;

  async register(details: SignUpDetails): Promise<User> {
    this.calls.push(`register ${details.email}`);
    this.failIfOffline();
    if (this.accounts.has(details.email)) throw new AuthError('email-taken', 'Email already registered');
    const user: User = {
      id: this.nextId++,
      email: details.email,
      firstName: details.firstName,
      gender: details.gender,
    };
    this.accounts.set(details.email, { password: details.password, user });
    return user;
  }

  async login(email: string, password: string): Promise<SignInResult> {
    this.calls.push(`login ${email}`);
    this.failIfOffline();
    const account = this.accounts.get(email);
    if (!account || account.password !== password) {
      throw new AuthError('invalid-credentials', 'Wrong email or password');
    }
    const token = `token-${email}-${this.calls.length}`;
    this.validTokens.set(token, account.user);
    return { accessToken: token, expiresInSeconds: 3600, user: account.user };
  }

  async currentUser(accessToken: string): Promise<User> {
    this.calls.push('me');
    this.failIfOffline();
    const user = this.validTokens.get(accessToken);
    if (!user) throw new AuthError('invalid-credentials', 'Invalid token');
    return user;
  }

  private failIfOffline(): void {
    if (this.offline) throw new AuthError('network', 'Could not reach the server');
  }
}

export class FakeTokenStore implements TokenStore {
  saved: Session | null = null;

  async load(): Promise<Session | null> {
    return this.saved;
  }

  async save(session: Session): Promise<void> {
    this.saved = session;
  }

  async clear(): Promise<void> {
    this.saved = null;
  }
}
