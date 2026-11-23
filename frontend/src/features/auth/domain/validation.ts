/**
 * The checks the sign-in and create-account forms run before calling the backend. They mirror the backend's
 * rules (backend/app/domain/users/user.py), so a form the app accepts is one the backend accepts too; the
 * backend still checks everything itself.
 *
 * The checks return problem codes, not sentences: the words are the screens' job (ui/authMessages.ts).
 */
import { isGender, type Gender } from './types';

/** user.py MAX_EMAIL_LENGTH. */
export const MAX_EMAIL_LENGTH = 254;
/** user.py MIN_PASSWORD_LENGTH. */
export const MIN_PASSWORD_LENGTH = 8;
/** user.py MAX_PASSWORD_LENGTH. */
export const MAX_PASSWORD_LENGTH = 128;
/** user.py MAX_FIRST_NAME_LENGTH. */
export const MAX_FIRST_NAME_LENGTH = 50;

/** user.py _EMAIL_PATTERN: something@something.something, no spaces. */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export type EmailProblem = 'email-missing' | 'email-invalid' | 'email-too-long';
export type PasswordProblem = 'password-missing' | 'password-too-short' | 'password-too-long';
export type FirstNameProblem = 'first-name-missing' | 'first-name-too-long' | 'first-name-unsavable';
export type GenderProblem = 'gender-missing';

export type SignInForm = { email: string; password: string };
export type SignInProblems = { email?: EmailProblem; password?: 'password-missing' };

export type SignUpForm = { firstName: string; email: string; password: string; gender: Gender | null };
export type SignUpProblems = {
  firstName?: FirstNameProblem;
  email?: EmailProblem;
  password?: PasswordProblem;
  gender?: GenderProblem;
};

/**
 * Length as Python counts it (code points), so an emoji counts once, as it does on the backend.
 * JavaScript's `.length` would count it twice.
 */
function characters(text: string): number {
  return [...text].length;
}

/** The backend trims and lower-cases the email before checking it (normalize_email). */
export function checkEmail(raw: string): EmailProblem | null {
  const email = raw.trim().toLowerCase();
  if (email.length === 0) return 'email-missing';
  if (characters(email) > MAX_EMAIL_LENGTH) return 'email-too-long';
  if (!EMAIL_PATTERN.test(email)) return 'email-invalid';
  return null;
}

/** validate_password. The password is never trimmed: spaces are part of it. */
export function checkNewPassword(password: string): PasswordProblem | null {
  if (password.length === 0) return 'password-missing';
  if (characters(password) < MIN_PASSWORD_LENGTH) return 'password-too-short';
  if (characters(password) > MAX_PASSWORD_LENGTH) return 'password-too-long';
  return null;
}

/** normalize_first_name: trimmed, then 1 to 50 characters, and no NUL (PostgreSQL cannot store it). */
export function checkFirstName(raw: string): FirstNameProblem | null {
  const firstName = raw.trim();
  if (firstName.length === 0) return 'first-name-missing';
  if (characters(firstName) > MAX_FIRST_NAME_LENGTH) return 'first-name-too-long';
  if (firstName.includes('\u0000')) return 'first-name-unsavable';
  return null;
}

export function checkGender(gender: Gender | null): GenderProblem | null {
  return isGender(gender) ? null : 'gender-missing';
}

/**
 * Sign in only needs something in both fields and an email-shaped email. The password's length is not
 * checked: a wrong password gets the backend's one generic answer, as any other wrong password does.
 */
export function validateSignIn(form: SignInForm): SignInProblems {
  const problems: SignInProblems = {};
  const email = checkEmail(form.email);
  if (email) problems.email = email;
  if (form.password.length === 0) problems.password = 'password-missing';
  return problems;
}

export function validateSignUp(form: SignUpForm): SignUpProblems {
  const problems: SignUpProblems = {};
  const firstName = checkFirstName(form.firstName);
  if (firstName) problems.firstName = firstName;
  const email = checkEmail(form.email);
  if (email) problems.email = email;
  const password = checkNewPassword(form.password);
  if (password) problems.password = password;
  const gender = checkGender(form.gender);
  if (gender) problems.gender = gender;
  return problems;
}

export function hasProblems(problems: object): boolean {
  return Object.keys(problems).length > 0;
}
