import { Text, type StyleProp, type TextProps, type TextStyle } from 'react-native';

import { defaultTextColor, inkOnHighlight, textStyles, useTheme, type ColorToken, type TextVariant } from '../theme';

/** A theme colour token, or 'on-highlight': ink #1c1d21 on the yellow swipe, in both themes (D038). */
export type TextColor = ColorToken | 'on-highlight';

/** Layout only. Type and colour come from `variant` and `color`, so screens cannot drift from DESIGN.md. */
export type AppTextLayoutStyle = Pick<
  TextStyle,
  | 'textAlign'
  | 'flex'
  | 'flexGrow'
  | 'flexShrink'
  | 'alignSelf'
  | 'margin'
  | 'marginTop'
  | 'marginBottom'
  | 'marginLeft'
  | 'marginRight'
  | 'marginHorizontal'
  | 'marginVertical'
>;

export type AppTextProps = Omit<TextProps, 'style'> & {
  /** One of the nine text styles (D014). */
  variant: TextVariant;
  /** Defaults per variant: ink, or ink-2 for meta, section-label and caption. */
  color?: TextColor;
  style?: StyleProp<AppTextLayoutStyle>;
};

export function useTextColor(color: TextColor): string {
  const { colors } = useTheme();
  return color === 'on-highlight' ? inkOnHighlight : colors[color];
}

/**
 * All text in the app. Follows the iPhone's text-size setting (D013), so never turn allowFontScaling off.
 * Write text in normal case: the variant adds capitals where D012 says so.
 */
export function AppText({ variant, color, style, ...rest }: AppTextProps) {
  const textColor = useTextColor(color ?? defaultTextColor[variant]);
  return <Text {...rest} style={[textStyles[variant], { color: textColor }, style]} />;
}
