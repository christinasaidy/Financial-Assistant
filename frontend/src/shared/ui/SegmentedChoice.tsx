import { Pressable, StyleSheet, View } from 'react-native';

import { colors, radius } from '../theme';
import { AppText } from './AppText';

export type Choice<T extends string> = { value: T; label: string };

type Props<T extends string> = {
  /** The cap label above, normal case ("Gender"); also the group's name for VoiceOver. */
  label: string;
  choices: readonly Choice<T>[];
  value: T | null;
  onChange: (value: T) => void;
  /** Shown under the switch, like a field's error. */
  error?: string | null;
  /** Each choice gets the test id `${testIDPrefix}-${value}`. */
  testIDPrefix: string;
};

/**
 * The segmented switch of the Assistant screen (design/reference/07): a track of rgba(0,0,0,.06), radius
 * 12, 3 px padding; the chosen segment is clean paper with a 1 px shadow, Geist 600 14; the others Geist
 * 500 14. A radio group for VoiceOver. Used for the gender question of create account.
 */
export function SegmentedChoice<T extends string>({ label, choices, value, onChange, error, testIDPrefix }: Props<T>) {
  return (
    <View>
      <AppText cap color="fieldLabel" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
      <View accessibilityRole="radiogroup" accessibilityLabel={label} style={styles.track}>
        {choices.map((choice, index) => {
          const chosen = choice.value === value;
          return (
            <Pressable
              key={choice.value}
              accessibilityRole="radio"
              accessibilityLabel={choice.label}
              accessibilityHint={error ?? `${index + 1} of ${choices.length}`}
              accessibilityState={{ checked: chosen }}
              onPress={() => onChange(choice.value)}
              testID={`${testIDPrefix}-${choice.value}`}
              style={[styles.segment, chosen ? styles.chosen : null]}
            >
              <AppText weight={chosen ? 600 : 500} size={14} color={chosen ? 'ink' : 'fieldLabel'} style={styles.text}>
                {choice.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
      {error ? (
        <AppText size={13} color="redText" style={styles.error}>
          {error}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    marginTop: 10,
    flexDirection: 'row',
    padding: 3,
    borderRadius: radius.button,
    backgroundColor: colors.segmentTrack,
  },
  segment: { flex: 1, minHeight: 44, borderRadius: 9, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  chosen: {
    backgroundColor: colors.paperClean,
    shadowColor: '#000000',
    shadowOpacity: 0.12,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
  },
  text: { textAlign: 'center' },
  error: { marginTop: 6 },
});
