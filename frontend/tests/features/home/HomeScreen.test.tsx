/**
 * The Home screen with a fake Home backend and a fake signed-in session, inside expo-router's test router
 * (so the links and the reload on focus work as in the app), against design/screens/03 and 04.
 */
import { act, fireEvent, renderRouter, screen, waitFor, within } from 'expo-router/testing-library';
import { StyleSheet, Text } from 'react-native';

import { AuthService } from '@/features/auth/application/authService';
import { SessionProvider } from '@/features/auth/ui/SessionProvider';
import { HomeService } from '@/features/home/application/homeService';
import { HomeScreen } from '@/features/home/ui/HomeScreen';
import { colors } from '@/shared/theme';
import { RouterTabBar, ScanHintProvider, appTabs } from '@/shared/ui';

import { christina, FakeAuthRepository, FakeTokenStore } from '../auth/fakes';
import { abouRami, emptyMonth, FakeHomeRepository, november, septemberReceipt, spinneys, zaatar } from './fakes';

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

async function renderHome(home: FakeHomeRepository, auth = signedIn()) {
  const service = new HomeService(home);
  const Home = () => (
    <SessionProvider authService={auth}>
      <ScanHintProvider>
        <HomeScreen service={service} />
        <Ring />
      </ScanHintProvider>
    </SessionProvider>
  );
  return renderRouter(
    {
      index: Home,
      budgets: () => <Text>Budgets tab</Text>,
      receipts: () => <Text>Receipts tab</Text>,
      assistant: () => <Text>Assistant tab</Text>,
      settings: () => <Text>Settings screen</Text>,
    },
    { initialUrl: '/' },
  );
}

/** The real tab bar, which reads Home's request for the ring around Scan. */
function Ring() {
  const props = {
    state: { index: 0, routes: appTabs.map((tab) => ({ key: tab.route, name: tab.route })) },
    emitter: { emit: () => ({ defaultPrevented: false }) },
    navigateToTab: () => undefined,
    insets: { top: 0, bottom: 0, left: 0, right: 0 },
  } as unknown as Parameters<typeof RouterTabBar>[0];
  return <RouterTabBar {...props} />;
}

async function loaded() {
  await waitFor(() => expect(screen.getByTestId('invoice-total')).toBeTruthy());
}

describe('Home with a month of receipts (design/screens/03-home.png)', () => {
  it('shows the invoice: number, month, billed to, total and the combined line', async () => {
    const home = new FakeHomeRepository();
    home.receiptList = [spinneys, zaatar, septemberReceipt];
    await renderHome(home);
    await loaded();

    expect(screen.getByText('Invoice Nº 0003')).toBeTruthy();
    expect(screen.getByText('Nov 2026')).toBeTruthy();
    expect(screen.getByText('Billed to Christina')).toBeTruthy();
    expect(screen.getByTestId('invoice-total').props.children).toBe('$447.80');
    expect(flat(screen.getByTestId('invoice-total').props.style).color).toBe(colors.ink);
    expect(screen.getByText('$412.60 + 3,150,000 LBP · 89,500')).toBeTruthy();
    expect(screen.getAllByText('$447.80')).toHaveLength(2);
    // Older months peek behind the invoice.
    const older = within(screen.getByTestId('older-months', { includeHiddenElements: true }));
    expect(older.getByText('Sep', { includeHiddenElements: true })).toBeTruthy();
    expect(older.getByText('Oct', { includeHiddenElements: true })).toBeTruthy();
  });

  it('fills the table: limits, spent, what is left, the over-budget row in red, and Everything else', async () => {
    await renderHome(new FakeHomeRepository());
    await loaded();

    expect(screen.getByText('Transport')).toBeTruthy();
    expect(screen.getByText('60')).toBeTruthy();
    expect(flat(screen.getByText('63.00').props.style).color).toBe(colors.red);
    expect(flat(screen.getByText('+3.00 over').props.style).color).toBe(colors.red);
    expect(flat(screen.getByTestId('budget-bar-1').props.style)).toMatchObject({ width: '100%', backgroundColor: colors.red });
    expect(screen.getByText('8.50 left')).toBeTruthy();
    expect(flat(screen.getByTestId('budget-bar-2').props.style)).toMatchObject({ width: '89.4%', backgroundColor: colors.ink });
    expect(screen.getByText('63.60 left')).toBeTruthy();
    expect(screen.getByText('Everything else')).toBeTruthy();
    expect(screen.getByText('126.90')).toBeTruthy();
  });

  it('lists the recent receipts with category, item count and dollars under pounds', async () => {
    await renderHome(new FakeHomeRepository());
    await loaded();
    expect(screen.getByText('Spinneys Achrafieh')).toBeTruthy();
    expect(screen.getByText('Groceries · 9 items')).toBeTruthy();
    expect(screen.getByText('$38.40')).toBeTruthy();
    expect(screen.getByText('450,000 LBP')).toBeTruthy();
    expect(screen.getByText('≈ $5.03')).toBeTruthy();
    expect(screen.getByText('Eating out · 2 items')).toBeTruthy();
  });

  it.each([
    ['the note', 'invoice-note', '/assistant'],
    ['See all', 'recent-see-all', '/receipts'],
    ['the wordmark', 'home-settings', '/settings'],
  ])('opens a screen from %s', async (_what, testID, path) => {
    const router = await renderHome(new FakeHomeRepository());
    await loaded();
    await fireEvent.press(screen.getByTestId(testID));
    await waitFor(() => expect(router.getPathname()).toBe(path));
  });

  it('does not ring Scan', async () => {
    await renderHome(new FakeHomeRepository());
    await loaded();
    expect(screen.queryByTestId('scan-ring')).toBeNull();
  });
});

describe('Home before anything (design/screens/04-home-empty.png)', () => {
  function blank() {
    const home = new FakeHomeRepository();
    home.spending = emptyMonth;
    home.budgetList = [];
    home.receiptList = [];
    return home;
  }

  it('is a blank invoice: Nº 0001, a grey $0.00, the sentence, blank rows and no older months', async () => {
    await renderHome(blank());
    await loaded();
    expect(screen.getByText('Invoice Nº 0001')).toBeTruthy();
    expect(flat(screen.getByTestId('invoice-total').props.style).color).toBe(colors.zeroAmount);
    expect(screen.getByText('A blank invoice. It fills itself in as you scan.')).toBeTruthy();
    expect(screen.getByLabelText('No budgets yet')).toBeTruthy();
    expect(screen.queryByText('Everything else')).toBeNull();
    expect(screen.queryByTestId('older-months', { includeHiddenElements: true })).toBeNull();
  });

  it('invites a first budget from the note and a first scan, and rings Scan', async () => {
    const router = await renderHome(blank());
    await loaded();
    expect(screen.getByText('Set your first monthly budget')).toBeTruthy();
    expect(screen.getByText('No receipts yet')).toBeTruthy();
    expect(screen.getByText('Tap Scan below to add your first one.')).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'See all' })).toBeNull();
    await waitFor(() => expect(screen.getByTestId('scan-ring')).toBeTruthy());

    await fireEvent.press(screen.getByTestId('invoice-note'));
    await waitFor(() => expect(router.getPathname()).toBe('/budgets'));
  });

  it('shows receipts from earlier months under a blank invoice', async () => {
    const home = blank();
    home.receiptList = [abouRami];
    await renderHome(home);
    await loaded();
    expect(screen.getByText('Abou Rami')).toBeTruthy();
  });
});

describe('Home loading and failing', () => {
  it('bills "you" for an account with no first name', async () => {
    await renderHome(new FakeHomeRepository(), signedIn(null));
    await loaded();
    expect(screen.getByText('Billed to you')).toBeTruthy();
  });

  it('shows a spinner until the figures arrive', async () => {
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
    await renderHome(home);

    expect(screen.getByLabelText('Loading')).toBeTruthy();
    await act(async () => release());
    await loaded();
    expect(screen.queryByLabelText('Loading')).toBeNull();
  });

  it('says why it could not load, and loads on Try again', async () => {
    const home = new FakeHomeRepository();
    home.offline = true;
    await renderHome(home);

    await waitFor(() => expect(screen.getByTestId('home-error')).toBeTruthy());
    expect(screen.getByText('Fatourati could not reach the server, so this month’s invoice is not shown. Check the connection.')).toBeTruthy();
    expect(screen.queryByTestId('invoice')).toBeNull();

    home.offline = false;
    await fireEvent.press(screen.getByRole('link', { name: 'Try again' }));
    await loaded();
    expect(screen.queryByTestId('home-error')).toBeNull();
  });

  it('reloads on pull-to-refresh, keeping the invoice if the reload fails', async () => {
    const home = new FakeHomeRepository();
    await renderHome(home);
    await loaded();

    home.spending = { ...november, total: '460.00' };
    const refresh = () => screen.getByTestId('home-scroll').props.refreshControl.props.onRefresh();
    await act(async () => refresh());
    await waitFor(() => expect(screen.getByTestId('invoice-total').props.children).toBe('$460.00'));

    home.offline = true;
    await act(async () => refresh());
    await waitFor(() => expect(screen.getByTestId('home-error')).toBeTruthy());
    expect(screen.getByTestId('invoice-total').props.children).toBe('$460.00');
  });
});
