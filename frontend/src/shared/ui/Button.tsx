import { Pressable, StyleSheet, View } from 'react-native';

import { rounded, sizes, spacing, useTheme } from '../theme';
import { AppText } from './AppText';
import { Icon, type IconName } from './Icon';

export type ButtonProps = {
  /** Written in normal case; the total-line style shows it in capitals (D012). */
  label: string;
  onPress: () => void;
  /** 16 px, one Mono character (0.6 em) before the label (D027, D037). */
  icon?: IconName;
  disabled?: boolean;
  /** Read by VoiceOver while the action runs (e.g. signing in); presses are ignored meanwhile. */
  busy?: boolean;
  accessibilityHint?: string;
  testID?: string;
};

/** The label's gap to the icon: one Mono character at the total-line size, 0.6 em of 16 px (D027). */
const ICON_GAP = 0.6 * 16;

/**
 * The main button (D037): full width, 48 px, square, pen-blue fill, paper-coloured label in the
 * total-line style. One per screen.
 *
 * Pressed, disabled and busy LOOKS are not designed yet (see README "Open questions"): for now they only
 * change behaviour and what VoiceOver says.
 */
export function Button({ label, onPress, icon, disabled = false, busy = false, accessibilityHint, testID }: ButtonProps) {
  const { colors } = useTheme();
  const inactive = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy }}
      disabled={inactive}
      onPress={onPress}
      testID={testID}
      style={[styles.button, { backgroundColor: colors.primary }]}
    >
      <View style={styles.content}>
        {icon ? (
          <View style={styles.icon}>
            <Icon name={icon} size={sizes.buttonIcon} color="paper" />
          </View>
        ) : null}
        <AppText variant="total-line" color="paper" style={styles.label}>
          {label}
        </AppText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignSelf: 'stretch',
    minHeight: sizes.button,
    borderRadius: rounded.none,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
  },
  content: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  icon: { marginRight: ICON_GAP },
  label: { textAlign: 'center', flexShrink: 1 },
});
