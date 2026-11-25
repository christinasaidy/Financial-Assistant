import { useRef, useState, type ComponentRef } from 'react';
import { AccessibilityInfo, Keyboard, StyleSheet, View, type TextInput } from 'react-native';

import { spacing } from '@/shared/theme';
import { AppText, TextField } from '@/shared/ui';

import type { Gender } from '../domain/types';
import { hasProblems, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, validateSignUp } from '../domain/validation';
import { messageForError, passwordHint, problemMessages } from './authMessages';
import { AuthScreenLayout } from './AuthScreenLayout';
import { GenderChoice } from './GenderChoice';
import { useSession } from './SessionProvider';
import { useSignedOutAgain } from './useSignedOutAgain';

type Field = 'firstName' | 'email' | 'password' | 'gender';
type Errors = Record<Field, string | null>;
const noErrors: Errors = { firstName: null, email: null, password: null, gender: null };
/** Top to bottom, as on screen. */
const fieldOrder: readonly Field[] = ['firstName', 'email', 'password', 'gender'];

/** iOS's strong-password suggestion follows the backend's limits. */
const PASSWORD_RULES = `minlength: ${MIN_PASSWORD_LENGTH}; maxlength: ${MAX_PASSWORD_LENGTH};`;

/**
 * Create account (D040, D041, mockup CreateAccount): first name, email, password and gender, all required.
 * Checked when CREATE ACCOUNT is pressed, not while typing; a field's message goes away as soon as it is
 * edited. On success the account is signed in and the session moves to the tabs by itself.
 */
export function SignUpScreen() {
  const { signUp } = useSession();
  const [firstName, setFirstName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [gender, setGender] = useState<Gender | null>(null);
  const [passwordShown, setPasswordShown] = useState(false);
  const [errors, setErrors] = useState<Errors>(noErrors);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const firstNameInput = useRef<ComponentRef<typeof TextInput>>(null);
  const emailInput = useRef<ComponentRef<typeof TextInput>>(null);
  const passwordInput = useRef<ComponentRef<typeof TextInput>>(null);

  useSignedOutAgain(() => {
    submitting.current = false;
    setBusy(false);
    setPassword('');
    setPasswordShown(false);
  });

  function clear(field: Field) {
    if (errors[field]) setErrors((current) => ({ ...current, [field]: null }));
    if (formError) setFormError(null);
  }

  function edit(field: Exclude<Field, 'gender'>, setValue: (value: string) => void) {
    return (value: string) => {
      setValue(value);
      clear(field);
    };
  }

  async function submit() {
    if (submitting.current) return;
    const problems = validateSignUp({ firstName, email, password, gender });
    const found: Errors = {
      firstName: problems.firstName ? problemMessages[problems.firstName] : null,
      email: problems.email ? problemMessages[problems.email] : null,
      password: problems.password ? problemMessages[problems.password] : null,
      gender: problems.gender ? problemMessages[problems.gender] : null,
    };
    setErrors(found);
    setFormError(null);
    // `!gender` is implied by the problems; it is repeated so TypeScript knows gender is set below.
    if (hasProblems(problems) || !gender) {
      // Move to the first field to fix (the keyboard closes if it is the gender) and say what is wrong.
      const first = fieldOrder.find((field) => found[field]) ?? 'gender';
      const inputs = { firstName: firstNameInput, email: emailInput, password: passwordInput };
      if (first === 'gender') Keyboard.dismiss();
      else inputs[first].current?.focus();
      AccessibilityInfo.announceForAccessibility(found[first] ?? problemMessages['gender-missing']);
      return;
    }

    submitting.current = true;
    setBusy(true);
    try {
      await signUp({ firstName, email, password, gender });
      // Signed in: this screen is about to be replaced by the tabs, so it stays busy until then.
    } catch (error) {
      const { field, message } = messageForError(error);
      if (field === 'email') setErrors({ ...noErrors, email: message });
      else setFormError(message);
      AccessibilityInfo.announceForAccessibility(message);
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <AuthScreenLayout
      title="Create account"
      sentence="Keep every receipt in one place, in dollars and pounds."
      top="2xl"
      formError={formError}
      submitLabel="Create account"
      onSubmit={() => void submit()}
      busy={busy}
      switchLink={{ question: 'Already have an account?', label: 'Sign in', href: '/sign-in', dismissTo: true }}
    >
      <TextField
        ref={firstNameInput}
        label="First name"
        value={firstName}
        onChangeText={edit('firstName', setFirstName)}
        error={errors.firstName}
        textContentType="givenName"
        autoComplete="given-name"
        autoCapitalize="words"
        autoCorrect={false}
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => emailInput.current?.focus()}
      />
      <TextField
        ref={emailInput}
        label="Email"
        value={email}
        onChangeText={edit('email', setEmail)}
        error={errors.email}
        placeholder="name@example.com"
        keyboardType="email-address"
        textContentType="username"
        autoComplete="email"
        autoCapitalize="none"
        autoCorrect={false}
        spellCheck={false}
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => passwordInput.current?.focus()}
      />
      {/* The hint sits under the line like a field's message, and gives way to the message when there is one. */}
      <View style={styles.passwordField}>
        <TextField
          ref={passwordInput}
          label="Password"
          value={password}
          onChangeText={edit('password', setPassword)}
          error={errors.password}
          accessibilityHint={passwordHint}
          secureTextEntry={!passwordShown}
          textContentType="newPassword"
          passwordRules={PASSWORD_RULES}
          autoComplete="new-password"
          autoCapitalize="none"
          autoCorrect={false}
          spellCheck={false}
          // Gender is not a text field: with it chosen, the return key creates the account; without, it
          // closes the keyboard so the options can be seen.
          returnKeyType={gender ? 'go' : 'done'}
          onSubmitEditing={() => (gender ? void submit() : Keyboard.dismiss())}
          trailingAction={{
            label: passwordShown ? 'Hide' : 'Show',
            accessibilityLabel: passwordShown ? 'Hide password' : 'Show password',
            onPress: () => setPasswordShown((shown) => !shown),
          }}
        />
        {errors.password ? null : (
          <AppText variant="meta" importantForAccessibility="no" accessibilityElementsHidden>
            {passwordHint}
          </AppText>
        )}
      </View>
      <GenderChoice
        value={gender}
        onChange={(chosen) => {
          setGender(chosen);
          clear('gender');
        }}
        error={errors.gender}
      />
    </AuthScreenLayout>
  );
}

const styles = StyleSheet.create({
  passwordField: { gap: spacing.xs },
});
