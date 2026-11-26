import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { AccessibilityInfo, StyleSheet } from 'react-native';

import { AuthService } from '@/features/auth/application/authService';
import { AuthError, type AuthErrorCode } from '@/features/auth/domain/errors';
import { SessionProvider } from '@/features/auth/ui/SessionProvider';
import { SignInScreen } from '@/features/auth/ui/SignInScreen';
import { colors } from '@/shared/theme';

import { maya, renderAuthRoutes } from './authRoutes';
import { FakeAuthRepository, FakeTokenStore } from './fakes';

// The first render loads expo-router, which is slow on a cold cache.
jest.setTimeout(30_000);

let announce: jest.SpyInstance;
beforeEach(() => {
  announce = jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => undefined);
});
afterEach(() => {
  jest.restoreAllMocks();
});

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

async function fill(email: string, password: string) {
  await fireEvent.changeText(screen.getByLabelText('Email'), email);
  await fireEvent.changeText(screen.getByLabelText('Password'), password);
}

async function pressSignIn() {
  await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
}

describe('SignInScreen', () => {
  it('shows the approved layout: wordmark, title, sentence, two fields, the button and the link', async () => {
    await renderAuthRoutes('/sign-in');
    expect(screen.getByLabelText('Fatourati')).toBeTruthy();
    // The eyebrow and the button both read "Sign in".
    expect(screen.getAllByText('Sign in')).toHaveLength(2);
    expect(screen.getByRole('header', { name: 'Let’s flatten these out.' })).toBeTruthy();
    expect(screen.getByText('Welcome back. Your receipts are where you left them.')).toBeTruthy();
    expect(screen.getByText('New to Fatourati?')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Create an account' })).toBeTruthy();
    // Left out until the backend supports them (D044).
    expect(screen.queryByText(/apple/i)).toBeNull();
    expect(screen.queryByText(/forgot/i)).toBeNull();
  });

  it('sets up the fields for the keyboard and password autofill', async () => {
    await renderAuthRoutes('/sign-in');
    expect(screen.getByLabelText('Email').props).toMatchObject({
      keyboardType: 'email-address',
      textContentType: 'username',
      autoComplete: 'email',
      autoCapitalize: 'none',
      autoCorrect: false,
      returnKeyType: 'next',
      placeholder: 'name@example.com',
    });
    expect(screen.getByLabelText('Password').props).toMatchObject({
      secureTextEntry: true,
      textContentType: 'password',
      autoComplete: 'current-password',
      returnKeyType: 'go',
    });
  });

  it('shows and hides the password', async () => {
    await renderAuthRoutes('/sign-in');
    await fireEvent.press(screen.getByRole('button', { name: 'Show password' }));
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(false);
    await fireEvent.press(screen.getByRole('button', { name: 'Hide password' }));
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);
  });

  it('checks the fields only when the button is pressed, and does not call the backend', async () => {
    const { repository } = await renderAuthRoutes('/sign-in');
    await fireEvent.changeText(screen.getByLabelText('Email'), 'maya');
    expect(screen.queryByText('Enter an email like name@example.com.')).toBeNull();

    await pressSignIn();
    expect(screen.getByText('Enter an email like name@example.com.')).toBeTruthy();
    expect(screen.getByText('Enter your password.')).toBeTruthy();
    expect(flat(screen.getByText('Enter your password.').props.style).color).toBe(colors.redText);
    expect(announce).toHaveBeenCalledWith('Enter an email like name@example.com.');
    expect(repository.calls).toEqual([]);
  });

  it('asks for the email when it is empty', async () => {
    await renderAuthRoutes('/sign-in');
    await pressSignIn();
    expect(screen.getByText('Enter your email.')).toBeTruthy();
  });

  it('removes a field message as soon as that field is edited', async () => {
    await renderAuthRoutes('/sign-in');
    await pressSignIn();
    await fireEvent.changeText(screen.getByLabelText('Email'), 'm');
    expect(screen.queryByText('Enter your email.')).toBeNull();
    expect(screen.getByText('Enter your password.')).toBeTruthy();
  });

  it('signs in and lets the session move to the signed-in routes', async () => {
    const { router, repository } = await renderAuthRoutes('/sign-in');
    await fill(`  ${maya.email} `, maya.password);
    await pressSignIn();
    await waitFor(() => expect(screen.getByText('Signed in as Maya')).toBeTruthy());
    expect(router.getPathname()).toBe('/home');
    expect(repository.calls).toEqual([`login ${maya.email}`]);
  });

  it('signs in from the return key of the password field', async () => {
    await renderAuthRoutes('/sign-in');
    await fill(maya.email, maya.password);
    await fireEvent(screen.getByLabelText('Password'), 'submitEditing');
    await waitFor(() => expect(screen.getByText('Signed in as Maya')).toBeTruthy());
  });

  it('is busy while signing in and ignores more presses', async () => {
    const { repository } = await renderAuthRoutes('/sign-in');
    let finish: () => void = () => undefined;
    const login = repository.login.bind(repository);
    jest.spyOn(repository, 'login').mockImplementation(
      (email, password) =>
        new Promise((resolve, reject) => {
          finish = () => void login(email, password).then(resolve, reject);
        }),
    );
    await fill(maya.email, maya.password);
    await pressSignIn();
    const button = screen.getByRole('button', { name: 'Sign in' });
    expect(button.props.accessibilityState).toMatchObject({ busy: true, disabled: true });
    await fireEvent(screen.getByLabelText('Password'), 'submitEditing');
    expect(repository.login).toHaveBeenCalledTimes(1);

    await act(async () => finish());
    await waitFor(() => expect(screen.getByText('Signed in as Maya')).toBeTruthy());
  });

  it('is ready again after signing out when the screen was kept alive under the tabs (as iOS does)', async () => {
    const repository = new FakeAuthRepository();
    await repository.register({ ...maya });
    const service = new AuthService(repository, new FakeTokenStore());
    // No guard: the screen stays mounted through the sign-in, like the native stack keeps it on the iPhone.
    function Layout() {
      return (
        <SessionProvider authService={service}>
          <SignInScreen />
        </SessionProvider>
      );
    }
    await renderRouter({ _layout: Layout, index: () => null }, { initialUrl: '/' });

    await fill(maya.email, maya.password);
    await pressSignIn();
    await waitFor(() => expect(service.accessToken()).not.toBeNull());
    expect(screen.getByRole('button', { name: 'Sign in' }).props.accessibilityState).toMatchObject({ busy: true });

    await act(() => service.signOut());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sign in' }).props.accessibilityState).toMatchObject({
        busy: false,
        disabled: false,
      }),
    );
    expect(screen.getByLabelText('Password').props.value).toBe('');

    await fill(maya.email, maya.password);
    await pressSignIn();
    await waitFor(() => expect(service.accessToken()).not.toBeNull());
    expect(repository.calls.filter((call) => call.startsWith('login'))).toHaveLength(2);
  });

  it('says the email or password is wrong, without saying which', async () => {
    await renderAuthRoutes('/sign-in');
    await fill(maya.email, 'not-her-password');
    await pressSignIn();
    expect(await screen.findByText('Wrong email or password.')).toBeTruthy();
    expect(announce).toHaveBeenCalledWith('Wrong email or password.');
    expect(screen.getByRole('button', { name: 'Sign in' }).props.accessibilityState).toMatchObject({ busy: false });

    // Editing clears the message; the next try works.
    await fireEvent.changeText(screen.getByLabelText('Password'), maya.password);
    expect(screen.queryByText('Wrong email or password.')).toBeNull();
    await pressSignIn();
    await waitFor(() => expect(screen.getByText('Signed in as Maya')).toBeTruthy());
  });

  it.each<[AuthErrorCode, string, string]>([
    ['network', 'Could not reach the server: Network request failed', "Can't reach Fatourati. Check your connection and try again."],
    ['unexpected', 'The request failed (500)', 'Fatourati could not finish this. Try again in a moment.'],
    ['invalid-details', 'Enter a valid email address', 'Enter a valid email address.'],
  ])('explains a %s failure', async (code, detail, message) => {
    const { repository } = await renderAuthRoutes('/sign-in');
    jest.spyOn(repository, 'login').mockRejectedValue(new AuthError(code, detail));
    await fill(maya.email, maya.password);
    await pressSignIn();
    expect(await screen.findByText(message)).toBeTruthy();
    expect(announce).toHaveBeenCalledWith(message);
  });

  it('goes to create account from the link', async () => {
    const { router } = await renderAuthRoutes('/sign-in');
    await fireEvent.press(screen.getByRole('link', { name: 'Create an account' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-up'));
    expect(screen.getByRole('header', { name: 'Start a fresh invoice.' })).toBeTruthy();
  });
});
