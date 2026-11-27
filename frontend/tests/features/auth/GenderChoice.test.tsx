import { fireEvent, render, screen } from '@testing-library/react-native';
import { useState } from 'react';
import { StyleSheet } from 'react-native';

import type { Gender } from '@/features/auth/domain/types';
import { GenderChoice } from '@/features/auth/ui/GenderChoice';
import { colors, fonts } from '@/shared/theme';

function flat(style: unknown) {
  return StyleSheet.flatten(style as never) as Record<string, unknown>;
}

function Choice({ initial = null }: { initial?: Gender | null }) {
  const [value, setValue] = useState<Gender | null>(initial);
  return <GenderChoice value={value} onChange={setValue} />;
}

describe('GenderChoice', () => {
  it('is a radio group of the three answers, in order, none chosen at first', async () => {
    await render(<Choice />);
    // The group is not one VoiceOver element itself (that would hide the options), so find it by its label.
    expect(screen.getByLabelText('Gender').props.accessibilityRole).toBe('radiogroup');
    const radios = screen.getAllByRole('radio');
    expect(radios.map((radio) => radio.props.accessibilityLabel)).toEqual(['Female', 'Male', 'Prefer not to say']);
    expect(radios.map((radio) => radio.props.accessibilityState)).toEqual([
      { checked: false },
      { checked: false },
      { checked: false },
    ]);
    expect(radios.map((radio) => radio.props.accessibilityHint)).toEqual(['1 of 3', '2 of 3', '3 of 3']);
  });

  it('checks the pressed answer and unchecks the others', async () => {
    await render(<Choice />);
    await fireEvent.press(screen.getByRole('radio', { name: 'Male' }));
    expect(screen.getByRole('radio', { name: 'Male', checked: true })).toBeTruthy();
    expect(screen.getAllByRole('radio', { checked: false })).toHaveLength(2);

    await fireEvent.press(screen.getByRole('radio', { name: 'Prefer not to say' }));
    expect(screen.getByRole('radio', { checked: true }).props.accessibilityLabel).toBe('Prefer not to say');
  });

  it('reports the chosen value', async () => {
    const onChange = jest.fn();
    await render(<GenderChoice value={null} onChange={onChange} />);
    await fireEvent.press(screen.getByRole('radio', { name: 'Female' }));
    expect(onChange).toHaveBeenCalledWith('female');
  });

  it('is the segmented switch: the chosen answer clean paper in ink 600, the others 500 (D044)', async () => {
    await render(<Choice initial="female" />);
    expect(flat(screen.getByTestId('gender-female').props.style)).toMatchObject({ backgroundColor: colors.paperClean, minHeight: 44 });
    expect(flat(screen.getByTestId('gender-male').props.style).backgroundColor).toBeUndefined();
    expect(flat(screen.getByText('Female').props.style)).toMatchObject({ color: colors.ink, fontFamily: fonts.sans.semibold });
    expect(flat(screen.getByText('Male').props.style)).toMatchObject({ color: colors.fieldLabel, fontFamily: fonts.sans.medium });
  });

  it('shows the error and gives it to VoiceOver on each option', async () => {
    await render(<GenderChoice value={null} onChange={jest.fn()} error="Choose Female, Male or Prefer not to say." />);
    expect(flat(screen.getByText('Choose Female, Male or Prefer not to say.').props.style).color).toBe(colors.redText);
    expect(screen.getByRole('radio', { name: 'Female' }).props.accessibilityHint).toBe(
      'Choose Female, Male or Prefer not to say.',
    );
  });
});
