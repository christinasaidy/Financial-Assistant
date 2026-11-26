/**
 * The launch route (app/index.tsx) in the real router: the launch screen while the saved session is
 * checked, then sign in. tests/routes.test.tsx covers where each status leads.
 */
import { join } from 'node:path';

import { act, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import * as SecureStore from 'expo-secure-store';

const APP_DIR = join(__dirname, '../../../app');

// The first render loads every route file, which is slow on a cold cache.
jest.setTimeout(30_000);

beforeEach(() => {
  process.env.EXPO_PUBLIC_API_URL = 'http://192.168.1.23:8000';
});

afterEach(() => {
  jest.restoreAllMocks();
});

it('shows the launch screen until the saved session is checked, then goes to sign in', async () => {
  let finishReading: (value: string | null) => void = () => {};
  jest
    .spyOn(SecureStore, 'getItemAsync')
    .mockImplementation(() => new Promise((resolve) => (finishReading = resolve)));

  const router = await renderRouter(APP_DIR, { initialUrl: '/' });
  expect(router.getPathname()).toBe('/');
  expect(screen.getByTestId('launch-screen')).toBeTruthy();
  expect(screen.getByRole('header', { name: 'Fatourati' })).toBeTruthy();

  await act(async () => finishReading(null));
  // The session is known, but the launch screen stays for its 1.5 s.
  expect(router.getPathname()).toBe('/');
  expect(screen.getByTestId('launch-screen')).toBeTruthy();
  await waitFor(() => expect(router.getPathname()).toBe('/sign-in'), { timeout: 5_000 });
  expect(screen.queryByTestId('launch-screen')).toBeNull();
});
