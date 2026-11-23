import { createContext, useContext, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { colorTokens, type ColorToken } from './tokens';

export type ColorScheme = 'light' | 'dark';

/** Every colour token resolved for one theme. */
export type Palette = Record<ColorToken, string>;

function paletteFor(scheme: ColorScheme): Palette {
  const entries = Object.entries(colorTokens).map(([name, value]) => [name, value[scheme]]);
  return Object.fromEntries(entries) as Palette;
}

export const palettes: Record<ColorScheme, Palette> = {
  light: paletteFor('light'),
  dark: paletteFor('dark'),
};

export type Theme = {
  scheme: ColorScheme;
  colors: Palette;
};

const SchemeOverride = createContext<ColorScheme | null>(null);

/**
 * Forces a theme for everything inside it. The app does not use it (it follows the phone, D003);
 * it exists for tests and for previewing a screen in the other theme.
 */
export function ThemeOverride({ scheme, children }: { scheme: ColorScheme; children: ReactNode }) {
  return <SchemeOverride.Provider value={scheme}>{children}</SchemeOverride.Provider>;
}

/** The light or dark palette, following the phone's setting (D003). */
export function useTheme(): Theme {
  const override = useContext(SchemeOverride);
  const system = useColorScheme();
  const scheme: ColorScheme = override ?? (system === 'dark' ? 'dark' : 'light');
  return { scheme, colors: palettes[scheme] };
}
