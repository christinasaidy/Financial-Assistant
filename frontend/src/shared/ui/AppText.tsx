import { Text, type TextProps, type TextStyle } from 'react-native';

import { colors, fonts, type ColorName } from '../theme';

export type FontKind = 'sans' | 'mono' | 'arabic';
export type FontWeight = 400 | 500 | 600 | 700;

const families: Record<FontKind, Partial<Record<FontWeight, string>>> = {
  sans: { 400: fonts.sans.regular, 500: fonts.sans.medium, 600: fonts.sans.semibold },
  mono: { 400: fonts.mono.regular, 500: fonts.mono.medium, 600: fonts.mono.semibold },
  arabic: { 600: fonts.arabic.semibold, 700: fonts.arabic.bold },
};

export type AppTextProps = TextProps & {
  /** Geist for UI text, Geist Mono for numbers, dates and small labels, Noto Naskh Arabic for فاتورتي. */
  font?: FontKind;
  weight?: FontWeight;
  /** Font size in px, as in design/reference. */
  size?: number;
  color?: ColorName;
  /** Letter spacing in em, as the reference writes it (".08em" is 0.08). */
  tracking?: number;
  /** The `cap` label (DESIGN.md §2): Geist Mono 500, 10.5 px, 0.08em, capitals, `capLabel`. */
  cap?: boolean;
};

/**
 * All text in the app. Each weight is its own font file (expo-font), so fontWeight is never set: iOS would
 * fake a bold. Mono numbers are tabular. Follows the iPhone's text size, so allowFontScaling stays on.
 * Write text in normal case; `cap` adds the capitals.
 */
export function AppText({ font, weight, size, color, tracking, cap = false, style, ...rest }: AppTextProps) {
  const kind = font ?? (cap ? 'mono' : 'sans');
  const chosenWeight = weight ?? (cap ? 500 : kind === 'arabic' ? 600 : 400);
  const fontSize = size ?? (cap ? 10.5 : 15);
  const family = families[kind][chosenWeight] ?? families[kind][kind === 'arabic' ? 600 : 400];
  const base: TextStyle = {
    fontFamily: family,
    fontSize,
    color: colors[color ?? (cap ? 'capLabel' : 'ink')],
    letterSpacing: (tracking ?? (cap ? 0.08 : 0)) * fontSize,
    ...(cap ? { textTransform: 'uppercase' as const } : null),
    ...(kind === 'mono' ? { fontVariant: ['tabular-nums' as const] } : null),
  };
  return <Text {...rest} style={[base, style]} />;
}
