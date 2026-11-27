/**
 * The scan screens with a fake backend, inside expo-router's test router (design/screens/09-12).
 */
import { fireEvent, renderRouter, screen, waitFor, within } from 'expo-router/testing-library';
import { Text } from 'react-native';

import { ScanService } from '@/features/scan/application/scanService';
import { CameraScreen } from '@/features/scan/ui/CameraScreen';
import { FiledScreen } from '@/features/scan/ui/FiledScreen';
import { ReadingScreen } from '@/features/scan/ui/ReadingScreen';
import { ReviewScreen } from '@/features/scan/ui/ReviewScreen';

import { FakeScanRepository, readSpinneys } from './fakes';

jest.setTimeout(30_000);

jest.mock('expo-camera', () => {
  const { View } = jest.requireActual('react-native');
  return {
    CameraView: (props: object) => <View {...props} />,
    useCameraPermissions: () => [globalThis.__cameraPermission, jest.fn()],
  };
});
jest.mock('expo-image-picker', () => ({ launchImageLibraryAsync: jest.fn() }));

declare global {
  var __cameraPermission: { granted: boolean; canAskAgain: boolean } | null;
}

const today = () => new Date(2026, 10, 26, 10);

async function renderScan(initialUrl: string, repository = new FakeScanRepository()) {
  const service = new ScanService(repository);
  const router = await renderRouter(
    {
      'scan/index': () => <Text>Camera</Text>,
      'scan/reading': () => <ReadingScreen service={service} rowMs={1} />,
      'scan/review': () => <ReviewScreen service={service} today={today} />,
      'scan/filed': () => <FiledScreen service={service} />,
      'receipt/[id]': () => <Text>Receipt page</Text>,
    },
    { initialUrl },
  );
  return { router, repository };
}

describe('the camera (screen 09)', () => {
  it('asks for the camera before it can take a photo, and keeps Upload', async () => {
    globalThis.__cameraPermission = { granted: false, canAskAgain: true };
    await renderRouter({ index: () => <CameraScreen /> }, { initialUrl: '/' });
    expect(screen.getByText('Fatourati needs the camera to scan your receipts.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Allow the camera' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Take photo' }).props.accessibilityState).toMatchObject({ disabled: true });
    expect(screen.getByRole('button', { name: 'Upload a photo' })).toBeTruthy();
    expect(screen.queryByText('Long receipt')).toBeNull();
  });

  it('shows the viewfinder with the tip and a flash toggle once allowed', async () => {
    globalThis.__cameraPermission = { granted: true, canAskAgain: true };
    await renderRouter({ index: () => <CameraScreen /> }, { initialUrl: '/' });
    expect(screen.getByTestId('camera-view')).toBeTruthy();
    expect(screen.getByText('Hold the phone steady')).toBeTruthy();
    expect(screen.getByText('Fit the whole receipt inside the corners')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Flash off' }));
    expect(screen.getByRole('button', { name: 'Flash on' })).toBeTruthy();
  });
});

describe('reading (screen 10)', () => {
  it('sends the photo, ticks off what was found, then opens Review', async () => {
    const { router, repository } = await renderScan('/scan/reading?uri=file%3A%2F%2F%2Fr.jpg&type=image%2Fjpeg');
    expect(screen.getByText('Reading receipt')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('step-Store')).toBeTruthy(), { timeout: 8000 });
    expect(repository.calls[0]).toBe('upload image/jpeg');
    await waitFor(() => expect(router.getPathname()).toBe('/scan/review'), { timeout: 8000 });
  });

  it('offers Retake and filling it in by hand when the photo could not be read', async () => {
    const repository = new FakeScanRepository();
    repository.failReading = true;
    await renderScan('/scan/reading?uri=file%3A%2F%2F%2Fr.jpg', repository);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Fill it in by hand' })).toBeTruthy(), { timeout: 8000 });
    expect(screen.getByRole('button', { name: 'Retake' })).toBeTruthy();
  });
});

describe('review (screen 11)', () => {
  async function openReview(repository = new FakeScanRepository()) {
    const result = await renderScan('/scan/review?id=100', repository);
    await waitFor(() => expect(screen.getByTestId('review-sheet')).toBeTruthy());
    return result;
  }

  it('shows what was read to edit, four items then the rest, and that they add up', async () => {
    await openReview();
    const sheet = within(screen.getByTestId('review-sheet'));
    expect(sheet.getByText('New receipt · for Nº 0003')).toBeTruthy();
    expect(screen.getByLabelText('Store').props.value).toBe('Spinneys Achrafieh');
    expect(screen.getByLabelText('Date').props.value).toBe('18/11/2026');
    expect(screen.getByRole('radio', { name: 'USD' }).props.accessibilityState).toMatchObject({ checked: true });
    expect(sheet.getByText('Labneh')).toBeTruthy();
    expect(sheet.queryByText('Halloumi')).toBeNull();
    expect(sheet.getByText('+ 5 more items')).toBeTruthy();
    expect(sheet.getByText('Items add up to the total')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('more-items'));
    expect(sheet.getByText('Halloumi')).toBeTruthy();
  });

  it('marks the unnamed item CHECK THIS, and suggests the store’s category', async () => {
    await openReview();
    expect(within(screen.getByTestId('review-line-3')).getByText('Check this')).toBeTruthy();
    expect(screen.getByRole('radio', { name: 'Groceries' }).props.accessibilityState).toMatchObject({ checked: true });
    expect(screen.getByText('Suggested from the store')).toBeTruthy();
    await fireEvent.press(screen.getByRole('radio', { name: 'Eating out' }));
    expect(screen.queryByText('Suggested from the store')).toBeNull();
  });

  it('warns when the items do not add up, and checks the fields before saving', async () => {
    const { repository } = await openReview();
    await fireEvent.changeText(screen.getByLabelText('Total'), '40.00');
    expect(screen.getByTestId('mismatch')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Store'), '');
    await fireEvent.changeText(screen.getByLabelText('Date'), '31/02/2026');
    await fireEvent.press(screen.getByRole('button', { name: 'Save to November invoice' }));
    expect(screen.getByText('Enter the store.')).toBeTruthy();
    expect(screen.getByText('Enter the date like 18/11/2026.')).toBeTruthy();
    expect(repository.saved).toBeNull();
  });

  it('saves to the month’s invoice and opens Filed', async () => {
    const { router, repository } = await openReview();
    await fireEvent.press(screen.getByRole('button', { name: 'Save to November invoice' }));
    await waitFor(() => expect(router.getPathname()).toBe('/scan/filed'));
    expect(repository.saved).toMatchObject({ categoryId: 1, total: '38.40' });
  });
});

describe('filed (screen 12)', () => {
  it('shows the category, the change struck through, and the new total', async () => {
    const repository = new FakeScanRepository();
    repository.saved = { shopName: 'Spinneys Achrafieh', receiptDate: '2026-11-18', currency: 'USD', total: '38.40', categoryId: 1, lines: readSpinneys().lines };
    const { router } = await renderScan('/scan/filed?id=100', repository);
    await waitFor(() => expect(screen.getByRole('header', { name: 'Filed under Groceries' })).toBeTruthy());
    const invoice = within(screen.getByTestId('filed-invoice'));
    expect(invoice.getByText('Invoice Nº 0003')).toBeTruthy();
    expect(invoice.getByText('148.00')).toBeTruthy();
    expect(invoice.getByText('+38.40')).toBeTruthy();
    expect(invoice.getByText('63.60 left')).toBeTruthy();
    expect(invoice.getByText('409.40')).toBeTruthy();
    await fireEvent.press(screen.getByRole('link', { name: 'View receipt' }));
    await waitFor(() => expect(router.getPathname()).toBe('/receipt/100'));
  });
});
