import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { radius, touchTarget } from '@/shared/theme';
import { LineIcon, type LineIconName, Wordmark } from '@/shared/ui';

/**
 * Home's header (DESIGN.md §4): the wordmark, and on the right the account button, which opens settings
 * (D045), then the bell, each a 44 px button with a 20 px line icon.
 */
export function HomeHeader() {
  const router = useRouter();
  return (
    <View style={styles.header}>
      <Wordmark />
      <View style={styles.actions}>
        <IconButton icon="account" label="Account and settings" onPress={() => router.navigate('/settings')} testID="home-settings" />
        {/* TODO(notifications): no notifications screen exists yet, so the bell does nothing. */}
        <IconButton icon="bell" label="Notifications" testID="home-notifications" />
      </View>
    </View>
  );
}

function IconButton({ icon, label, onPress, testID }: { icon: LineIconName; label: string; onPress?: () => void; testID: string }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.button, { opacity: pressed ? 0.6 : 1 }]}
      testID={testID}
    >
      <LineIcon name={icon} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 12,
    paddingRight: 12,
    paddingBottom: 4,
    paddingLeft: 20,
  },
  actions: { flexDirection: 'row' },
  button: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
});
