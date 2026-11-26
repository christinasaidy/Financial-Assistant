import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { radius, touchTarget } from '@/shared/theme';
import { LineIcon, Wordmark } from '@/shared/ui';

/**
 * Home's header (DESIGN.md §4): the wordmark, and the bell in a 44 px button on the right. The design has
 * no settings button, so the wordmark opens settings (D044).
 */
export function HomeHeader() {
  const router = useRouter();
  return (
    <View style={styles.header}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Fatourati"
        accessibilityHint="Opens settings"
        onPress={() => router.navigate('/settings')}
        hitSlop={{ top: 12, bottom: 12, right: 12 }}
        style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}
        testID="home-settings"
      >
        <Wordmark />
      </Pressable>
      {/* TODO(notifications): no notifications screen exists yet, so the bell does nothing. */}
      <Pressable accessibilityRole="button" accessibilityLabel="Notifications" style={styles.bell} testID="home-notifications">
        <LineIcon name="bell" />
      </Pressable>
    </View>
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
  bell: { width: touchTarget, height: touchTarget, borderRadius: radius.button, alignItems: 'center', justifyContent: 'center' },
});
