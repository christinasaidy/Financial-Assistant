import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Svg, { Polygon } from 'react-native-svg';

import { useTheme } from '../theme';

/**
 * The corners of the yellow highlighter swipe, in percent of its box, copied from the mockups' clip-paths
 * (the edges are slightly uneven, like a real highlighter stroke).
 */
const SHAPES = {
  /** Behind the wordmark: clip-path polygon(0 8%, 100% 0, 99% 94%, 1% 100%). */
  wordmark: '0,8 100,0 99,94 1,100',
  /** Behind the selected tab's label: clip-path polygon(0 10%, 100% 0, 98% 92%, 2% 100%). */
  tab: '0,10 100,0 98,92 2,100',
} as const;

export type HighlightShape = keyof typeof SHAPES;

type Props = {
  shape: HighlightShape;
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
};

/**
 * The brand yellow (D038) drawn as a flat SVG polygon behind its children. Only for the wordmark and the
 * selected tab; whatever sits on it must be ink #1c1d21 (AppText color="on-highlight").
 */
export function HighlightSwipe({ shape, children, style }: Props) {
  const { colors } = useTheme();
  return (
    <View style={style}>
      <Svg
        style={StyleSheet.absoluteFill}
        width="100%"
        height="100%"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        pointerEvents="none"
        testID="highlight-swipe"
      >
        <Polygon points={SHAPES[shape]} fill={colors.highlight} />
      </Svg>
      {children}
    </View>
  );
}
