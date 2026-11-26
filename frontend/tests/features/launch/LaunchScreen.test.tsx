import { render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { LaunchScreen } from '@/features/launch/ui/LaunchScreen';
import { colors, fonts } from '@/shared/theme';

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

describe('LaunchScreen (design/screens/01-launch.png)', () => {
  it('is one creased launch sheet on white', async () => {
    await render(
      <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 59, bottom: 34, left: 0, right: 0 } }}>
        <LaunchScreen />
      </SafeAreaProvider>,
    );
    expect(flat(screen.getByTestId('launch-screen').props.style).backgroundColor).toBe(colors.white);
    expect(flat(screen.getByText('Fatourati').parent?.parent?.props.style).backgroundColor).toBe(colors.launchPaper);
    expect(screen.getByTestId('crease', { includeHiddenElements: true }).props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({ opacity: 0.69 })]),
    );
  });

  it('carries the invoice header, the huge فاتورتي, the name, the zero total and the tagline', async () => {
    await render(
      <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 59, bottom: 34, left: 0, right: 0 } }}>
        <LaunchScreen />
      </SafeAreaProvider>,
    );
    expect(flat(screen.getByText('Invoice Nº 0001').props.style).color).toBe(colors.launchCobalt);
    expect(screen.getByText('USD · LBP')).toBeTruthy();
    expect(flat(screen.getByText('فاتورتي').props.style)).toMatchObject({ fontFamily: fonts.arabic.bold, fontSize: 108 });
    expect(screen.getByRole('header', { name: 'Fatourati' })).toBeTruthy();
    expect(screen.getByText('Total · $0.00')).toBeTruthy();
    expect(screen.getByText('Every crumpled receipt, flattened out and accounted for.')).toBeTruthy();
  });
});
