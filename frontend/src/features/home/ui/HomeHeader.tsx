import { Pressable, StyleSheet, View } from 'react-native';

import { sizes, spacing } from '@/shared/theme';
import { Icon, Wordmark } from '@/shared/ui';

/** The small wordmark's artwork has 7 px of air on its left; the mockup pulls it back so FATOURATI lines up. */
const WORDMARK_SMALL_AIR = 7;

/**
 * Home's header (D035, D038): the small highlighted wordmark on the left, the bell on the right, 44 px tall.
 * The right padding is 12 px, so the bell's 44 pt touch area keeps its 24 px icon about 20 px from the edge.
 */
export function HomeHeader() {
  return (
    <View style={styles.header}>
      <View style={styles.wordmark}>
        <Wordmark size="small" highlighted />
      </View>
      {/* TODO(notifications): no notifications screen exists yet, so the bell does nothing. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Notifications"
        style={styles.bell}
        testID="home-notifications"
      >
        <Icon name="notifications" />
      </Pressable>
    </View>
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
  bell: {
    width: sizes.touchTarget,
    height: sizes.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
