/**
 * The Receipts tab, a receipt's page and its two sheets with a fake backend, inside expo-router's test router.
 * Today is Thursday 26 November 2026.
 */

import { fireEvent, renderRouter, screen, waitFor, within } from 'expo-router/testing-library';
import { Share } from 'react-native';

import { ReceiptsService } from '@/features/receipts/application/receiptsService';
import { ReceiptScreen } from '@/features/receipts/ui/ReceiptScreen';
import { ChangeCategoryScreen, SplitItemsScreen } from '@/features/receipts/ui/ReceiptSheets';
import { ReceiptsScreen } from '@/features/receipts/ui/ReceiptsScreen';

import { FakeReceiptsRepository } from './fakes';

jest.setTimeout(30_000);

const today = () => new Date(2026, 10, 26, 10);

async function renderReceipts(repository = new FakeReceiptsRepository(), initialUrl = '/') {
  const service = new ReceiptsService(repository);
  const router = await renderRouter(
    {
      index: () => <ReceiptsScreen service={service} today={today} />,
      'receipt/[id]': () => <ReceiptScreen service={service} />,
      'receipt-category': () => <ChangeCategoryScreen service={service} />,
      'receipt-split': () => <SplitItemsScreen service={service} />,
    },
    { initialUrl },
  );
  return { router, repository };
}

afterEach(() => jest.restoreAllMocks());

describe('the Receipts tab (screen 13)', () => {
  it('shows the month, its total, the chips and the roll grouped by week', async () => {
    await renderReceipts();
    await waitFor(() => expect(screen.getByTestId('receipts-roll')).toBeTruthy());
    expect(screen.getByText('November 2026')).toBeTruthy();
    expect(screen.getByTestId('receipts-total').props.children).toBe('Total $447.80');
    expect(screen.getByText('This week')).toBeTruthy();
    expect(screen.getByText('Earlier in November')).toBeTruthy();
    expect(screen.getByText('Barbar Hamra')).toBeTruthy();
    expect(screen.getByText('Groceries · 5 items')).toBeTruthy();
    expect(screen.getByText('≈ $5.03')).toBeTruthy();
    // Only confirmed receipts.
    expect(screen.queryByText('Still reading')).toBeNull();
    expect(screen.getAllByRole('radio').map((chip) => chip.props.accessibilityLabel)).toEqual(['All', 'Eating out', 'Groceries', 'Transport', 'Other']);
  });

  it('narrows the roll with a chip and says how many are shown', async () => {
    await renderReceipts();
    await waitFor(() => expect(screen.getByTestId('receipts-roll')).toBeTruthy());
    await fireEvent.press(screen.getByRole('radio', { name: 'Eating out' }));
    expect(screen.getByTestId('receipts-total').props.children).toBe('2 receipts shown');
    expect(screen.queryByText('Spinneys Achrafieh')).toBeNull();
    await fireEvent.press(screen.getByRole('radio', { name: 'Other' }));
    expect(screen.getByText('Kiosk')).toBeTruthy();
  });

  it('searches shops and categories', async () => {
    await renderReceipts();
    await waitFor(() => expect(screen.getByTestId('receipts-roll')).toBeTruthy());
    await fireEvent.press(screen.getByRole('button', { name: 'Search receipts' }));
    await fireEvent.changeText(screen.getByLabelText('Search shops and categories'), 'spinn');
    expect(screen.getByText('Spinneys Achrafieh')).toBeTruthy();
    expect(screen.queryByText('Bolt')).toBeNull();
    await fireEvent.changeText(screen.getByLabelText('Search shops and categories'), 'nothing here');
    expect(screen.getByText('No receipts match “nothing here”.')).toBeTruthy();
  });

  it('goes to older receipts, and back with the month switcher', async () => {
    const { repository } = await renderReceipts();
    await waitFor(() => expect(screen.getByTestId('older-receipts')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('older-receipts'));
    await waitFor(() => expect(screen.getByText('Medco station')).toBeTruthy());
    expect(repository.calls).toContain('total 2026-10');
    await fireEvent.press(screen.getByRole('button', { name: 'Change month' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Next month' }));
    await waitFor(() => expect(screen.getByText('Barbar Hamra')).toBeTruthy());
    expect(screen.getByRole('button', { name: 'Next month' }).props.accessibilityState).toMatchObject({ disabled: true });
  });

  it('opens a receipt from its row', async () => {
    const { router } = await renderReceipts();
    await waitFor(() => expect(screen.getByTestId('receipt-31')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('receipt-31'));
    await waitFor(() => expect(router.getPathname()).toBe('/receipt/31'));
  });
});

describe('a receipt’s page (screen 05)', () => {
  async function openSpinneys(repository = new FakeReceiptsRepository()) {
    const result = await renderReceipts(repository, '/receipt/31');
    await waitFor(() => expect(screen.getByTestId('receipt-sheet')).toBeTruthy());
    return result;
  }

  it('shows the receipt: category, shop, total, the item table and the budget after it', async () => {
    await openSpinneys();
    const sheet = within(screen.getByTestId('receipt-sheet'));
    expect(sheet.getByText('Receipt · Groceries')).toBeTruthy();
    expect(sheet.getByText('Spinneys Achrafieh')).toBeTruthy();
    expect(sheet.getByTestId('receipt-total').props.children).toBe('$38.40');
    expect(sheet.getByText('Labneh')).toBeTruthy();
    expect(sheet.getAllByText('1 kg')).toHaveLength(1);
    expect(sheet.getByText('12')).toBeTruthy();
    expect(sheet.getByText('Total · 5 items')).toBeTruthy();
    expect(sheet.getByText('Groceries after this')).toBeTruthy();
    expect(sheet.getByText('186.40 / 250')).toBeTruthy();
    expect(sheet.getByText('$63.60 left this month')).toBeTruthy();
  });

  it('shares the receipt as text', async () => {
    const share = jest.spyOn(Share, 'share').mockResolvedValue({ action: 'sharedAction', activityType: undefined });
    await openSpinneys();
    await fireEvent.press(screen.getByRole('button', { name: 'Share receipt' }));
    expect(share.mock.calls[0]?.[0]).toMatchObject({ message: expect.stringContaining('Spinneys Achrafieh · Groceries') });
  });

  it('changes the category: every item follows it', async () => {
    const { repository, router } = await openSpinneys();
    await fireEvent.press(screen.getByRole('button', { name: 'Change category' }));
    await waitFor(() => expect(screen.getByRole('header', { name: 'Which category?' })).toBeTruthy());
    expect(screen.getByRole('radio', { name: 'Groceries' }).props.accessibilityState).toMatchObject({ checked: true });
    await fireEvent.press(screen.getByRole('radio', { name: 'Eating out' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Save category' }));
    await waitFor(() => expect(router.getPathname()).toBe('/receipt/31'));
    expect(repository.saved[0]?.payload.categoryId).toBe(2);
    await waitFor(() => expect(screen.getByText('Receipt · Eating out')).toBeTruthy());
  });

  it('splits items into their own categories', async () => {
    const { repository } = await openSpinneys();
    await fireEvent.press(screen.getByRole('button', { name: 'Split items' }));
    await waitFor(() => expect(screen.getByRole('header', { name: 'Give items their own category.' })).toBeTruthy());
    expect(screen.getByText('The rest stay in Groceries.')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('split-3-4'));
    await fireEvent.press(screen.getByRole('button', { name: 'Save split' }));
    await waitFor(() => expect(repository.saved).toHaveLength(1));
    expect(repository.saved[0]?.payload.lines.map((item) => item.categoryId)).toEqual([null, null, null, 4, null]);
    // Back on the page, the split item is marked with its own category.
    await waitFor(() => expect(within(screen.getByTestId('line-3')).getByText('Pharmacy')).toBeTruthy());
  });

  it('says why it could not load, and loads on Try again', async () => {
    const repository = new FakeReceiptsRepository();
    repository.offline = true;
    await renderReceipts(repository, '/receipt/31');
    await waitFor(() => expect(screen.getByText("Can't reach Fatourati. Check your connection and try again.")).toBeTruthy());
    repository.offline = false;
    await fireEvent.press(screen.getByRole('link', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByTestId('receipt-sheet')).toBeTruthy());
  });
});

