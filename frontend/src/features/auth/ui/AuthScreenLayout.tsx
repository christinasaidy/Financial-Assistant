import { Link, type Href } from 'expo-router';
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors } from '@/shared/theme';
import { AppText, Button, PaperSheet, Wordmark } from '@/shared/ui';

import { ReceiptSlips } from './ReceiptSlips';

export type SwitchLinkProps = {
  /** The sentence before the link ("New to Fatourati?"). */
  question: string;
  /** The cobalt link ("Create an account"). */
  label: string;
  href: Href;
  /** Go back to the screen if it is already in the stack, instead of stacking another copy. */
  dismissTo?: boolean;
};

type Props = {
  /** The cobalt cap label at the top of the form sheet ("Sign in"). */
  eyebrow: string;
  /** The heading ("Let’s flatten these out."). */
  heading: string;
  /** The sentence under the heading. */
  sentence: string;
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
 * The reference places the wordmark 22 px from the top of a screen drawn without a status bar; here it sits
 * 8 px under the safe area, and the slips move down with it.
 */
const TOP_SHIFT = 8 - 22;
/** Where the form sheet starts in the reference (the slips run on under it to 330 px). */
const FORM_TOP = 282;

/**
 * What sign in and create account share (design/screens/02-sign-in.png): on the grey background, the
 * wordmark and four crumpled receipt slips; below, the clean form sheet (`paperClean`, almost no crease,
 * straight top edge, a shadow above it) with the cobalt cap label, the heading, one sentence, the fields,
 * the cobalt button and the link to the other screen at the bottom. Everything scrolls, so the keyboard and
 * large text sizes never cut anything off.
 */
export function AuthScreenLayout({ eyebrow, heading, sentence, children, formError, submitLabel, onSubmit, busy, switchLink }: Props) {
  const insets = useSafeAreaInsets();
  const shift = insets.top + TOP_SHIFT;
  return (
    <View style={styles.screen}>
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView style={styles.fill} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive">
          <View style={{ height: FORM_TOP + shift }}>
            <View style={[styles.wordmark, { top: 22 + shift }]}>
              <Wordmark />
            </View>
            <ReceiptSlips top={shift} />
          </View>

          <PaperSheet
            color="paperClean"
            crease={0.15}
            creaseTileWidth={520}
            tear={null}
            shadow={styles.formShadow}
            outerStyle={styles.formPlace}
            style={[styles.form, { paddingBottom: 22 + insets.bottom }]}
          >
            <View style={styles.between}>
              <AppText cap color="cobalt">
                {eyebrow}
              </AppText>
              <AppText cap color="capOnForm" accessibilityElementsHidden importantForAccessibility="no">
                Nº ————
              </AppText>
            </View>
            <AppText weight={600} size={25} tracking={-0.02} accessibilityRole="header" style={styles.heading}>
              {heading}
            </AppText>
            <AppText size={15} color="formSoft" style={styles.sentence}>
              {sentence}
            </AppText>

            <View style={styles.fields}>{children}</View>

            {formError ? (
              <AppText size={14} color="redText" accessibilityLiveRegion="polite" style={styles.formError}>
                {formError}
              </AppText>
            ) : null}

            <View style={styles.button}>
              <Button label={submitLabel} onPress={onSubmit} busy={busy} />
            </View>

            <SwitchLink {...switchLink} />
          </PaperSheet>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

/** "New to Fatourati? Create an account": 14.5 px, the link in cobalt 600, centred, wrapping if needed. */
function SwitchLink({ question, label, href, dismissTo = false }: SwitchLinkProps) {
  return (
    <View style={styles.switch}>
      <AppText size={14.5} color="formSoft">
        {question}
      </AppText>
      <Link href={href} dismissTo={dismissTo} asChild>
        <Pressable accessibilityRole="link" accessibilityLabel={label} hitSlop={{ top: 14, bottom: 14, left: 8, right: 8 }}>
          <AppText size={14.5} weight={600} color="cobalt">
            {label}
          </AppText>
        </Pressable>
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  fill: { flex: 1 },
  content: { flexGrow: 1 },
  wordmark: { position: 'absolute', left: 20, zIndex: 3 },
  formPlace: { flexGrow: 1, zIndex: 2 },
  formShadow: {
    shadowColor: 'rgb(30,30,35)',
    shadowOpacity: 0.16,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: -8 },
  },
  form: { flexGrow: 1, paddingTop: 30, paddingHorizontal: 22 },
  between: { flexDirection: 'row', justifyContent: 'space-between' },
  heading: { marginTop: 14, marginBottom: 4, lineHeight: 27.5 },
  sentence: { lineHeight: 21, marginBottom: 14 },
  fields: { gap: 22 },
  formError: { marginTop: 16, lineHeight: 19 },
  button: { marginTop: 20 },
  // marginTop auto keeps the link at the bottom of a tall screen; the padding keeps it off the button.
  switch: {
    marginTop: 'auto',
    paddingTop: 28,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    alignItems: 'baseline',
    columnGap: 4,
  },
});
