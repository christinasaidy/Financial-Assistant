/**
 * Settings with a fake signed-in session, inside expo-router's test router, so Back can be checked as in the
 * app.
 */
import { router as appRouter } from 'expo-router';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Text } from 'react-native';

import { AuthService } from '@/features/auth/application/authService';
import { SessionProvider } from '@/features/auth/ui/SessionProvider';
import { SettingsScreen } from '@/features/settings/ui/SettingsScreen';

import { christina, FakeAuthRepository, FakeTokenStore } from '../auth/fakes';

jest.setTimeout(30_000);

function signedIn() {
  const repository = new FakeAuthRepository();
  const tokens = new FakeTokenStore();
  repository.validTokens.set('jwt', christina);
  tokens.saved = { accessToken: 'jwt', expiresAt: Date.now() + 3_600_000, user: christina };
  return new AuthService(repository, tokens);
}

async function renderSettings(auth = signedIn()) {
  const wrap = (element: React.ReactElement) => {
    function Wrapped() {
      return <SessionProvider authService={auth}>{element}</SessionProvider>;
    }
    return Wrapped;
  };
  const router = await renderRouter({ index: wrap(<Text>Home</Text>), settings: wrap(<SettingsScreen />) }, { initialUrl: '/' });
  await act(() => appRouter.push('/settings'));
  await waitFor(() => expect(screen.getByRole('header', { name: 'Settings' })).toBeTruthy());
  return { router, auth };
}

describe('Settings', () => {
  it('shows the account on a creased sheet: name and email', async () => {
    await renderSettings();
    expect(screen.getByText('Account')).toBeTruthy();
    expect(screen.getByText(christina.firstName as string)).toBeTruthy();
    expect(screen.getByTestId('settings-email').props.children).toBe(christina.email);
  });

  it('has no appearance setting: the app is light only (D044)', async () => {
    await renderSettings();
    expect(screen.queryByText('Appearance')).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('signs out', async () => {
    const { auth } = await renderSettings();
    await fireEvent.press(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(auth.accessToken()).toBeNull());
  });

  it('goes back with Back', async () => {
    const { router } = await renderSettings();
    await fireEvent.press(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(router.getPathname()).toBe('/'));
  });
});
