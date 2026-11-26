/**
 * Sign out from settings and sign in again, through the real app/ routes and container (Keychain mocked in
 * jest.setup.ts, fetch mocked here). Its own file, because the container is built once per file and keeps
 * the session of earlier tests.
 */
import { join } from 'node:path';

import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

const APP_DIR = join(__dirname, '../app');
jest.setTimeout(60_000);

beforeEach(() => {
  process.env.EXPO_PUBLIC_API_URL = 'http://192.168.1.23:8000';
});

afterEach(() => {
  jest.restoreAllMocks();
});

const christinaFromApi = { id: 7, email: 'christina@example.com', first_name: 'Christina', gender: 'female' };

function replyWith(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) } as Response;
}

it('opens settings from the wordmark, signs out there, and signs in again', async () => {
  const fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes('/auth/login')) return replyWith({ access_token: 'jwt', token_type: 'bearer', expires_in: 3600, user: christinaFromApi });
    if (url.includes('/auth/me')) return replyWith(christinaFromApi);
    if (url.includes('/spending/summary')) return replyWith({ month: '2026-11', currency: 'USD', total: '0', by_currency: [], rate: null });
    return replyWith([]);
  });

  const router = await renderRouter(APP_DIR, { initialUrl: '/' });
  await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));

  const signInOnce = async () => {
    await fireEvent.changeText(screen.getByLabelText('Email'), 'christina@example.com');
    await fireEvent.changeText(screen.getByLabelText('Password'), 'password123');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByTestId('home-settings')).toBeTruthy());
  };
  await signInOnce();

  await fireEvent.press(screen.getByTestId('home-settings'));
  await waitFor(() => expect(router.getPathname()).toBe('/settings'));
  await fireEvent.press(screen.getByRole('button', { name: 'Sign out' }));
  await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));

  const before = fetchMock.mock.calls.filter(([u]) => String(u).includes('/auth/login')).length;
  await fireEvent.changeText(screen.getByLabelText('Email'), 'christina@example.com');
  await fireEvent.changeText(screen.getByLabelText('Password'), 'password123');
  const button = screen.getByRole('button', { name: 'Sign in' });
  await fireEvent.press(button);
  await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/auth/login')).length).toBe(before + 1));
  await waitFor(() => expect(screen.getByTestId('home-settings')).toBeTruthy());
});
