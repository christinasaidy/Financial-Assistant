import { Pressable, StyleSheet, View } from 'react-native';

import { rounded, sizes, spacing, useTheme } from '../theme';
import { AppText } from './AppText';

/** Height of an option (D041). */
const OPTION_HEIGHT = 48;
/** The chosen option's border (D041). */
const CHOSEN_BORDER = 2;

export type Option<T extends string> = {
  value: T;
  /** Normal case; shown in capitals by the section-label style (D012). */
  label: string;
};

type Props<T extends string> = {
  /** The caption above the options, normal case ("Gender"); also the radio group's name for VoiceOver. */
  caption: string;
  options: readonly Option<T>[];
  value: T | null;
  onChange: (value: T) => void;
  /** Shown under the options in the same style as a field's error. */
  error?: string | null;
  /** Each option gets the test id `${testIDPrefix}-${value}`. */
  testIDPrefix: string;
};

/**
 * A choice of a few equal square options in one row under a caption (D041, D043): gender on create account,
 * appearance in settings. Each option has a 1 px `rule` border; the chosen one a 2 px pen-blue border and a
 * pen-blue label, because it is something the user changes (D018). A radio group for VoiceOver:
 * "Female, radio button, checked, 1 of 3".
 *
 * The thicker border is drawn without moving the label: each option keeps 2 px of border plus padding, and
 * the 1 px border gets 1 px more padding.
 */
export function OptionRow<T extends string>({ caption, options, value, onChange, error, testIDPrefix }: Props<T>) {
  const { colors } = useTheme();
  return (
    <View style={styles.field}>
      {/* Read by VoiceOver before the options, so each option can be just its name. */}
      <AppText variant="section-label">{caption}</AppText>
      <View accessibilityRole="radiogroup" accessibilityLabel={caption} style={styles.row}>
        {options.map((option, index) => {
          const chosen = option.value === value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityLabel={option.label}
              accessibilityHint={error ?? `${index + 1} of ${options.length}`}
              accessibilityState={{ checked: chosen }}
              onPress={() => onChange(option.value)}
              testID={`${testIDPrefix}-${option.value}`}
              style={[
                styles.option,
                chosen
                  ? { borderWidth: CHOSEN_BORDER, borderColor: colors.primary, padding: spacing.xs }
                  : { borderWidth: sizes.hairline, borderColor: colors.rule, padding: spacing.xs + CHOSEN_BORDER - sizes.hairline },
              ]}
            >
              <AppText variant="section-label" color={chosen ? 'primary' : 'ink-2'} style={styles.label}>
                {option.label}
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
