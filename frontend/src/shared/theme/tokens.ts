/**
 * Design tokens, copied by hand from docs/design/DESIGN.md (front matter). DESIGN.md is the source of truth:
 * change a value there first (with its DECISIONS.md entry), then here. tokens.test.ts checks that the two match.
 */

/** Colours (D022, D023, D038, D039, D042). Each has a light and a dark value (D003). */
export const colorTokens = {
  primary: { light: '#2443a8', dark: '#9db0ff' },
  paper: { light: '#ffffff', dark: '#17181b' },
  ink: { light: '#1c1d21', dark: '#e6e6e1' },
  'ink-2': { light: '#575a60', dark: '#a2a4a8' },
  rule: { light: '#c3c6c2', dark: '#3a3c40' },
  track: { light: '#dfe1dd', dark: '#2a2c30' },
  'near-limit': { light: '#8a5a00', dark: '#e0a43a' },
  'limit-reached': { light: '#b0241b', dark: '#e0524f' },
  highlight: { light: '#f5e54a', dark: '#e8d84a' },
} as const;

export type ColorToken = keyof typeof colorTokens;

/** Text on the yellow highlight is always light-mode ink, in both themes (D038). */
export const inkOnHighlight = colorTokens.ink.light;

/** The launch screen is yellow paper in both themes (D039). */
export const launchBackground = colorTokens.highlight.light;

/** Spacing (D031): a 4 px scale, nothing in between, and 20 px screen margins. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  '2xl': 32,
  '3xl': 48,
  'screen-margin': 20,
} as const;

export type SpacingToken = keyof typeof spacing;

/** Shapes (D032): square corners everywhere. */
export const rounded = { none: 0 } as const;

/** Font family names as registered with expo-font in app/_layout.tsx (D006). */
export const fontFamilies = {
  mono: 'DejaVuSansMono',
  monoBold: 'DejaVuSansMono-Bold',
  sans: 'DejaVuSans',
  sansBold: 'DejaVuSans-Bold',
} as const;

/** Component sizes recorded in DESIGN.md "Components" (D027, D033, D037). */
export const sizes = {
  /** An icon on its own (D027). */
  icon: 24,
  /** Apple's minimum touch area for an icon on its own (D027). */
  touchTarget: 44,
  /** Main button height (D037). */
  button: 48,
  /** Icon inside the main button (D037). */
  buttonIcon: 16,
  /** Tab bar height above the home indicator (D033). */
  tabBar: 64,
  /** The Scan tab's pen-blue square (D033). */
  scanSquare: 44,
  /** Rules (D032). */
  hairline: 1,
  /** Dashed rule: 4 on, 3 off (D032). */
  dashOn: 4,
  dashOff: 3,
} as const;
