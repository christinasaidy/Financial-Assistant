import {
  MAX_EMAIL_LENGTH,
  MAX_FIRST_NAME_LENGTH,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  checkEmail,
  checkFirstName,
  checkGender,
  checkNewPassword,
  hasProblems,
  validateSignIn,
  validateSignUp,
} from '@/features/auth/domain/validation';

describe('the limits are the backend rules (backend/app/domain/users/user.py)', () => {
  it('uses the same numbers', () => {
    expect({ MAX_EMAIL_LENGTH, MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH, MAX_FIRST_NAME_LENGTH }).toEqual({
      MAX_EMAIL_LENGTH: 254,
      MIN_PASSWORD_LENGTH: 8,
      MAX_PASSWORD_LENGTH: 128,
      MAX_FIRST_NAME_LENGTH: 50,
    });
  });
});

describe('checkEmail', () => {
  it.each(['christina@example.com', '  Christina@Example.COM  ', 'maya.k+fatourati@mail.co.lb'])('accepts %p', (email) => {
    expect(checkEmail(email)).toBeNull();
  });

  it.each([
    ['', 'email-missing'],
    ['   ', 'email-missing'],
    ['christina', 'email-invalid'],
    ['christina@example', 'email-invalid'],
    ['chris tina@example.com', 'email-invalid'],
    ['@example.com', 'email-invalid'],
    ['a@b@example.com', 'email-invalid'],
  ])('refuses %p (%s)', (email, problem) => {
    expect(checkEmail(email)).toBe(problem);
  });

  it('allows 254 characters and refuses 255, counted after trimming', () => {
    const at254 = `${'a'.repeat(254 - '@example.com'.length)}@example.com`;
    expect(at254).toHaveLength(254);
    expect(checkEmail(`  ${at254}  `)).toBeNull();
    expect(checkEmail(`a${at254}`)).toBe('email-too-long');
  });
});

describe('checkNewPassword', () => {
  it('needs 8 to 128 characters, counted as the backend counts them', () => {
    expect(checkNewPassword('')).toBe('password-missing');
    expect(checkNewPassword('1234567')).toBe('password-too-short');
    expect(checkNewPassword('12345678')).toBeNull();
    expect(checkNewPassword('x'.repeat(128))).toBeNull();
    expect(checkNewPassword('x'.repeat(129))).toBe('password-too-long');
    // Four emoji are 8 UTF-16 units but 4 characters to Python: too short.
    expect(checkNewPassword('🧾🧾🧾🧾')).toBe('password-too-short');
  });

  it('keeps spaces as part of the password', () => {
    expect(checkNewPassword('        ')).toBeNull();
  });
});

describe('checkFirstName', () => {
  it('is trimmed, then 1 to 50 characters', () => {
    expect(checkFirstName('')).toBe('first-name-missing');
    expect(checkFirstName('   ')).toBe('first-name-missing');
    expect(checkFirstName(' Christina ')).toBeNull();
    expect(checkFirstName(`  ${'a'.repeat(50)}  `)).toBeNull();
    expect(checkFirstName('a'.repeat(51))).toBe('first-name-too-long');
    expect(checkFirstName('كريستينا')).toBeNull();
  });

  it('refuses a NUL character, which the database cannot store', () => {
    expect(checkFirstName('Chris\u0000tina')).toBe('first-name-unsavable');
  });
});

describe('checkGender', () => {
  it('needs one of the three answers; "prefer not to say" is an answer', () => {
    expect(checkGender(null)).toBe('gender-missing');
    expect(checkGender('female')).toBeNull();
    expect(checkGender('male')).toBeNull();
    expect(checkGender('prefer_not_to_say')).toBeNull();
  });
});

describe('validateSignIn', () => {
  it('needs an email-shaped email and any password', () => {
    expect(validateSignIn({ email: '', password: '' })).toEqual({ email: 'email-missing', password: 'password-missing' });
    expect(validateSignIn({ email: 'christina', password: 'x' })).toEqual({ email: 'email-invalid' });
    // A short password is not refused here: the backend answers it like any wrong password.
    expect(hasProblems(validateSignIn({ email: 'christina@example.com', password: 'x' }))).toBe(false);
  });
});

describe('validateSignUp', () => {
  it('reports every field at once', () => {
    expect(validateSignUp({ firstName: ' ', email: 'nope', password: 'short', gender: null })).toEqual({
      firstName: 'first-name-missing',
      email: 'email-invalid',
      password: 'password-too-short',
      gender: 'gender-missing',
    });
  });

  it('passes a complete form', () => {
    const problems = validateSignUp({
      firstName: 'Christina',
      email: 'christina@example.com',
      password: 'zaatar-w-zeit',
      gender: 'prefer_not_to_say',
    });
    expect(problems).toEqual({});
    expect(hasProblems(problems)).toBe(false);
  });
});
