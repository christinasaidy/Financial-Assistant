import { Pressable } from 'react-native';

import { sizes, textStyles } from '../theme';
import { AppText } from './AppText';

/** Grows the 16 px label line to Apple's 44 pt touch height without moving it (the mockups' 14 px padding). */
const SLOP = (sizes.touchTarget - textStyles['section-label'].lineHeight) / 2;

type Props = {
  /** Normal case; shown in capitals by the section-label style. */
  label: string;
  onPress: () => void;
  testID?: string;
};

/** A pen-blue link in the section-label style: SEE ALL, SET A BUDGET, TRY AGAIN, SIGN OUT (D018, D035, D037, D043). */
export function TextLink({ label, onPress, testID }: Props) {
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={{ top: SLOP, bottom: SLOP }}
      style={{ alignSelf: 'flex-start' }}
      testID={testID}
    >
      <AppText variant="section-label" color="primary">
        {label}
      </AppText>
    </Pressable>
  );
}
