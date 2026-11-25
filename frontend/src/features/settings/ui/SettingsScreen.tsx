import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { sizes, spacing } from '@/shared/theme';
import { AppText, DashedRule, Icon, OptionRow, Paper, TextLink } from '@/shared/ui';

import type { Appearance } from '../domain/appearance';
import { useAppearance } from './AppearanceProvider';

/** Written in normal case; shown in capitals by the section-label style (D012, D043). */
const appearanceOptions: readonly { value: Appearance; label: string }[] = [
  { value: 'phone', label: 'Phone' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

/**
 * Settings (D043), opened from the gear on Home: APPEARANCE (Phone, Light, Dark) and the account with
 * SIGN OUT, on plain paper, laid out like Home: a 44 px header with Back, the screen title, sections 24 px
 * apart with a dashed rule between them.
 */
export function SettingsScreen() {
  const { appearance, setAppearance } = useAppearance();
  const { user, signOut } = useSession();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <Paper variant="plain">
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top, paddingBottom: insets.bottom + spacing.xl }}
        testID="settings-scroll"
      >
        <View style={styles.header}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back"
            onPress={() => router.back()}
            style={styles.back}
            testID="settings-back"
          >
            <Icon name="back" />
          </Pressable>
        </View>
        <View style={styles.main}>
          <AppText variant="screen-title" accessibilityRole="header">
            Settings
          </AppText>
          <OptionRow
            caption="Appearance"
            options={appearanceOptions}
            value={appearance}
            onChange={setAppearance}
            testIDPrefix="appearance"
          />
          <DashedRule />
          <View style={styles.account}>
            <AppText variant="section-label">Account</AppText>
            {user ? (
              <AppText variant="meta" testID="settings-email">
                {user.email}
              </AppText>
            ) : null}
            <TextLink label="Sign out" onPress={() => void signOut()} testID="settings-sign-out" />
          </View>
        </View>
      </ScrollView>
    </Paper>
  );
}

const styles = StyleSheet.create({
  // The mirror of Home's header: 12 px padding, so Back's 24 px icon sits about 20 px from the edge.
  header: { minHeight: sizes.touchTarget, paddingLeft: spacing.md, flexDirection: 'row', alignItems: 'center' },
  back: { width: sizes.touchTarget, height: sizes.touchTarget, alignItems: 'center', justifyContent: 'center' },
  main: { paddingTop: spacing.lg, paddingHorizontal: spacing['screen-margin'], gap: spacing.xl },
  account: { gap: spacing.sm },
});
