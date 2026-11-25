import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { sizes, spacing } from '@/shared/theme';
import { Icon, type IconName, Wordmark } from '@/shared/ui';

/** The small wordmark's artwork has 7 px of air on its left; the mockup pulls it back so FATOURATI lines up. */
const WORDMARK_SMALL_AIR = 7;

/**
 * Home's header (D035, D038, D043): the small highlighted wordmark on the left; on the right the gear, which
 * opens settings, then the bell, 44 px tall. Their 44 pt touch areas sit side by side, so the two 24 px icons
 * are 20 px apart. The right padding is 12 px, so the bell's icon is about 20 px from the edge.
 */
export function HomeHeader() {
  const router = useRouter();
  return (
    <View style={styles.header}>
      <View style={styles.wordmark}>
        <Wordmark size="small" highlighted />
      </View>
      <View style={styles.actions}>
        <HeaderButton
          icon="settings"
          label="Settings"
          onPress={() => router.navigate('/settings')}
          testID="home-settings"
        />
        {/* TODO(notifications): no notifications screen exists yet, so the bell does nothing. */}
        <HeaderButton icon="notifications" label="Notifications" testID="home-notifications" />
      </View>
    </View>
  );
}

function HeaderButton({ icon, label, onPress, testID }: { icon: IconName; label: string; onPress?: () => void; testID: string }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.button} testID={testID}>
      <Icon name={icon} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: sizes.touchTarget,
    paddingLeft: spacing['screen-margin'],
    paddingRight: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  wordmark: { marginLeft: -WORDMARK_SMALL_AIR },
  actions: { flexDirection: 'row' },
  button: {
    width: sizes.touchTarget,
    height: sizes.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
