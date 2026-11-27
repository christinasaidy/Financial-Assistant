/**
 * Why signing in or creating an account failed, in terms the screens can act on. The data layer turns
 * HTTP statuses into these, so the UI never looks at status codes.
 */
export type AuthErrorCode =
  /** Wrong email or password (sign in). */
  | 'invalid-credentials'
  /** The email already has an account (create account). */
  | 'email-taken'
  /** The backend refused a value: an invalid email, a weak password, a missing name. `message` says which. */
  | 'invalid-details'
  /** The phone could not reach the backend. */
  | 'network'
  /** Anything else (a server error). */
  | 'unexpected';

export class AuthError extends Error {
  readonly code: AuthErrorCode;

  constructor(code: AuthErrorCode, message: string) {
    super(message);
    this.name = 'AuthError';
    this.code = code;
  }
}
