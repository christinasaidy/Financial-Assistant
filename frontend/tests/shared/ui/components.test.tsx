import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet, Text } from 'react-native';

import { colors, fonts } from '@/shared/theme';
import {
  AppText,
  Button,
  Crease,
  Icon,
  LineIcon,
  PaperSheet,
  SegmentedChoice,
  TabBar,
  TextField,
  Wordmark,
  appTabs,
  iconNames,
  tears,
} from '@/shared/ui';

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

async function layout(testID: string, width: number, height: number) {
  await fireEvent(screen.getByTestId(testID, { includeHiddenElements: true }), 'layout', { nativeEvent: { layout: { x: 0, y: 0, width, height } } });
}

describe('AppText', () => {
  it('draws the cap label: Geist Mono 500, 10.5 px, 0.08em, capitals, capLabel', async () => {
    await render(<AppText cap>Invoice Nº 0447</AppText>);
    const style = flat(screen.getByText('Invoice Nº 0447').props.style);
    expect(style).toMatchObject({
      fontFamily: fonts.mono.medium,
      fontSize: 10.5,
      textTransform: 'uppercase',
      color: colors.capLabel,
    });
    expect(style.letterSpacing).toBeCloseTo(0.84);
  });

  it('picks the font file by kind and weight, and makes mono numbers tabular', async () => {
    await render(
      <>
        <AppText weight={600} size={18}>
          Fatourati
        </AppText>
        <AppText font="mono" weight={500} size={52}>
          $447.80
        </AppText>
        <AppText font="arabic">فاتورتي</AppText>
      </>,
    );
    expect(flat(screen.getByText('Fatourati').props.style)).toMatchObject({ fontFamily: fonts.sans.semibold, fontSize: 18 });
    expect(flat(screen.getByText('$447.80').props.style)).toMatchObject({ fontFamily: fonts.mono.medium, fontVariant: ['tabular-nums'] });
    expect(flat(screen.getByText('فاتورتي').props.style).fontFamily).toBe(fonts.arabic.semibold);
  });
});

describe('Button', () => {
  it('is cobalt with a white Geist 600 label, 52 px, radius 12', async () => {
    const onPress = jest.fn();
    await render(<Button label="Sign in" onPress={onPress} />);
    const button = screen.getByRole('button', { name: 'Sign in' });
    expect(flat(button.props.style)).toMatchObject({ backgroundColor: colors.cobalt, minHeight: 52, borderRadius: 12 });
    expect(flat(screen.getByText('Sign in').props.style)).toMatchObject({ color: colors.white, fontFamily: fonts.sans.semibold });
    await fireEvent.press(button);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('is outlined in ink when secondary', async () => {
    await render(<Button kind="secondary" label="Sign out" onPress={jest.fn()} />);
    expect(flat(screen.getByRole('button', { name: 'Sign out' }).props.style)).toMatchObject({ borderWidth: 1, borderColor: colors.ink });
  });

  it('ignores presses while busy', async () => {
    const onPress = jest.fn();
    await render(<Button label="Sign in" onPress={onPress} busy />);
    const button = screen.getByRole('button', { name: 'Sign in' });
    expect(button.props.accessibilityState).toMatchObject({ busy: true, disabled: true });
    await fireEvent.press(button);
    expect(onPress).not.toHaveBeenCalled();
  });
});

describe('TextField', () => {
  it('labels the input, shows the error, and turns the line cobalt while focused', async () => {
    await render(<TextField label="Email" value="" error="Enter your email." />);
    const input = screen.getByLabelText('Email');
    expect(input.props.accessibilityHint).toBe('Enter your email.');
    expect(screen.getByText('Enter your email.')).toBeTruthy();
    expect(flat(input.parent?.props.style)).toMatchObject({ borderBottomColor: colors.fieldLine });
    await fireEvent(input, 'focus');
    expect(flat(screen.getByLabelText('Email').parent?.props.style)).toMatchObject({ borderBottomWidth: 2, borderBottomColor: colors.cobalt });
  });

  it('hides a password and shows it with the eye button', async () => {
    await render(<TextField label="Password" value="secret-pass" password />);
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);
    await fireEvent.press(screen.getByRole('button', { name: 'Show password' }));
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(false);
    expect(screen.getByRole('button', { name: 'Hide password' })).toBeTruthy();
  });
});

describe('SegmentedChoice', () => {
  it('is a radio group whose chosen segment is clean paper', async () => {
    const onChange = jest.fn();
    await render(
      <SegmentedChoice
        label="Gender"
        choices={[
          { value: 'a', label: 'Female' },
          { value: 'b', label: 'Male' },
        ]}
        value="a"
        onChange={onChange}
        testIDPrefix="g"
      />,
    );
    expect(screen.getByRole('radio', { name: 'Female' }).props.accessibilityState).toMatchObject({ checked: true });
    expect(flat(screen.getByTestId('g-a').props.style).backgroundColor).toBe(colors.paperClean);
    await fireEvent.press(screen.getByRole('radio', { name: 'Male' }));
    expect(onChange).toHaveBeenCalledWith('b');
  });
});

describe('TabBar', () => {
  it('shows the five tabs, the active one ink and 600, Scan as the cobalt square', async () => {
    const onSelect = jest.fn();
    await render(<TabBar tabs={appTabs} selectedRoute="index" onSelect={onSelect} bottomInset={34} />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.props.accessibilityLabel)).toEqual(['Home', 'Receipts', 'Scan a receipt', 'Budgets', 'Assistant']);
    expect(flat(screen.getByText('Home').props.style)).toMatchObject({ color: colors.ink, fontFamily: fonts.sans.semibold });
    expect(flat(screen.getByText('Budgets').props.style)).toMatchObject({ color: colors.inkMuted, fontFamily: fonts.sans.medium });
    expect(screen.queryByText('Scan a receipt')).toBeNull();
    expect(flat(screen.getByTestId('tab-scan').props.style)).toMatchObject({ width: 56, height: 56, borderRadius: 16, backgroundColor: colors.cobalt });

    await fireEvent.press(screen.getByRole('tab', { name: 'Scan a receipt' }));
    expect(onSelect).toHaveBeenCalledWith('scan');
  });

  it('rings Scan only when asked (the empty Home)', async () => {
    await render(<TabBar tabs={appTabs} selectedRoute="index" onSelect={jest.fn()} bottomInset={0} />);
    expect(screen.queryByTestId('scan-ring')).toBeNull();
    await render(<TabBar tabs={appTabs} selectedRoute="index" onSelect={jest.fn()} bottomInset={0} scanHint />);
    expect(screen.getByTestId('scan-ring')).toBeTruthy();
  });

  it('keeps Christina’s five icons and no others', () => {
    expect([...iconNames].sort()).toEqual(['assistant', 'budgets', 'home', 'receipts', 'scan']);
  });
});

describe('paper', () => {
  it('tiles the crease 300 px wide over the whole box, with the overlay blend, never taking taps', async () => {
    await render(<Crease opacity={0.6} />);
    await layout('crease', 390, 700);
    const crease = screen.getByTestId('crease', { includeHiddenElements: true });
    expect(flat(crease.props.style)).toMatchObject({ mixBlendMode: 'overlay', opacity: 0.6 });
    expect(crease.props.pointerEvents).toBe('none');
    const tiles = crease.children as unknown as { props: { style: { width: number } } }[];
    // 390 px wide, centred: three columns; 700 px tall at 591 px a tile, centred: three rows.
    expect(tiles).toHaveLength(9);
    expect(tiles[0]?.props.style.width).toBe(300);
  });

  it('draws a sheet with its content under the crease, in an isolated, square box', async () => {
    await render(
      <PaperSheet on="bg" testID="sheet">
        <Text>Invoice</Text>
      </PaperSheet>,
    );
    const sheet = screen.getByText('Invoice').parent;
    expect(flat(sheet?.props.style)).toMatchObject({ backgroundColor: colors.paper, isolation: 'isolate', borderRadius: 0 });
    // The crease comes after the content, so it is drawn over it.
    const children = sheet?.children ?? [];
    const crease = screen.getByTestId('crease', { includeHiddenElements: true });
    expect(children.indexOf(crease)).toBeGreaterThan(children.indexOf(screen.getByText('Invoice')));
  });

  it('has the torn edges of DESIGN.md §3', () => {
    expect(tears).toEqual({ sheet: { tooth: 12, height: 6 }, slip: { tooth: 10, height: 5 }, launch: { tooth: 14, height: 7 } });
  });
});

describe('icons and wordmark', () => {
  it('draws every printed icon and every line icon', async () => {
    for (const name of iconNames) await render(<Icon name={name} />);
    for (const name of ['bell', 'eye', 'arrow', 'back', 'account'] as const) await render(<LineIcon name={name} />);
  });

  it('reads the wordmark as "Fatourati": Geist 600 18 with فاتورتي in Naskh, inkMuted', async () => {
    await render(<Wordmark />);
    expect(screen.getByLabelText('Fatourati')).toBeTruthy();
    expect(flat(screen.getByText('فاتورتي').props.style)).toMatchObject({ fontFamily: fonts.arabic.semibold, fontSize: 15, color: colors.inkMuted });
  });
});
