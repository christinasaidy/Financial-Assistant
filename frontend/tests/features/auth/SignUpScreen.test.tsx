import { fireEvent, screen, testRouter, waitFor } from 'expo-router/testing-library';
import { AccessibilityInfo, Keyboard } from 'react-native';

import { AuthError, type AuthErrorCode } from '@/features/auth/domain/errors';

import { maya, renderAuthRoutes } from './authRoutes';

// The first render loads expo-router, which is slow on a cold cache.
jest.setTimeout(30_000);

let announce: jest.SpyInstance;
beforeEach(() => {
  announce = jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => undefined);
});
afterEach(() => {
  jest.restoreAllMocks();
});

const rania = { firstName: 'Rania', email: 'rania@example.com', password: 'manoushe-2026' };

async function fill(values: { firstName: string; email: string; password: string }) {
  await fireEvent.changeText(screen.getByLabelText('First name'), values.firstName);
  await fireEvent.changeText(screen.getByLabelText('Email'), values.email);
  await fireEvent.changeText(screen.getByLabelText('Password'), values.password);
}

async function pressCreate() {
  await fireEvent.press(screen.getByRole('button', { name: 'Create account' }));
}

describe('SignUpScreen', () => {
  it('shows the approved layout with the gender choice and no Apple button', async () => {
    await renderAuthRoutes('/sign-up');
    expect(screen.getByTestId('paper-creased')).toBeTruthy();
    expect(screen.getByLabelText('Fatourati')).toBeTruthy();
    expect(screen.getByRole('header', { name: 'Create account' })).toBeTruthy();
    expect(screen.getByText('Keep every receipt in one place, in dollars and pounds.')).toBeTruthy();
    // Shown under the line; VoiceOver reads it as the field's hint instead, so it is not read twice.
    expect(screen.getByText('At least 8 characters', { includeHiddenElements: true })).toBeTruthy();
    expect(screen.getAllByRole('radio').map((radio) => radio.props.accessibilityLabel)).toEqual([
      'Female',
      'Male',
      'Prefer not to say',
    ]);
    expect(screen.getByText('Already have an account?')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy();
    expect(screen.queryByText(/apple/i)).toBeNull();
  });

  it('sets up the fields for the keyboard and a new password', async () => {
    await renderAuthRoutes('/sign-up');
    expect(screen.getByLabelText('First name').props).toMatchObject({
      textContentType: 'givenName',
      autoComplete: 'given-name',
      autoCapitalize: 'words',
      returnKeyType: 'next',
    });
    expect(screen.getByLabelText('Email').props).toMatchObject({
      keyboardType: 'email-address',
      textContentType: 'username',
      autoCapitalize: 'none',
      returnKeyType: 'next',
    });
    expect(screen.getByLabelText('Password').props).toMatchObject({
      secureTextEntry: true,
      textContentType: 'newPassword',
      autoComplete: 'new-password',
      passwordRules: 'minlength: 8; maxlength: 128;',
      accessibilityHint: 'At least 8 characters',
      returnKeyType: 'done',
    });
  });

  it('checks every field when the button is pressed, and does not call the backend', async () => {
    const { repository } = await renderAuthRoutes('/sign-up');
    await fill({ firstName: '   ', email: 'rania@example', password: 'short' });
    expect(screen.queryByText('Enter your first name.')).toBeNull();

    await pressCreate();
    expect(screen.getByText('Enter your first name.')).toBeTruthy();
    expect(screen.getByText('Enter an email like name@example.com.')).toBeTruthy();
    expect(screen.getByText('Use at least 8 characters.')).toBeTruthy();
    // The message takes the hint's place.
    expect(screen.queryByText('At least 8 characters', { includeHiddenElements: true })).toBeNull();
    expect(screen.getByText('Choose Female, Male or Prefer not to say.')).toBeTruthy();
    expect(announce).toHaveBeenCalledWith('Enter your first name.');
    expect(repository.calls).toEqual([]);
  });

  it('asks only for the gender when everything else is right, and closes the keyboard to show it', async () => {
    const dismiss = jest.spyOn(Keyboard, 'dismiss');
    const { repository } = await renderAuthRoutes('/sign-up');
    await fill(rania);
    await pressCreate();
    expect(screen.getByText('Choose Female, Male or Prefer not to say.')).toBeTruthy();
    expect(announce).toHaveBeenCalledWith('Choose Female, Male or Prefer not to say.');
    expect(dismiss).toHaveBeenCalled();
    expect(repository.calls).toEqual([]);

    await fireEvent.press(screen.getByRole('radio', { name: 'Prefer not to say' }));
    expect(screen.queryByText('Choose Female, Male or Prefer not to say.')).toBeNull();
  });

  it('refuses names and passwords over the backend limits', async () => {
    await renderAuthRoutes('/sign-up');
    await fill({ firstName: 'a'.repeat(51), email: rania.email, password: 'x'.repeat(129) });
    await pressCreate();
    expect(screen.getAllByText('Use at most 50 characters.')).toHaveLength(1);
    expect(screen.getByText('Use at most 128 characters.')).toBeTruthy();
  });

  it('creates the account with trimmed values and the chosen gender, then signs in', async () => {
    const { router, repository } = await renderAuthRoutes('/sign-up');
    await fill({ firstName: '  Rania ', email: ` ${rania.email}`, password: rania.password });
    await fireEvent.press(screen.getByRole('radio', { name: 'Female' }));
    await pressCreate();
    await waitFor(() => expect(screen.getByText('Signed in as Rania')).toBeTruthy());
    expect(router.getPathname()).toBe('/home');
    expect(repository.calls).toEqual([`register ${rania.email}`, `login ${rania.email}`]);
    expect(repository.accounts.get(rania.email)?.user).toMatchObject({ firstName: 'Rania', gender: 'female' });
  });

  it('creates the account from the return key once a gender is chosen', async () => {
    await renderAuthRoutes('/sign-up');
    await fill(rania);
    await fireEvent.press(screen.getByRole('radio', { name: 'Male' }));
    expect(screen.getByLabelText('Password').props.returnKeyType).toBe('go');
    await fireEvent(screen.getByLabelText('Password'), 'submitEditing');
    await waitFor(() => expect(screen.getByText('Signed in as Rania')).toBeTruthy());
  });

  it('says under the email when an account already uses it', async () => {
    await renderAuthRoutes('/sign-up');
    await fill({ firstName: 'Maya', email: maya.email, password: maya.password });
    await fireEvent.press(screen.getByRole('radio', { name: 'Female' }));
    await pressCreate();
    expect(await screen.findByText('An account already uses this email.')).toBeTruthy();
    expect(screen.getByLabelText('Email').props.accessibilityHint).toBe('An account already uses this email.');
    expect(announce).toHaveBeenCalledWith('An account already uses this email.');
    expect(screen.getByRole('button', { name: 'Create account' }).props.accessibilityState).toMatchObject({
      busy: false,
    });
  });

  it.each<[AuthErrorCode, string, string]>([
    ['network', 'Could not reach the server: Network request failed', "Can't reach Fatourati. Check your connection and try again."],
    ['unexpected', 'The request failed (500)', 'Fatourati could not finish this. Try again in a moment.'],
    ['invalid-details', 'Password must be at least 8 characters', 'Password must be at least 8 characters.'],
  ])('explains a %s failure above the button', async (code, detail, message) => {
    const { repository } = await renderAuthRoutes('/sign-up');
    jest.spyOn(repository, 'register').mockRejectedValue(new AuthError(code, detail));
    await fill(rania);
    await fireEvent.press(screen.getByRole('radio', { name: 'Male' }));
    await pressCreate();
    expect(await screen.findByText(message)).toBeTruthy();
    expect(announce).toHaveBeenCalledWith(message);
  });

  it('goes back to sign in from the link, without stacking another sign in', async () => {
    const { router } = await renderAuthRoutes('/sign-in');
    await fireEvent.press(screen.getByRole('link', { name: 'Create an account' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-up'));
    expect(testRouter.canGoBack()).toBe(true);

    await fireEvent.press(screen.getByRole('link', { name: 'Sign in' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
    expect(testRouter.canGoBack()).toBe(false);
  });

  it('replaces itself with sign in when it was opened directly', async () => {
    const { router } = await renderAuthRoutes('/sign-up');
    await fireEvent.press(screen.getByRole('link', { name: 'Sign in' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
    expect(screen.getByRole('header', { name: 'Sign in' })).toBeTruthy();
  });
});
