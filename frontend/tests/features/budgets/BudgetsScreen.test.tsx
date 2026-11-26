/**
 * Budgets and its form sheet with a fake backend, inside expo-router's test router, against
 * design/screens/06-budgets.png. Today is fixed at 26 November 2026, so November has 4 days left.
 */
import { fireEvent, renderRouter, screen, waitFor, within } from 'expo-router/testing-library';
import { Alert, StyleSheet } from 'react-native';

import { BudgetsService } from '@/features/budgets/application/budgetsService';
import { BudgetFormScreen } from '@/features/budgets/ui/BudgetFormScreen';
import { BudgetsScreen } from '@/features/budgets/ui/BudgetsScreen';
import { colors } from '@/shared/theme';

import { FakeBudgetsRepository } from './fakes';

jest.setTimeout(30_000);

const today = () => new Date(2026, 10, 26, 10, 0);

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

async function renderBudgets(repository = new FakeBudgetsRepository()) {
  const service = new BudgetsService(repository);
  const router = await renderRouter(
    {
      index: () => <BudgetsScreen service={service} today={today} />,
      'budget-form': () => <BudgetFormScreen service={service} />,
    },
    { initialUrl: '/' },
  );
  await waitFor(() => expect(screen.getByTestId('budget-sheet')).toBeTruthy());
  return { router, repository };
}

afterEach(() => jest.restoreAllMocks());

describe('Budgets (design/screens/06-budgets.png)', () => {
  it('shows the budget sheet with the design’s numbers', async () => {
    await renderBudgets();
    const sheet = within(screen.getByTestId('budget-sheet'));
    expect(sheet.getByText('Budget sheet · Nov 2026')).toBeTruthy();
    expect(sheet.getByText('4 days left')).toBeTruthy();
    expect(sheet.getByText('$320.90')).toBeTruthy();
    expect(sheet.getByText('of $390 budgeted')).toBeTruthy();
    expect(sheet.getByText('$69.10 left across 3 budgets')).toBeTruthy();
    expect(sheet.getByText('82%')).toBeTruthy();
  });

  it('shows one slip per budget, over-budget first and in red, with the pace', async () => {
    await renderBudgets();
    const slips = screen.getAllByTestId(/^budget-slip-/).map((slip) => slip.props.testID);
    expect(slips).toEqual(['budget-slip-1', 'budget-slip-2', 'budget-slip-3']);
    const transport = within(screen.getByTestId('budget-slip-1'));
    expect(flat(transport.getByText('63.00').props.style)).toMatchObject({ color: colors.redText });
    expect(flat(transport.getByText('Over by $3.00').props.style)).toMatchObject({ color: colors.redText });
    expect(transport.getByText('$0.00 a day')).toBeTruthy();
    const eatingOut = within(screen.getByTestId('budget-slip-2'));
    expect(eatingOut.getByText('$8.50 left')).toBeTruthy();
    expect(eatingOut.getByText('$2.13 a day')).toBeTruthy();
    expect(within(screen.getByTestId('budget-slip-3')).getByText('$15.90 a day')).toBeTruthy();
    expect(screen.getByText('Not in any budget yet')).toBeTruthy();
    expect(screen.getByText('· $126.90')).toBeTruthy();
  });

  it('cannot go past the current month, and shows an earlier month as ended', async () => {
    const { repository } = await renderBudgets();
    expect(screen.getByRole('button', { name: 'Next month' }).props.accessibilityState).toMatchObject({ disabled: true });

    await fireEvent.press(screen.getByRole('button', { name: 'Previous month' }));
    await waitFor(() => expect(screen.getByText('Budget sheet · Oct 2026')).toBeTruthy());
    expect(repository.calls).toContain('budgets 2026-10');
    expect(screen.getByText('Month ended')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next month' }).props.accessibilityState).toMatchObject({ disabled: false });
  });

  it('is a blank budget sheet before any budget (D046)', async () => {
    const repository = new FakeBudgetsRepository();
    repository.byMonth.set('2026-11', []);
    await renderBudgets(repository);
    expect(flat(screen.getByTestId('budget-sheet-spent').props.style).color).toBe(colors.zeroAmount);
    expect(screen.getByText('No budgets yet. Set a monthly limit for a category.')).toBeTruthy();
    expect(screen.getByText('· $447.80')).toBeTruthy();
  });

  it('says why it could not load, and loads on Try again', async () => {
    const repository = new FakeBudgetsRepository();
    repository.offline = true;
    const service = new BudgetsService(repository);
    await renderRouter({ index: () => <BudgetsScreen service={service} today={today} /> }, { initialUrl: '/' });
    await waitFor(() => expect(screen.getByText("Can't reach Fatourati. Check your connection and try again.")).toBeTruthy());
    repository.offline = false;
    await fireEvent.press(screen.getByRole('link', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByTestId('budget-sheet')).toBeTruthy());
  });
});

describe('the budget form (D046)', () => {
  it('creates a budget: choose a category, a limit and the currency', async () => {
    const { router, repository } = await renderBudgets();
    await fireEvent.press(screen.getByRole('button', { name: 'New budget' }));
    await waitFor(() => expect(screen.getByRole('header', { name: 'Set a monthly limit.' })).toBeTruthy());
    expect(screen.getByText('It applies from November 2026 onwards.')).toBeTruthy();
    expect(screen.getAllByRole('radio').filter((radio) => radio.props.testID?.startsWith('category-')).map((radio) => radio.props.accessibilityLabel)).toEqual([
      'Bills',
      'Pharmacy',
    ]);

    await fireEvent.press(screen.getByRole('button', { name: 'Save budget' }));
    expect(screen.getByText('Choose a category.')).toBeTruthy();
    expect(screen.getByText('Enter a monthly limit.')).toBeTruthy();
    expect(repository.calls.filter((call) => call.startsWith('set'))).toEqual([]);

    await fireEvent.press(screen.getByRole('radio', { name: 'Pharmacy' }));
    await fireEvent.changeText(screen.getByLabelText('Monthly limit'), '120');
    await fireEvent.press(screen.getByRole('button', { name: 'Save budget' }));
    await waitFor(() => expect(router.getPathname()).toBe('/'));
    expect(repository.calls).toContain('set 5 2026-11 USD 120');
    await waitFor(() => expect(screen.getByTestId('budget-slip-5')).toBeTruthy());
  });

  it('opens a budget from its slip, filled in, and changes it', async () => {
    const { repository } = await renderBudgets();
    await fireEvent.press(screen.getByTestId('budget-slip-1'));
    await waitFor(() => expect(screen.getByRole('header', { name: 'Transport' })).toBeTruthy());
    expect(screen.getByText('Edit budget')).toBeTruthy();
    expect(screen.getByLabelText('Monthly limit').props.value).toBe('60');
    expect(screen.queryByRole('radio', { name: 'Bills' })).toBeNull();

    await fireEvent.changeText(screen.getByLabelText('Monthly limit'), '1,000.5');
    await fireEvent.press(screen.getByRole('radio', { name: 'LBP' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Save budget' }));
    expect(screen.getByText('Pounds have no decimals.')).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText('Monthly limit'), '5,000,000');
    await fireEvent.press(screen.getByRole('button', { name: 'Save budget' }));
    await waitFor(() => expect(repository.calls).toContain('set 1 2026-11 LBP 5000000'));
  });

  it('removes a budget after asking', async () => {
    const alert = jest.spyOn(Alert, 'alert');
    const { router, repository } = await renderBudgets();
    await fireEvent.press(screen.getByTestId('budget-slip-2'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove budget' })).toBeTruthy());
    await fireEvent.press(screen.getByRole('button', { name: 'Remove budget' }));

    expect(alert).toHaveBeenCalledWith('Remove the Eating out budget?', 'It is removed for every month.', expect.any(Array));
    const buttons = alert.mock.calls[0]?.[2] as { text: string; onPress?: () => Promise<void> }[];
    await buttons.find((button) => button.text === 'Remove')?.onPress?.();
    await waitFor(() => expect(router.getPathname()).toBe('/'));
    expect(repository.calls).toContain('remove 2');
  });

  it('shows the backend’s reason when it refuses a budget', async () => {
    const repository = new FakeBudgetsRepository();
    repository.rejectWith = 'The limit is too large';
    await renderBudgets(repository);
    await fireEvent.press(screen.getByTestId('budget-slip-3'));
    await waitFor(() => expect(screen.getByLabelText('Monthly limit').props.value).toBe('250'));
    await fireEvent.press(screen.getByRole('button', { name: 'Save budget' }));
    await waitFor(() => expect(screen.getByText('The limit is too large')).toBeTruthy());
  });
});
