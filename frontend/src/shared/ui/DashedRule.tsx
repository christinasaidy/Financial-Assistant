import { View, type StyleProp, type ViewStyle } from 'react-native';
import Svg, { Line } from 'react-native-svg';

import { sizes, useTheme } from '../theme';

type Props = {
  /** Margins around the rule (24 px above and below between sections, D031). */
  style?: StyleProp<ViewStyle>;
};

/**
 * The receipt's tear line (D032): dashed, 1 px, 4 on and 3 off, in `rule`. Between sections and between
 * receipt rows. Decoration only, so VoiceOver skips it. React Native's own dashed border cannot set the
 * dash length, so it is drawn with SVG.
 */
export function DashedRule({ style }: Props) {
  const { colors } = useTheme();
  return (
    <View
      style={[{ height: sizes.hairline, alignSelf: 'stretch' }, style]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      testID="dashed-rule"
    >
      <Svg width="100%" height={sizes.hairline}>
        <Line
          x1={0}
          y1={sizes.hairline / 2}
          x2="100%"
          y2={sizes.hairline / 2}
          stroke={colors.rule}
          strokeWidth={sizes.hairline}
          strokeDasharray={[sizes.dashOn, sizes.dashOff]}
        />
      </Svg>
    </View>
  );
}
