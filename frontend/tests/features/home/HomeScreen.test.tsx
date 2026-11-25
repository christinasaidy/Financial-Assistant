/**
 * The Home screen with a fake Home backend and a fake signed-in session, inside expo-router's test router
 * (so the tab links and the reload on focus work as in the app). Run in light and in dark.
 */
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { StyleSheet, Text } from 'react-native';

import { AuthService } from '@/features/auth/application/authService';
import { SessionProvider } from '@/features/auth/ui/SessionProvider';
import { HomeService } from '@/features/home/application/homeService';
import { HomeScreen } from '@/features/home/ui/HomeScreen';
import { colorTokens, ThemeOverride, type ColorScheme } from '@/shared/theme';

import { christina, FakeAuthRepository, FakeTokenStore } from '../auth/fakes';
import { abouRami, emptyMonth, FakeHomeRepository, november, spinneys, transport, zaatar } from './fakes';

jest.setTimeout(30_000);

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

function signedIn(firstName: string | null = 'Christina') {
  const repository = new FakeAuthRepository();
  const tokens = new FakeTokenStore();
  const user = { ...christina, firstName };
  repository.validTokens.set('jwt', user);
  tokens.saved = { accessToken: 'jwt', expiresAt: Date.now() + 3_600_000, user };
  return new AuthService(repository, tokens);
}

async function renderHome(scheme: ColorScheme, home: FakeHomeRepository, auth = signedIn()) {
  const service = new HomeService(home);
  const Home = () => (
    <ThemeOverride scheme={scheme}>
      <SessionProvider authService={auth}>
        <HomeScreen service={service} />
      </SessionProvider>
    </ThemeOverride>
  );
  const router = await renderRouter(
    {
      index: Home,
      budgets: () => <Text>Budgets tab</Text>,
      scan: () => <Text>Scan tab</Text>,
      settings: () => <Text>Settings screen</Text>,
    },
    { initialUrl: '/' },
  );
  return router;
}

describe.each<ColorScheme>(['light', 'dark'])('Home in %s', (scheme) => {
  const color = (token: keyof typeof colorTokens) => colorTokens[token][scheme];

  it('shows the month, the three budgets closest to their limit and the newest receipts', async () => {
    const home = new FakeHomeRepository();
    home.receiptList = [spinneys, zaatar, abouRami];
    await renderHome(scheme, home);

    await waitFor(() => expect(screen.getByText('$447.80')).toBeTruthy());
    expect(screen.getByTestId('paper-plain')).toBeTruthy();
    expect(screen.getByLabelText('Fatourati')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeTruthy();
    expect(screen.getByText('Hello, Christina')).toBeTruthy();
    expect(screen.getByText('This month · November')).toBeTruthy();
    expect(screen.getByText('$412.60 + 3,150,000 LBP at 89,500 LBP per $')).toBeTruthy();

    // Budgets, closest first, with the state in words in its colour.
    expect(screen.getByRole('link', { name: 'See all' })).toBeTruthy();
    expect(screen.getByText('$63.00 / $60')).toBeTruthy();
    const reached = screen.getByText('Limit reached · 105%');
    expect(flat(reached.props.style)).toMatchObject({ color: color('limit-reached'), textTransform: 'uppercase' });
    expect(flat(screen.getByText('Near limit · 89%').props.style).color).toBe(color('near-limit'));
    expect(screen.getByText('$186.40 / $250')).toBeTruthy();
    expect(screen.queryByText(/Groceries.*%/)).toBeNull();
    expect(flat(screen.getByTestId(`home-budget-bar-${transport.categoryId}`).props.style)).toMatchObject({
      width: '100%',
      backgroundColor: color('limit-reached'),
    });
    expect(flat(screen.getByTestId('home-budget-bar-3').props.style)).toMatchObject({
      width: '74.6%',
      backgroundColor: color('ink'),
    });

    // Recent, newest first.
    expect(screen.getByText('Spinneys Achrafieh')).toBeTruthy();
    expect(screen.getByText('$38.40')).toBeTruthy();
    expect(screen.getByText('18/11/2026 · 18:42 · 9 items')).toBeTruthy();
    expect(screen.getByText('450,000 LBP')).toBeTruthy();
    expect(screen.getByText('17/11/2026 · 13:05 · 2 items')).toBeTruthy();
    expect(screen.getByText('Abou Rami')).toBeTruthy();

    // No empty-state text when there is data.
    expect(screen.queryByText('No receipts yet this month')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Scan a receipt' })).toBeNull();
  });

  it('before any receipts: $0.00, the scan prompt and what Budgets and Recent will show', async () => {
    const home = new FakeHomeRepository();
    home.spending = emptyMonth;
    home.budgetList = [];
    home.receiptList = [];
    await renderHome(scheme, home);

    await waitFor(() => expect(screen.getByText('$0.00')).toBeTruthy());
    expect(screen.getByText('No receipts yet this month')).toBeTruthy();
    expect(
      screen.getByText(
        'Take a photo of a receipt. Fatourati reads the shop, the items and the total, in dollars or pounds.',
      ),
    ).toBeTruthy();
    const scan = screen.getByRole('button', { name: 'Scan a receipt' });
    expect(flat(scan.props.style).backgroundColor).toBe(color('primary'));
    const budgetsSentence = screen.getByText(
      'Set a monthly limit for groceries, fuel or eating out, and see how close you are.',
    );
    expect(flat(budgetsSentence.props.style).color).toBe(color('ink-2'));
    expect(flat(screen.getByText('Set a budget').props.style).color).toBe(color('primary'));
    expect(screen.queryByRole('link', { name: 'See all' })).toBeNull();
    expect(screen.getByText('Receipts you scan show up here, newest first.')).toBeTruthy();
  });

  it('shows each empty part on its own: receipts but no budgets', async () => {
    const home = new FakeHomeRepository();
    home.budgetList = [];
    await renderHome(scheme, home);

    await waitFor(() => expect(screen.getByText('Spinneys Achrafieh')).toBeTruthy());
    expect(screen.getByText('$447.80')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Set a budget' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Scan a receipt' })).toBeNull();
    expect(screen.queryByText('Receipts you scan show up here, newest first.')).toBeNull();
  });

  it('shows each empty part on its own: budgets and older receipts, nothing this month', async () => {
    const home = new FakeHomeRepository();
    home.spending = emptyMonth;
    await renderHome(scheme, home);

    await waitFor(() => expect(screen.getByText('No receipts yet this month')).toBeTruthy());
    expect(screen.getByRole('button', { name: 'Scan a receipt' })).toBeTruthy();
    expect(screen.getByText('Limit reached · 105%')).toBeTruthy();
    expect(screen.getByText('Spinneys Achrafieh')).toBeTruthy();
  });
});

describe('Home', () => {
  it('says just Hello for an account with no first name', async () => {
    await renderHome('light', new FakeHomeRepository(), signedIn(null));
    await waitFor(() => expect(screen.getByText('$447.80')).toBeTruthy());
    expect(screen.getByText('Hello')).toBeTruthy();
  });

  it('shows Loading… under the greeting until the figures arrive', async () => {
    const home = new FakeHomeRepository();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const original = home.monthSpending.bind(home);
    home.monthSpending = async (month) => {
      await gate;
      return original(month);
    };
    await renderHome('light', home);

    expect(screen.getByText('Loading…')).toBeTruthy();
    await act(async () => release());
    await waitFor(() => expect(screen.getByText('$447.80')).toBeTruthy());
    expect(screen.queryByText('Loading…')).toBeNull();
  });

  it('says why it could not load, and loads on Try again', async () => {
    const home = new FakeHomeRepository();
    home.offline = true;
    await renderHome('light', home);

    await waitFor(() => expect(screen.getByTestId('home-error')).toBeTruthy());
    expect(
      screen.getByText(
        'Fatourati could not reach the server, so this month’s spending is not shown. Check the connection.',
      ),
    ).toBeTruthy();
    expect(screen.queryByText('$0.00')).toBeNull();

    home.offline = false;
    await fireEvent.press(screen.getByRole('link', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByText('$447.80')).toBeTruthy());
    expect(screen.queryByTestId('home-error')).toBeNull();
  });

  it('reloads on pull-to-refresh, keeping the figures if the reload fails', async () => {
    const home = new FakeHomeRepository();
    await renderHome('light', home);
    await waitFor(() => expect(screen.getByText('$447.80')).toBeTruthy());

    home.spending = { ...november, total: '460.00' };
    const refresh = () => screen.getByTestId('home-scroll').props.refreshControl.props.onRefresh();
    await act(async () => refresh());
    await waitFor(() => expect(screen.getByText('$460.00')).toBeTruthy());

    home.offline = true;
    await act(async () => refresh());
    await waitFor(() => expect(screen.getByTestId('home-error')).toBeTruthy());
    expect(screen.getByText('$460.00')).toBeTruthy();
  });

  it('opens the Budgets tab from See all', async () => {
    const router = await renderHome('light', new FakeHomeRepository());
    await waitFor(() => expect(screen.getByText('$447.80')).toBeTruthy());
    await fireEvent.press(screen.getByRole('link', { name: 'See all' }));
    await waitFor(() => expect(router.getPathname()).toBe('/budgets'));
  });

  it('opens the Scan tab from the main button', async () => {
    const home = new FakeHomeRepository();
    home.spending = emptyMonth;
    const router = await renderHome('light', home);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Scan a receipt' })).toBeTruthy());
    await fireEvent.press(screen.getByRole('button', { name: 'Scan a receipt' }));
    await waitFor(() => expect(router.getPathname()).toBe('/scan'));
  });

  it('opens the Budgets tab from Set a budget', async () => {
    const home = new FakeHomeRepository();
    home.budgetList = [];
    const router = await renderHome('light', home);
    await waitFor(() => expect(screen.getByRole('link', { name: 'Set a budget' })).toBeTruthy());
    await fireEvent.press(screen.getByRole('link', { name: 'Set a budget' }));
    await waitFor(() => expect(router.getPathname()).toBe('/budgets'));
  });

  it('opens settings from the gear, and has no sign out of its own (it moved to settings, D043)', async () => {
    const router = await renderHome('light', new FakeHomeRepository());
    await waitFor(() => expect(screen.getByText('Hello, Christina')).toBeTruthy());
    expect(screen.queryByRole('link', { name: 'Sign out' })).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Settings' }));
    await waitFor(() => expect(router.getPathname()).toBe('/settings'));
  });
});
