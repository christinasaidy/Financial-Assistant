import { View } from 'react-native';

import { sizes, useTheme, type ColorToken } from '../theme';
import { ArtSvg } from './art/ArtSvg';
import { iconArt, type IconName } from './art/iconArt.generated';

export type { IconName } from './art/iconArt.generated';
export { iconNames } from './art/iconArt.generated';

export type IconProps = {
  name: IconName;
  /**
   * Box size in px. 24 on its own (D027); beside text, the font size of that text (15 beside a receipt
   * line, 16 in the main button).
   */
  size?: number;
  /** Ink in light and dark by default (DESIGN.md Iconography). */
  color?: ColorToken;
  /** The Printed variant is the app's look (D027); `printed={false}` draws the Clean master. */
  printed?: boolean;
  /** Icons are decoration unless given a label; the button or tab around them carries the name. */
  accessibilityLabel?: string;
};

/** One of the twelve icons drawn in Figma (D024, D030). No icon library (D008). */
export function Icon({ name, size = sizes.icon, color = 'ink', printed = true, accessibilityLabel }: IconProps) {
  const { colors } = useTheme();
  const art = iconArt[name][printed ? 'printed' : 'clean'];
  return (
    <View
      style={{ width: size, height: size }}
      accessible={Boolean(accessibilityLabel)}
      accessibilityLabel={accessibilityLabel}
      accessibilityRole={accessibilityLabel ? 'image' : undefined}
      importantForAccessibility={accessibilityLabel ? 'yes' : 'no-hide-descendants'}
      accessibilityElementsHidden={!accessibilityLabel}
      testID={`icon-${name}`}
    >
      <ArtSvg art={art} width={size} height={size} color={colors[color]} />
    </View>
  );
}
