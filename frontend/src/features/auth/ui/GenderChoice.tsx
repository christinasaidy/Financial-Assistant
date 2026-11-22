import { Pressable, StyleSheet, View } from 'react-native';

import { rounded, sizes, spacing, useTheme } from '@/shared/theme';
import { AppText } from '@/shared/ui';

import { genders, type Gender } from '../domain/types';

/** Written in normal case; shown in capitals by the section-label style (D012). */
export const genderLabels: Record<Gender, string> = {
  female: 'Female',
  male: 'Male',
  prefer_not_to_say: 'Prefer not to say',
};

/** Height of an option (D041). */
const OPTION_HEIGHT = 48;
/** The chosen option's border (D041). */
const CHOSEN_BORDER = 2;

type Props = {
  value: Gender | null;
  onChange: (gender: Gender) => void;
  /** Shown under the options in the same style as a field's error. */
  error?: string | null;
};

/**
 * The gender question of create account (D041): a GENDER caption over three equal square options in one row.
 * Each option has a 1 px `rule` border; the chosen one a 2 px pen-blue border and a pen-blue label, because it
 * is something the user changes (D018). A radio group for VoiceOver: "Female, radio button, checked, 1 of 3".
 *
 * The thicker border is drawn without moving the label: each option keeps 2 px of border plus padding, and
 * the 1 px border gets 1 px more padding.
 */
export function GenderChoice({ value, onChange, error }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.field}>
      {/* Read by VoiceOver before the options, so each option can be just its name. */}
      <AppText variant="section-label">Gender</AppText>
      <View accessibilityRole="radiogroup" accessibilityLabel="Gender" style={styles.row}>
        {genders.map((gender, index) => {
          const chosen = gender === value;
          return (
            <Pressable
              key={gender}
              accessibilityRole="radio"
              accessibilityLabel={genderLabels[gender]}
              accessibilityHint={error ?? `${index + 1} of ${genders.length}`}
              accessibilityState={{ checked: chosen }}
              onPress={() => onChange(gender)}
              testID={`gender-${gender}`}
              style={[
                styles.option,
                chosen
                  ? { borderWidth: CHOSEN_BORDER, borderColor: colors.primary, padding: spacing.xs }
                  : { borderWidth: sizes.hairline, borderColor: colors.rule, padding: spacing.xs + CHOSEN_BORDER - sizes.hairline },
              ]}
            >
              <AppText variant="section-label" color={chosen ? 'primary' : 'ink-2'} style={styles.label}>
                {genderLabels[gender]}
              </AppText>
            </Pressable>
          );
        })}
      </View>
      {error ? (
        <AppText variant="sentence" color="limit-reached">
          {error}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { gap: spacing.sm },
  row: { flexDirection: 'row', gap: spacing.sm },
  option: {
    flex: 1,
    minHeight: OPTION_HEIGHT,
    borderRadius: rounded.none,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { textAlign: 'center' },
});
