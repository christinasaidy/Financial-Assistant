import { View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

import { colors, type ColorName } from '../theme';
import { ArtSvg } from './art/ArtSvg';
import { iconArt, type IconName } from './art/iconArt.generated';

export type { IconName } from './art/iconArt.generated';
export { iconNames } from './art/iconArt.generated';

function decorative(label: string | undefined) {
  return {
    accessible: Boolean(label),
    accessibilityLabel: label,
    accessibilityRole: label ? ('image' as const) : undefined,
    importantForAccessibility: label ? ('yes' as const) : ('no-hide-descendants' as const),
    accessibilityElementsHidden: !label,
  };
}

export type IconProps = {
  name: IconName;
  /** 22 in the tab bar (DESIGN.md §4), 24 in the Scan button. */
  size?: number;
  color?: ColorName;
  /** Icons are decoration unless given a label; the button or tab around them carries the name. */
  accessibilityLabel?: string;
};

/**
 * Christina's own printed icons, kept from the first design for the five tabs: Home, Receipts, Scan,
 * Budgets, Assistant (D044). Drawn in Figma; no icon library.
 */
export function Icon({ name, size = 22, color = 'ink', accessibilityLabel }: IconProps) {
  return (
    <View style={{ width: size, height: size }} {...decorative(accessibilityLabel)} testID={`icon-${name}`}>
      <ArtSvg art={iconArt[name].printed} width={size} height={size} color={colors[color]} />
    </View>
  );
}

/** The new design's line icons, copied from design/reference (24 × 24 view box). */
const lineIcons = {
  bell: { strokeWidth: 1.7, paths: ['M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z', 'M10 20.5a2 2 0 0 0 4 0'] },
  eye: { strokeWidth: 1.7, paths: ['M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z'], circle: true },
  arrow: { strokeWidth: 2, paths: ['M5 12h14M13 6l6 6-6 6'] },
  back: { strokeWidth: 1.8, paths: ['M19 12H5M11 6l-6 6 6 6'] },
} as const;

export type LineIconName = keyof typeof lineIcons;

export type LineIconProps = {
  name: LineIconName;
  /** 20 in a 44 px icon button, 18 for the note's arrow (design/reference). */
  size?: number;
  color?: ColorName;
  accessibilityLabel?: string;
};

/** A line icon of the new design: bell, eye (show password), arrow (the note), back. */
export function LineIcon({ name, size = 20, color = 'ink', accessibilityLabel }: LineIconProps) {
  const icon = lineIcons[name];
  const stroke = colors[color];
  return (
    <View style={{ width: size, height: size }} {...decorative(accessibilityLabel)} testID={`line-icon-${name}`}>
      <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={icon.strokeWidth}>
        {icon.paths.map((d) => (
          <Path key={d} d={d} />
        ))}
        {'circle' in icon ? <Circle cx={12} cy={12} r={2.6} /> : null}
      </Svg>
    </View>
  );
}
