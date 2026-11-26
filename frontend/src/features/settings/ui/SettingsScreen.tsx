import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useSession } from '@/features/auth/ui/SessionProvider';
import { colors, radius, touchTarget } from '@/shared/theme';
import { AppText, Button, LineIcon, PaperSheet } from '@/shared/ui';

/**
 * Settings (D044, D045), opened from the account button on Home. Not in the design, so it is built from its parts: the
 * receipt screen's top bar (Back, a cap title), a creased sheet with ACCOUNT, the name and the email, and an
 * outlined Sign out button.
 */
export function SettingsScreen() {
  const { user, signOut } = useSession();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top, paddingBottom: insets.bottom + 24 }} testID="settings-scroll">
        <View style={styles.bar}>
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} style={styles.iconButton} testID="settings-back">
            <LineIcon name="back" />
          </Pressable>
          <AppText cap color="ink" accessibilityRole="header">
            Settings
          </AppText>
          <View style={styles.iconButton} />
        </View>

        <PaperSheet on="bg" outerStyle={styles.sheetPlace} style={styles.sheet}>
          <AppText cap color="cobalt">
            Account
          </AppText>
          {user?.firstName ? (
            <AppText weight={600} size={24} tracking={-0.02} style={styles.name}>
              {user.firstName}
            </AppText>
          ) : null}
          {user ? (
            <AppText size={14} color="inkSoft" style={styles.email} testID="settings-email">
              {user.email}
            </AppText>
          ) : null}
        </PaperSheet>

        <View style={styles.actions}>
          <Button kind="secondary" label="Sign out" onPress={() => void signOut()} testID="settings-sign-out" />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  bar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 12, paddingHorizontal: 8, paddingBottom: 4 },
  iconButton: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
  sheetPlace: { marginTop: 6, marginHorizontal: 14 },
  sheet: { paddingTop: 18, paddingHorizontal: 18, paddingBottom: 24 },
  name: { marginTop: 14, lineHeight: 26.5 },
  email: { marginTop: 2 },
  actions: { marginTop: 20, marginHorizontal: 14 },
});
