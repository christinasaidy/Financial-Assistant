import type { TextStyle } from 'react-native';

import { fontFamilies, type ColorToken } from './tokens';

/**
 * The nine text styles of the type scale "Balanced" (D014), in px, from DESIGN.md "typography".
 *
 * - Each weight is its own font family (expo-font registers Book and Bold separately), so no style sets
 *   fontWeight: iOS would otherwise try to fake a bold.
 * - Capitals are a style, never typed (D012): textTransform 'uppercase'.
 * - letterSpacing is in px in React Native: the section label's +8% (0.08em) at 12 px is 0.96.
 * - All sizes follow the iPhone's text-size setting (D013): AppText leaves allowFontScaling on.
 */
export const textVariants = [
  'total-hero',
  'screen-title',
  'shop-name',
  'total-line',
  'receipt-line',
  'sentence',
  'meta',
  'section-label',
  'caption',
] as const;

export type TextVariant = (typeof textVariants)[number];

type VariantStyle = Required<Pick<TextStyle, 'fontFamily' | 'fontSize' | 'lineHeight'>> &
  Pick<TextStyle, 'letterSpacing' | 'textTransform'>;

export const textStyles: Record<TextVariant, VariantStyle> = {
  'total-hero': { fontFamily: fontFamilies.monoBold, fontSize: 36, lineHeight: 38 },
  'screen-title': {
    fontFamily: fontFamilies.monoBold,
    fontSize: 22,
    lineHeight: 26,
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  'shop-name': { fontFamily: fontFamilies.monoBold, fontSize: 16, lineHeight: 21, textTransform: 'uppercase' },
  'total-line': { fontFamily: fontFamilies.monoBold, fontSize: 16, lineHeight: 21, textTransform: 'uppercase' },
  'receipt-line': { fontFamily: fontFamilies.mono, fontSize: 15, lineHeight: 20 },
  sentence: { fontFamily: fontFamilies.sans, fontSize: 15, lineHeight: 22 },
  meta: { fontFamily: fontFamilies.mono, fontSize: 13, lineHeight: 18 },
  'section-label': {
    fontFamily: fontFamilies.mono,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 12 * 0.08,
    textTransform: 'uppercase',
  },
  caption: { fontFamily: fontFamilies.mono, fontSize: 12, lineHeight: 16 },
};

/** The colour each style has unless told otherwise: dates, labels and captions are grey (D014). */
export const defaultTextColor: Record<TextVariant, ColorToken> = {
  'total-hero': 'ink',
  'screen-title': 'ink',
  'shop-name': 'ink',
  'total-line': 'ink',
  'receipt-line': 'ink',
  sentence: 'ink',
  meta: 'ink-2',
  'section-label': 'ink-2',
  caption: 'ink-2',
};
