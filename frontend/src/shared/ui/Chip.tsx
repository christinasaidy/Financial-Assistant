import { Pressable, StyleSheet } from 'react-native';

import { colors, radius } from '../theme';
import { AppText } from './AppText';

type Props = {
  label: string;
  onPress: () => void;
  /** Chosen: ink with light text, like the user's chat bubble (D046). */
  selected?: boolean;
  /** 'radio' when it is a choice (the default), 'button' when it does something (the Assistant's suggestions). */
  role?: 'radio' | 'button';
  /** The Receipts filter chips are a little smaller: 38 px, radius 19 (design/reference/13). */
  compact?: boolean;
  testID?: string;
};

/**
 * The suggestion chip of the Assistant screen (design/reference/07): 40 px tall, radius 20, 1 px outline,
 * Geist 500 14. Used as a choice (the budget form's categories), so it is a radio for VoiceOver.
 */
export function Chip({ label, onPress, selected = false, role = 'radio', compact = false, testID }: Props) {
  return (
    <Pressable
      accessibilityRole={role}
      accessibilityLabel={label}
      accessibilityState={role === 'radio' ? { checked: selected } : undefined}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.chip,
        compact ? styles.compact : null,
        selected ? styles.selected : { backgroundColor: pressed ? colors.segmentTrack : 'transparent' },
      ]}
    >
      <AppText weight={500} size={14} color={selected ? 'userBubbleText' : 'ink'}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    minHeight: 40,
    paddingHorizontal: 14,
    borderRadius: radius.chip,
    borderWidth: 1,
    borderColor: colors.chipBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compact: { minHeight: 38, borderRadius: 19 },
  selected: { backgroundColor: colors.ink, borderColor: colors.ink },
});
