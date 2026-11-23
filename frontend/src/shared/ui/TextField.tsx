import { useId, type ComponentRef, type Ref } from 'react';
import { Pressable, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { fontFamilies, rounded, sizes, spacing, textStyles, useTheme } from '../theme';
import { AppText } from './AppText';

export type TextFieldAction = {
  /** Normal case ("Show"); shown in capitals in pen blue (D040). */
  label: string;
  onPress: () => void;
  /** What VoiceOver says, if the label alone is not enough ("Show password"). */
  accessibilityLabel?: string;
};

export type TextFieldProps = Omit<TextInputProps, 'style' | 'placeholderTextColor'> & {
  /** The caption above the line, written in normal case ("Email"); shown as a section label. */
  label: string;
  /** Shown under the line in the limit-reached colour; also read by VoiceOver with the field. */
  error?: string | null;
  /** A pen-blue text action at the end of the line, such as SHOW / HIDE for a password. */
  trailingAction?: TextFieldAction;
  ref?: Ref<ComponentRef<typeof TextInput>>;
};

/** Height of the value row, from the sign-in mockup (D040). */
const ROW_HEIGHT = 40;

/**
 * A fill-in line (D040), like "Signature: ____" on a receipt: a section-label caption, the value in the
 * receipt-line style, a single 1 px ink line under it, no box, square everything.
 */
export function TextField({ label, error, trailingAction, accessibilityLabel, ref, ...inputProps }: TextFieldProps) {
  const { colors } = useTheme();
  const errorId = useId();
  return (
    <View style={styles.field}>
      <AppText variant="section-label" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
      <View style={[styles.row, { borderBottomColor: colors.ink }]}>
        <TextInput
          ref={ref}
          {...inputProps}
          accessibilityLabel={accessibilityLabel ?? label}
          accessibilityHint={error ?? inputProps.accessibilityHint}
          aria-describedby={error ? errorId : undefined}
          placeholderTextColor={colors['ink-2']}
          selectionColor={colors.primary}
          style={[styles.input, { color: colors.ink }]}
        />
        {trailingAction ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={trailingAction.accessibilityLabel ?? trailingAction.label}
            onPress={trailingAction.onPress}
            hitSlop={{ top: (sizes.touchTarget - ROW_HEIGHT) / 2, bottom: (sizes.touchTarget - ROW_HEIGHT) / 2 }}
            style={styles.action}
          >
            <AppText variant="section-label" color="primary">
              {trailingAction.label}
            </AppText>
          </Pressable>
        ) : null}
      </View>
      {error ? (
        <AppText variant="sentence" color="limit-reached" nativeID={errorId}>
          {error}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { gap: spacing.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: ROW_HEIGHT,
    borderBottomWidth: sizes.hairline,
    borderRadius: rounded.none,
  },
  input: {
    flex: 1,
    minWidth: 0,
    minHeight: ROW_HEIGHT,
    padding: 0,
    fontFamily: fontFamilies.mono,
    fontSize: textStyles['receipt-line'].fontSize,
  },
  action: { minHeight: ROW_HEIGHT, justifyContent: 'center', paddingLeft: spacing.md },
});
