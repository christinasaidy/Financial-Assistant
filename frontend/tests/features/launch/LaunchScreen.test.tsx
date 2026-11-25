import { render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { LaunchScreen } from '@/features/launch/ui/LaunchScreen';
import { ThemeOverride, inkOnHighlight, type ColorScheme } from '@/shared/theme';

// The status bar draws nothing in the tree; record the style the screen asks for instead.
jest.mock('expo-status-bar', () => {
  const { View } = jest.requireActual('react-native');
  return {
    StatusBar: ({ style }: { style?: string }) => <View testID="status-bar" accessibilityHint={style} />,
  };
});

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

describe.each<ColorScheme>(['light', 'dark'])('LaunchScreen in the %s theme', (scheme) => {
  beforeEach(async () => {
    await render(
      <ThemeOverride scheme={scheme}>
        <LaunchScreen />
      </ThemeOverride>,
    );
  });

  it('is yellow paper with its grain, the same in both themes (D039)', () => {
    expect(flat(screen.getByTestId('paper-yellow').props.style).backgroundColor).toBe('#f5e54a');
    expect(screen.queryByTestId('paper-plain')).toBeNull();
  });

  it('shows only the large wordmark, in ink, read as "Fatourati", centred', () => {
    const wordmark = screen.getByLabelText('Fatourati');
    expect(wordmark.props.accessibilityRole).toBe('image');
    expect(flat(wordmark.props.style)).toMatchObject({ width: 284, height: 59 });
    const drawing = wordmark.children[0];
    expect(typeof drawing === 'object' ? drawing.props.color : null).toBe(inkOnHighlight);
    // The wordmark sits in a box that shrinks to it, in a box that fills the paper and centres it.
    expect(flat(wordmark.parent?.parent?.props.style)).toMatchObject({
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
    });
    expect(screen.queryAllByText(/./)).toHaveLength(0);
  });

  it('keeps the status bar dark on the yellow', () => {
    expect(screen.getByTestId('status-bar').props.accessibilityHint).toBe('dark');
  });
});
