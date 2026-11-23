/** What the app knows about an account (D041). Plain types: no React, no Expo, no HTTP. */

export const genders = ['female', 'male', 'prefer_not_to_say'] as const;

/** "Prefer not to say" is a real answer, not a missing one (D041). */
export type Gender = (typeof genders)[number];

export type User = {
  id: number;
  email: string;
  /** Null for accounts made before first names existed (D041). */
  firstName: string | null;
  /** Null for accounts made before gender existed (D041). */
  gender: Gender | null;
};

/** A signed-in session: the backend's access token, when it stops working, and whose it is. */
export type Session = {
  accessToken: string;
  /** Milliseconds since 1970 (Date.now()). */
  expiresAt: number;
  user: User;
};

export type SignUpDetails = {
  email: string;
  password: string;
  firstName: string;
  gender: Gender;
};

export function isGender(value: unknown): value is Gender {
  return typeof value === 'string' && (genders as readonly string[]).includes(value);
}
