import { useId, useState, type ComponentRef, type Ref } from 'react';
import { Pressable, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { colors, fonts, touchTarget } from '../theme';
import { AppText } from './AppText';
import { LineIcon } from './Icon';

export type TextFieldProps = Omit<TextInputProps, 'style' | 'placeholderTextColor'> & {
  /** The capital label above the field, written in normal case ("Email"). */
  label: string;
  /** Shown under the line; also read by VoiceOver with the field. */
  error?: string | null;
  /** A password field: the eye button inside the field shows or hides it. */
  password?: boolean;
  ref?: Ref<ComponentRef<typeof TextInput>>;
};

/**
 * A field of the sign-in form (design/reference/02-sign-in.html): a cap label, a 46 px field with a 1 px
 * line under it (2 px cobalt while focused), Geist 16 text, and for a password an eye button inside.
 */
export function TextField({ label, error, password = false, accessibilityLabel, ref, onFocus, onBlur, ...inputProps }: TextFieldProps) {
  const errorId = useId();
  const [focused, setFocused] = useState(false);
  const [shown, setShown] = useState(false);
  return (
    <View>
      <AppText cap color="fieldLabel" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </AppText>
      <View
        style={[
          styles.row,
          focused ? { borderBottomWidth: 2, borderBottomColor: colors.cobalt } : { borderBottomWidth: 1, borderBottomColor: colors.fieldLine },
        ]}
      >
        <TextInput
          ref={ref}
          {...inputProps}
          secureTextEntry={password && !shown}
          accessibilityLabel={accessibilityLabel ?? label}
          accessibilityHint={error ?? inputProps.accessibilityHint}
          aria-describedby={error ? errorId : undefined}
          placeholderTextColor={colors.placeholder}
          selectionColor={colors.cobalt}
          onFocus={(event) => {
            setFocused(true);
            onFocus?.(event);
          }}
          onBlur={(event) => {
            setFocused(false);
            onBlur?.(event);
          }}
          style={styles.input}
        />
        {password ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={shown ? 'Hide password' : 'Show password'}
            onPress={() => setShown((value) => !value)}
            style={styles.eye}
          >
            <LineIcon name="eye" color="capOnForm" />
          </Pressable>
        ) : null}
      </View>
      {error ? (
        <AppText size={13} color="redText" nativeID={errorId} style={styles.error}>
          {error}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', minHeight: 46 },
  input: {
    flex: 1,
    minWidth: 0,
    minHeight: 45,
    paddingVertical: 0,
    paddingLeft: 2,
    fontFamily: fonts.sans.regular,
    fontSize: 16,
    color: colors.ink,
  },
  eye: { width: touchTarget, height: touchTarget, alignItems: 'center', justifyContent: 'center' },
  error: { marginTop: 6 },
});
