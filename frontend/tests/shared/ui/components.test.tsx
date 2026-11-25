import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { ThemeOverride, colorTokens, inkOnHighlight } from '@/shared/theme';
import { AppText, Button, DashedRule, Icon, Paper, TabBar, TextField, Wordmark, appTabs, iconNames } from '@/shared/ui';

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

describe('AppText', () => {
  it('applies the variant: font, size, capitals by style and its default colour', async () => {
    await render(<AppText variant="section-label">This month</AppText>);
    const style = flat(screen.getByText('This month').props.style);
    expect(style).toMatchObject({
      fontFamily: 'DejaVuSansMono',
      fontSize: 12,
      lineHeight: 16,
      textTransform: 'uppercase',
      color: colorTokens['ink-2'].light,
    });
    expect(style.letterSpacing).toBeCloseTo(0.96);
  });

  it('uses the dark value of a token in dark mode', async () => {
    await render(
      <ThemeOverride scheme="dark">
        <AppText variant="receipt-line" color="primary">
          See all
        </AppText>
      </ThemeOverride>,
    );
    expect(flat(screen.getByText('See all').props.style).color).toBe(colorTokens.primary.dark);
  });
});

describe('Button', () => {
  it('is a button with a paper-coloured total-line label on pen blue', async () => {
    const onPress = jest.fn();
    await render(<Button label="Scan a receipt" icon="scan" onPress={onPress} />);
    const button = screen.getByRole('button', { name: 'Scan a receipt' });
    expect(flat(button.props.style)).toMatchObject({ backgroundColor: colorTokens.primary.light, minHeight: 48 });
    expect(flat(screen.getByText('Scan a receipt').props.style)).toMatchObject({
      fontFamily: 'DejaVuSansMono-Bold',
      fontSize: 16,
      color: colorTokens.paper.light,
    });
    await fireEvent.press(button);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('ignores presses while busy', async () => {
    const onPress = jest.fn();
    await render(<Button label="Sign in" busy onPress={onPress} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(onPress).not.toHaveBeenCalled();
  });
});

describe('TextField', () => {
  it('labels the input, shows the error and runs the trailing action', async () => {
    const onToggle = jest.fn();
    await render(
      <TextField
        label="Password"
        value="secret"
        secureTextEntry
        error="Wrong email or password"
        trailingAction={{ label: 'Show', accessibilityLabel: 'Show password', onPress: onToggle }}
      />,
    );
    expect(screen.getByLabelText('Password')).toBeTruthy();
    expect(flat(screen.getByText('Wrong email or password').props.style).color).toBe(
      colorTokens['limit-reached'].light,
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Show password' }));
    expect(onToggle).toHaveBeenCalled();
  });
});

describe('TabBar', () => {
  it('shows the five tabs, marks the selected one and reports presses', async () => {
    const onSelect = jest.fn();
    await render(<TabBar tabs={appTabs} selectedRoute="index" onSelect={onSelect} bottomInset={34} />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.props.accessibilityLabel)).toEqual(['Home', 'Receipts', 'Scan', 'Budgets', 'Assistant']);
    expect(screen.getByRole('tab', { name: 'Home' }).props.accessibilityState).toMatchObject({ selected: true });
    // Ink text on the yellow swipe (D038), grey for the others.
    expect(flat(screen.getByText('Home').props.style).color).toBe(inkOnHighlight);
    expect(flat(screen.getByText('Budgets').props.style).color).toBe(colorTokens['ink-2'].light);
    expect(screen.getAllByTestId('highlight-swipe')).toHaveLength(1);

    await fireEvent.press(screen.getByRole('tab', { name: 'Scan' }));
    expect(onSelect).toHaveBeenCalledWith('scan');
  });

  it('draws the yellow swipe at the size its label measures, clipped to it, so it never spills onto the icon', async () => {
    await render(<TabBar tabs={appTabs} selectedRoute="budgets" onSelect={jest.fn()} bottomInset={0} />);
    const swipe = screen.getByTestId('highlight-swipe');
    let box = swipe.parent;
    while (box && !box.props.onLayout) box = box.parent;
    if (!box) throw new Error('the swipe has no measured box');
    expect(flat(box.props.style).overflow).toBe('hidden');

    await fireEvent(box, 'layout', { nativeEvent: { layout: { x: 0, y: 0, width: 61, height: 15 } } });
    const drawn = screen.getByTestId('highlight-swipe');
    expect([drawn.props.width, drawn.props.height]).toEqual([61, 15]);
  });
});

describe('artwork and paper', () => {
  it('draws every icon in both variants', async () => {
    for (const name of iconNames) {
      await render(<Icon name={name} />);
      await render(<Icon name={name} printed={false} />);
    }
  });

  it('reads the wordmark as "Fatourati"', async () => {
    await render(<Wordmark size="small" highlighted />);
    expect(screen.getByLabelText('Fatourati')).toBeTruthy();
    expect(screen.getByTestId('highlight-swipe')).toBeTruthy();
  });

  it('renders both papers and the dashed rule', async () => {
    await render(
      <Paper variant="plain">
        <DashedRule />
      </Paper>,
    );
    expect(screen.getByTestId('paper-plain')).toBeTruthy();
    await render(<Paper variant="yellow" />);
    expect(flat(screen.getByTestId('paper-yellow').props.style).backgroundColor).toBe('#f5e54a');
  });
});
