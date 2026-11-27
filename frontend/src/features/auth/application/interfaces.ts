import type { Session, SignUpDetails, User } from '../domain/types';

/**
 * The ports of the auth feature: what AuthService needs from the outside world, written from its point of
 * view. The data layer implements them (apiAuthRepository.ts, secureTokenStore.ts); tests use fakes.
 */

export type SignInResult = {
  accessToken: string;
  /** Seconds the token stays valid, as the backend sends it. */
  expiresInSeconds: number;
  user: User;
};

/** Accounts on the backend. Implementations throw AuthError for expected failures. */
export interface AuthRepository {
  register(details: SignUpDetails): Promise<User>;
  login(email: string, password: string): Promise<SignInResult>;
  /** The account the token belongs to. Throws AuthError('invalid-credentials') if the token is rejected. */
  currentUser(accessToken: string): Promise<User>;
}

/** Keeps the session across app launches, somewhere safe (the Keychain). */
export interface TokenStore {
  load(): Promise<Session | null>;
  save(session: Session): Promise<void>;
  clear(): Promise<void>;
}
