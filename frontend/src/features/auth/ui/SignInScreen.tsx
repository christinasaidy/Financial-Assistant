import { useRef, useState, type ComponentRef } from 'react';
import { AccessibilityInfo, type TextInput } from 'react-native';

import { TextField } from '@/shared/ui';

import { hasProblems, validateSignIn } from '../domain/validation';
import { messageForError, problemMessages } from './authMessages';
import { AuthScreenLayout } from './AuthScreenLayout';
import { useSession } from './SessionProvider';
import { useSignedOutAgain } from './useSignedOutAgain';

type Errors = { email: string | null; password: string | null };
const noErrors: Errors = { email: null, password: null };

/**
 * Sign in (design/screens/02-sign-in.png; Forgot? and Continue with Apple wait for the backend, D044). The fields are checked when SIGN IN is pressed, not while typing;
 * a field's message goes away as soon as it is edited. Once signed in, the session moves to the tabs by
 * itself (app/_layout.tsx).
 */
export function SignInScreen() {
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors>(noErrors);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const emailInput = useRef<ComponentRef<typeof TextInput>>(null);
  const passwordInput = useRef<ComponentRef<typeof TextInput>>(null);

  useSignedOutAgain(() => {
    submitting.current = false;
    setBusy(false);
    setPassword('');
  });

  function edit(field: keyof Errors, setValue: (value: string) => void) {
    return (value: string) => {
      setValue(value);
      if (errors[field]) setErrors((current) => ({ ...current, [field]: null }));
      if (formError) setFormError(null);
    };
  }

  async function submit() {
    if (submitting.current) return;
    const problems = validateSignIn({ email, password });
    const found: Errors = {
      email: problems.email ? problemMessages[problems.email] : null,
      password: problems.password ? problemMessages[problems.password] : null,
    };
    setErrors(found);
    setFormError(null);
    if (hasProblems(problems)) {
      (problems.email ? emailInput : passwordInput).current?.focus();
      AccessibilityInfo.announceForAccessibility((found.email ?? found.password) as string);
      return;
    }

    submitting.current = true;
    setBusy(true);
    try {
      await signIn(email, password);
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
      eyebrow="Sign in"
      heading="Let’s flatten these out."
      sentence="Welcome back. Your receipts are where you left them."
      formError={formError}
      submitLabel="Sign in"
      onSubmit={() => void submit()}
      busy={busy}
      switchLink={{ question: 'New to Fatourati?', label: 'Create an account', href: '/sign-up' }}
    >
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
      <TextField
        ref={passwordInput}
        label="Password"
        value={password}
        onChangeText={edit('password', setPassword)}
        error={errors.password}
        password
        textContentType="password"
        autoComplete="current-password"
        autoCapitalize="none"
        autoCorrect={false}
        spellCheck={false}
        returnKeyType="go"
        onSubmitEditing={() => void submit()}
      />
    </AuthScreenLayout>
  );
}
