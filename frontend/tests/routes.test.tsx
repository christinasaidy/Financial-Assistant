/**
 * The routing skeleton in app/, run through expo-router's test renderer with the real container
 * (Keychain mocked in jest.setup.ts, fetch mocked here).
 */
import { join } from 'node:path';

import { renderRouter, screen, waitFor } from 'expo-router/testing-library';
import * as SecureStore from 'expo-secure-store';

import { SESSION_KEY } from '@/shared/storage/tokenStore';

const APP_DIR = join(__dirname, '../app');

// The first render loads every route file, which is slow on a cold cache.
jest.setTimeout(30_000);

beforeEach(async () => {
  process.env.EXPO_PUBLIC_API_URL = 'http://192.168.1.23:8000';
  await SecureStore.deleteItemAsync(SESSION_KEY);
});

afterEach(() => {
  jest.restoreAllMocks();
});

it('sends a signed-out user from the launch route to sign in', async () => {
  const router = await renderRouter(APP_DIR, { initialUrl: '/' });
  await waitFor(() => expect(router.getPathname()).toBe('/sign-in'), { timeout: 5_000 });
  expect(screen.getByRole('header', { name: 'Let’s flatten these out.' })).toBeTruthy();
});

it('sends a signed-in user to Home, with the five tabs', async () => {
  const user = { id: 7, email: 'christina@example.com', first_name: 'Christina', gender: 'female' };
  await SecureStore.setItemAsync(
    SESSION_KEY,
    JSON.stringify({
      accessToken: 'jwt',
      expiresAt: Date.now() + 3_600_000,
      user: { id: 7, email: user.email, firstName: 'Christina', gender: 'female' },
    }),
  );
  jest.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(user),
  } as Response);

  const router = await renderRouter(APP_DIR, { initialUrl: '/' });
  await waitFor(() => expect(screen.getByTestId('home-settings')).toBeTruthy(), { timeout: 5_000 });
  expect(router.getSegments()).toEqual(['(tabs)']);
  expect(screen.getAllByRole('tab').map((tab) => tab.props.accessibilityLabel)).toEqual([
    'Home',
    'Receipts',
    'Scan a receipt',
    'Budgets',
    'Assistant',
  ]);
});
