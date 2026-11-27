import { Pressable, type ViewStyle } from 'react-native';

import { touchTarget } from '../theme';
import { AppText } from './AppText';

type Props = {
  label: string;
  onPress: () => void;
  /** 14 with weight 500 ("See all"); the sign-in screens use 14.5 and 600. */
  size?: number;
  weight?: 500 | 600;
  /** Where it sits across its parent: at the start by default; "center" in a row such as RECENT RECEIPTS. */
  align?: ViewStyle['alignSelf'];
  testID?: string;
};

/** A cobalt text link: "See all", "Create an account", "Try again" (DESIGN.md: links are cobalt). */
export function TextLink({ label, onPress, size = 14, weight = 500, align = 'flex-start', testID }: Props) {
  const slop = Math.max(0, (touchTarget - size * 1.3) / 2);
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={{ top: slop, bottom: slop }}
      style={({ pressed }) => ({ alignSelf: align, opacity: pressed ? 0.7 : 1 })}
      testID={testID}
    >
      <AppText weight={weight} size={size} color="cobalt">
        {label}
      </AppText>
    </Pressable>
  );
}
