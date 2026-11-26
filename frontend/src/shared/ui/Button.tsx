import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { colors, radius } from '../theme';
import { AppText } from './AppText';

export type ButtonProps = {
  label: string;
  onPress: () => void;
  /** primary: cobalt fill, white label. secondary: 1 px ink outline (DESIGN.md §4). */
  kind?: 'primary' | 'secondary';
  disabled?: boolean;
  /** While the action runs (signing in): a spinner instead of the label, and presses are ignored. */
  busy?: boolean;
  accessibilityHint?: string;
  testID?: string;
};

/**
 * A button of DESIGN.md §4: full width, 52 px, radius 12, Geist 600 16. Primary is cobalt and turns
 * `cobaltPressed` while pressed; secondary is outlined in ink.
 */
export function Button({ label, onPress, kind = 'primary', disabled = false, busy = false, accessibilityHint, testID }: ButtonProps) {
  const inactive = disabled || busy;
  const primary = kind === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy }}
      disabled={inactive}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.button,
        primary
          ? { backgroundColor: pressed ? colors.cobaltPressed : colors.cobalt }
          : { borderWidth: 1, borderColor: colors.ink, backgroundColor: pressed ? colors.segmentTrack : 'transparent' },
      ]}
    >
      {busy ? (
        <ActivityIndicator color={primary ? colors.white : colors.ink} />
      ) : (
        <AppText weight={600} size={16} color={primary ? 'white' : 'ink'} style={styles.label}>
          {label}
        </AppText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignSelf: 'stretch',
    minHeight: 52,
    borderRadius: radius.button,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  label: { textAlign: 'center' },
});
