import { useState, type ReactNode } from 'react';
import { StyleSheet, View, type LayoutChangeEvent, type StyleProp, type ViewStyle } from 'react-native';
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
  // The swipe is drawn at the size the box measured, never at a percentage: on iOS a percentage-sized Svg
  // can come out larger than its box and spill over the icon and the next tab. The box also clips it.
  const [box, setBox] = useState({ width: 0, height: 0 });
  const measure = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setBox((old) => (old.width === width && old.height === height ? old : { width, height }));
  };
  return (
    <View style={[styles.clip, style]} onLayout={measure}>
      <Svg
        style={styles.swipe}
        width={box.width}
        height={box.height}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        pointerEvents="none"
        testID="highlight-swipe"
      >
        <Polygon points={SHAPES[shape]} fill={colors.highlight} />
      </Svg>
      {/* Its own box, so the children paint above the absolutely placed swipe on every platform (on the
          web an absolutely placed element otherwise paints over its plain siblings). */}
      <View>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  clip: { overflow: 'hidden' },
  swipe: { position: 'absolute', top: 0, left: 0 },
});
