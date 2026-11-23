import { View } from 'react-native';

import { inkOnHighlight, useTheme } from '../theme';
import { ArtSvg } from './art/ArtSvg';
import { wordmarkArt } from './art/wordmarkArt.generated';
import { HighlightSwipe } from './HighlightSwipe';

export type WordmarkProps = {
  /** large: 48 px type, launch and sign in (284 x 59). small: 20 px type, the Home header (118 x 25). D029. */
  size: 'large' | 'small';
  /** The yellow swipe behind it (D038): sign in, create account and the Home header. */
  highlighted?: boolean;
  /**
   * Force ink #1c1d21, for a wordmark sitting on yellow paper without its own swipe (the launch screen).
   * Highlighted wordmarks are always ink; otherwise it follows the theme's ink.
   */
  onYellow?: boolean;
};

/**
 * FATOURATI, drawn once in Figma with its printed look (D010, D029), read by VoiceOver as "Fatourati".
 * The artwork has a little space on its left, which the mockups pull back with a negative margin
 * (-12 px large, -7 px small) so the letters line up with the 20 px screen margin.
 */
export function Wordmark({ size, highlighted = false, onYellow = false }: WordmarkProps) {
  const { colors } = useTheme();
  const art = wordmarkArt[size];
  const width = Number(art.props.width);
  const height = Number(art.props.height);
  const color = highlighted || onYellow ? inkOnHighlight : colors.ink;
  const drawing = <ArtSvg art={art} width={width} height={height} color={color} />;

  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel="Fatourati"
      style={{ width, height, alignSelf: 'flex-start' }}
      testID="wordmark"
    >
      {highlighted ? <HighlightSwipe shape="wordmark">{drawing}</HighlightSwipe> : drawing}
    </View>
  );
}
