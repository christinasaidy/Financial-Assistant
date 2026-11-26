import { Pressable, StyleSheet } from 'react-native';

import { colors, radius } from '../theme';
import { AppText } from './AppText';

type Props = {
  label: string;
  onPress: () => void;
  /** Chosen: ink with light text, like the user's chat bubble (D046). */
  selected?: boolean;
  testID?: string;
};

/**
 * The suggestion chip of the Assistant screen (design/reference/07): 40 px tall, radius 20, 1 px outline,
 * Geist 500 14. Used as a choice (the budget form's categories), so it is a radio for VoiceOver.
 */
export function Chip({ label, onPress, selected = false, testID }: Props) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.chip,
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
  selected: { backgroundColor: colors.ink, borderColor: colors.ink },
});
