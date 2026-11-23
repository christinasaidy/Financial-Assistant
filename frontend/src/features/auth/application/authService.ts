import { AuthError } from '../domain/errors';
import type { Session, SignUpDetails, User } from '../domain/types';
import type { AuthRepository, TokenStore } from './interfaces';

export type SessionListener = (user: User | null) => void;

/**
 * The auth use cases: sign in, create an account, sign out, and pick the session up again when the app
 * starts. It depends only on the two interfaces it is given, so it runs the same against the real
 * backend and Keychain or against fakes in a test.
 *
 * It also holds the current session in memory, so the HTTP client can read the token on every request
 * (accessToken()) and screens can follow sign-in and sign-out (subscribe()).
 */
export class AuthService {
  private session: Session | null = null;
  private readonly listeners = new Set<SessionListener>();
  private readonly repository: AuthRepository;
  private readonly tokenStore: TokenStore;
  private readonly now: () => number;

  constructor(repository: AuthRepository, tokenStore: TokenStore, now: () => number = Date.now) {
    this.repository = repository;
    this.tokenStore = tokenStore;
    this.now = now;
  }

  async signIn(email: string, password: string): Promise<User> {
    const result = await this.repository.login(email.trim(), password);
    await this.start({
      accessToken: result.accessToken,
      expiresAt: this.now() + result.expiresInSeconds * 1000,
      user: result.user,
    });
    return result.user;
  }

  /** Creates the account, then signs in with it (the backend's register does not return a token). */
  async signUp(details: SignUpDetails): Promise<User> {
    const cleaned: SignUpDetails = { ...details, email: details.email.trim(), firstName: details.firstName.trim() };
    await this.repository.register(cleaned);
    return this.signIn(cleaned.email, cleaned.password);
  }

  async signOut(): Promise<void> {
    await this.end();
  }

  /**
   * Called once at launch. Returns the signed-in user, or null if there is no usable session.
   * - No saved session, or it has expired: signed out.
   * - The backend rejects the token: signed out, and the saved session is removed.
   * - The backend cannot be reached: the saved session is kept (offline start); a later 401 ends it.
   */
  async restoreSession(): Promise<User | null> {
    const saved = await this.tokenStore.load();
    if (!saved) return null;
    if (saved.expiresAt <= this.now()) {
      await this.tokenStore.clear();
      return null;
    }
    try {
      const user = await this.repository.currentUser(saved.accessToken);
      await this.start({ ...saved, user });
      return user;
    } catch (error) {
      if (error instanceof AuthError && error.code === 'invalid-credentials') {
        await this.tokenStore.clear();
        return null;
      }
      this.setSession(saved);
      return saved.user;
    }
  }

  currentUser(): User | null {
    return this.session?.user ?? null;
  }

  accessToken(): string | null {
    if (!this.session || this.session.expiresAt <= this.now()) return null;
    return this.session.accessToken;
  }

  /** The backend rejected the token mid-session (HTTP 401). Ends the session without waiting. */
  expireSession(): void {
    if (!this.session) return;
    void this.end().catch(() => undefined);
  }

  /** Follow sign-in and sign-out. Returns the function that stops listening. */
  subscribe(listener: SessionListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private async start(session: Session): Promise<void> {
    await this.tokenStore.save(session);
    this.setSession(session);
  }

  private async end(): Promise<void> {
    this.setSession(null);
    await this.tokenStore.clear();
  }

  private setSession(session: Session | null): void {
    this.session = session;
    const user = session?.user ?? null;
    this.listeners.forEach((listener) => listener(user));
  }
}
