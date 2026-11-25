import { Link, type Href } from 'expo-router';
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { spacing, type SpacingToken } from '@/shared/theme';
import { AppText, Button, Paper, Wordmark } from '@/shared/ui';

/**
 * The large wordmark's artwork has a little space on its left; the mockups pull it back by 12 px so the
 * letters line up with the screen margin (see Wordmark).
 */
const WORDMARK_PULL = -12;

/** A link's text is 16 px tall; this grows its touch area to 44 px (sizes.touchTarget). */
const LINK_SLOP = { top: 14, bottom: 14, left: spacing.sm, right: spacing.sm };

export type SwitchLinkProps = {
  /** The grey sentence before the link ("New to Fatourati?"). */
  question: string;
  /** The link, in normal case ("Create an account"); shown in capitals in pen blue. */
  label: string;
  href: Href;
  /** Go back to the screen if it is already in the stack, instead of stacking another copy. */
  dismissTo?: boolean;
};

type Props = {
  /** The screen title, normal case ("Sign in"). */
  title: string;
  /** The one grey sentence under the title. */
  sentence: string;
  /** Space between the safe area and the wordmark (the mockups: 112 px for sign in, 96 for create account). */
  top: SpacingToken;
  /** The fields. */
  children: ReactNode;
  /** About the whole form (wrong password, no connection); shown above the button. */
  formError: string | null;
  submitLabel: string;
  onSubmit: () => void;
  busy: boolean;
  switchLink: SwitchLinkProps;
};

/**
 * What sign in and create account share (D040): plain paper (D042), the large highlighted
 * wordmark, the title, one grey sentence, the fields, the main button, and the link to the other screen
 * at the bottom. The content scrolls, so large text sizes and the keyboard never cut anything off.
 */
export function AuthScreenLayout({ title, sentence, top, children, formError, submitLabel, onSubmit, busy, switchLink }: Props) {
  const insets = useSafeAreaInsets();
  return (
    <Paper variant="plain">
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          style={styles.fill}
          contentContainerStyle={[
            styles.content,
            { paddingTop: insets.top + spacing[top], paddingBottom: insets.bottom + spacing.lg },
          ]}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
        >
          <View style={styles.wordmark}>
            <Wordmark size="large" highlighted />
          </View>
          <AppText variant="screen-title" accessibilityRole="header" style={styles.title}>
            {title}
          </AppText>
          <AppText variant="sentence" color="ink-2" style={styles.sentence}>
            {sentence}
          </AppText>

          <View style={styles.fields}>{children}</View>

          {formError ? (
            <AppText variant="sentence" color="limit-reached" accessibilityLiveRegion="polite" style={styles.formError}>
              {formError}
            </AppText>
          ) : null}

          <View style={styles.button}>
            <Button label={submitLabel} onPress={onSubmit} busy={busy} />
          </View>

          <SwitchLink {...switchLink} />
        </ScrollView>
      </KeyboardAvoidingView>
    </Paper>
  );
}

/** "New to Fatourati? CREATE AN ACCOUNT": a grey sentence and a pen-blue link, centred, wrapping if needed. */
function SwitchLink({ question, label, href, dismissTo = false }: SwitchLinkProps) {
  return (
    <View style={styles.switch}>
      <AppText variant="sentence" color="ink-2" style={styles.switchText}>
        {question}
      </AppText>
      <Link href={href} dismissTo={dismissTo} asChild>
        <Pressable accessibilityRole="link" accessibilityLabel={label} hitSlop={LINK_SLOP}>
          <AppText variant="section-label" color="primary" style={styles.switchText}>
            {label}
          </AppText>
        </Pressable>
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { flexGrow: 1, paddingHorizontal: spacing['screen-margin'] },
  wordmark: { marginLeft: WORDMARK_PULL },
  title: { marginTop: spacing['2xl'] },
  sentence: { marginTop: spacing.sm },
  fields: { marginTop: spacing['2xl'], gap: spacing.xl },
  formError: { marginTop: spacing.xl },
  button: { marginTop: spacing['2xl'] },
  // marginTop auto keeps the link at the bottom of a tall screen; the padding keeps it off the button on a
  // short one (or at large text sizes, where everything scrolls).
  switch: {
    marginTop: 'auto',
    paddingTop: spacing.xl,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    alignItems: 'baseline',
    columnGap: spacing.xs,
  },
  switchText: { textAlign: 'center' },
});
