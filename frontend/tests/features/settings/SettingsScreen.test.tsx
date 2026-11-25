/**
 * Settings with a fake appearance store and a fake signed-in session, inside expo-router's test router, so
 * Back and the theme change can be checked as in the app.
 */
import { router as appRouter } from 'expo-router';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { StyleSheet, Text } from 'react-native';

import { AuthService } from '@/features/auth/application/authService';
import { SessionProvider } from '@/features/auth/ui/SessionProvider';
import { SettingsService } from '@/features/settings/application/settingsService';
import { AppearanceProvider } from '@/features/settings/ui/AppearanceProvider';
import { SettingsScreen } from '@/features/settings/ui/SettingsScreen';
import { colorTokens, useTheme } from '@/shared/theme';

import { christina, FakeAuthRepository, FakeTokenStore } from '../auth/fakes';
import { FakeAppearanceStore } from './fakes';

jest.setTimeout(30_000);

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

function signedIn() {
  const repository = new FakeAuthRepository();
  const tokens = new FakeTokenStore();
  repository.validTokens.set('jwt', christina);
  tokens.saved = { accessToken: 'jwt', expiresAt: Date.now() + 3_600_000, user: christina };
  return new AuthService(repository, tokens);
}

/** Shows which theme the app is in, the way any screen reads it. */
function SchemeProbe() {
  const { scheme } = useTheme();
  return <Text testID="scheme">{scheme}</Text>;
}

async function renderSettings(store = new FakeAppearanceStore(), auth = signedIn()) {
  const settings = new SettingsService(store);
  const wrap = (screenElement: React.ReactElement) => {
    function Wrapped() {
      return (
        <SessionProvider authService={auth}>
          <AppearanceProvider service={settings}>
            <SchemeProbe />
            {screenElement}
          </AppearanceProvider>
        </SessionProvider>
      );
    }
    return Wrapped;
  };
  const router = await renderRouter(
    { index: wrap(<Text>Home</Text>), settings: wrap(<SettingsScreen />) },
    { initialUrl: '/' },
  );
  await act(() => appRouter.push('/settings'));
  await waitFor(() => expect(screen.getByRole('header', { name: 'Settings' })).toBeTruthy());
  return { router, store, auth };
}

describe('Settings', () => {
  it('starts on Phone and switches the whole app to the chosen theme, saving it', async () => {
    const { store } = await renderSettings();
    expect(screen.getByRole('radio', { name: 'Phone' }).props.accessibilityState).toMatchObject({ checked: true });

    await fireEvent.press(screen.getByRole('radio', { name: 'Dark' }));
    await waitFor(() => expect(screen.getAllByTestId('scheme').every((probe) => probe.props.children === 'dark')).toBe(true));
    expect(store.saved).toBe('dark');
    expect(flat(screen.getByTestId('paper-plain').props.style).backgroundColor).toBe(colorTokens.paper.dark);
    expect(screen.getByRole('radio', { name: 'Dark' }).props.accessibilityState).toMatchObject({ checked: true });

    await fireEvent.press(screen.getByRole('radio', { name: 'Light' }));
    await waitFor(() => expect(flat(screen.getByTestId('paper-plain').props.style).backgroundColor).toBe(colorTokens.paper.light));
    expect(store.saved).toBe('light');
  });

  it('opens on the saved choice', async () => {
    const store = new FakeAppearanceStore();
    store.saved = 'dark';
    await renderSettings(store);
    await waitFor(() =>
      expect(screen.getByRole('radio', { name: 'Dark' }).props.accessibilityState).toMatchObject({ checked: true }),
    );
  });

  it('shows the account and signs out', async () => {
    const { auth } = await renderSettings();
    expect(screen.getByTestId('settings-email').props.children).toBe(christina.email);
    await fireEvent.press(screen.getByRole('link', { name: 'Sign out' }));
    await waitFor(() => expect(auth.accessToken()).toBeNull());
  });

  it('goes back with Back', async () => {
    const { router } = await renderSettings();
    await fireEvent.press(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(router.getPathname()).toBe('/'));
  });
});
