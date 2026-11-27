/** Every sentence the sign-in and create-account screens can show when something needs fixing. */
import { AuthError } from '../domain/errors';
import {
  MAX_EMAIL_LENGTH,
  MAX_FIRST_NAME_LENGTH,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  type EmailProblem,
  type FirstNameProblem,
  type GenderProblem,
  type PasswordProblem,
} from '../domain/validation';

export type FormProblem = EmailProblem | PasswordProblem | FirstNameProblem | GenderProblem;

export const problemMessages: Record<FormProblem, string> = {
  'email-missing': 'Enter your email.',
  'email-invalid': 'Enter an email like name@example.com.',
  'email-too-long': `Emails can be at most ${MAX_EMAIL_LENGTH} characters.`,
  'password-missing': 'Enter your password.',
  'password-too-short': `Use at least ${MIN_PASSWORD_LENGTH} characters.`,
  'password-too-long': `Use at most ${MAX_PASSWORD_LENGTH} characters.`,
  'first-name-missing': 'Enter your first name.',
  'first-name-too-long': `Use at most ${MAX_FIRST_NAME_LENGTH} characters.`,
  'first-name-unsavable': 'Your first name has a character that cannot be saved. Remove it and try again.',
  'gender-missing': 'Choose Female, Male or Prefer not to say.',
};

/** The hint under the new password, before anything goes wrong. */
export const passwordHint = `At least ${MIN_PASSWORD_LENGTH} characters`;

export const serverMessages = {
  'invalid-credentials': 'Wrong email or password.',
  'email-taken': 'An account already uses this email.',
  network: "Can't reach Fatourati. Check your connection and try again.",
  unexpected: 'Fatourati could not finish this. Try again in a moment.',
} as const;

/**
 * What to say when the backend refuses. `field: 'email'` puts the sentence under the email line (an account
 * already uses it); everything else goes above the button, because it is about the whole form.
 */
export function messageForError(error: unknown): { field: 'email' | null; message: string } {
  if (!(error instanceof AuthError)) return { field: null, message: serverMessages.unexpected };
  switch (error.code) {
    case 'invalid-credentials':
      return { field: null, message: serverMessages['invalid-credentials'] };
    case 'email-taken':
      return { field: 'email', message: serverMessages['email-taken'] };
    case 'network':
      return { field: null, message: serverMessages.network };
    case 'invalid-details':
      // The form checks the same rules first, so this is rare. The backend's own sentence is already plain
      // ("Enter a valid email address", "Password must be at least 8 characters").
      return { field: null, message: sentence(error.message) || serverMessages.unexpected };
    case 'unexpected':
      return { field: null, message: serverMessages.unexpected };
  }
}

function sentence(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length === 0) return '';
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}
