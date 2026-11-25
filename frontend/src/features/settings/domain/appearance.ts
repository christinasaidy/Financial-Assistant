/**
 * How the app looks (D043): follow the phone's light or dark setting, or always light, or always dark.
 * A phone setting, not an account one: it is kept on the phone and survives signing out.
 */
export const appearances = ['phone', 'light', 'dark'] as const;

export type Appearance = (typeof appearances)[number];

/** Until the user picks one, the app follows the phone (D003). */
export const defaultAppearance: Appearance = 'phone';

export function isAppearance(value: unknown): value is Appearance {
  return typeof value === 'string' && (appearances as readonly string[]).includes(value);
}

/** The theme to force, or null to follow the phone. */
export function forcedScheme(appearance: Appearance): 'light' | 'dark' | null {
  return appearance === 'phone' ? null : appearance;
}
