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
  eye: { strokeWidth: 1.7, paths: ['M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z'], circle: { cx: 12, cy: 12, r: 2.6 } },
  arrow: { strokeWidth: 2, paths: ['M5 12h14M13 6l6 6-6 6'] },
  back: { strokeWidth: 1.8, paths: ['M19 12H5M11 6l-6 6 6 6'] },
  /** Budgets: previous and next month (18 px). */
  chevronLeft: { strokeWidth: 2, paths: ['M15 6l-6 6 6 6'] },
  chevronRight: { strokeWidth: 2, paths: ['M9 6l6 6-6 6'] },
  /** Budgets: new budget, white on the black square (18 px). */
  plus: { strokeWidth: 2.2, paths: ['M12 5v14M5 12h14'] },
  /** Receipts: search and change month (20 px). */
  search: { strokeWidth: 1.8, paths: ['M16 16l4 4'], circle: { cx: 11, cy: 11, r: 6.5 } },
  calendar: { strokeWidth: 1.8, paths: ['M4 10h16M9 3v4M15 3v4', 'M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z'] },
  /** Receipt: share (20 px). */
  share: { strokeWidth: 1.8, paths: ['M12 4v11M7 9l5-5 5 5M5 14v5h14v-5'] },
  /** Assistant: new conversation (20 px). */
  newConversation: { strokeWidth: 1.8, paths: ['M12 5v14M5 12h14'] },
  /** Assistant: send, white on cobalt (18 px). */
  send: { strokeWidth: 2.2, paths: ['M12 19V5M6 11l6-6 6 6'] },
  /** Assistant, Beta: Show / Hide query (14 px; turned for Hide). */
  chevronDown: { strokeWidth: 2.2, paths: ['M6 9l6 6 6-6'] },
  /** Assistant, Beta: Was this right? (16 px). */
  check: { strokeWidth: 2.2, paths: ['M5 12l5 5L20 7'] },
  cross: { strokeWidth: 2.2, paths: ['M6 6l12 12M18 6L6 18'] },
  /** Not in the design: drawn in its line style for the account button by the bell (D045). */
  account: { strokeWidth: 1.7, paths: ['M12 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M4.5 20.5c1.3-3.6 4.2-5.5 7.5-5.5s6.2 1.9 7.5 5.5'] },
} as const;

export type LineIconName = keyof typeof lineIcons;

export type LineIconProps = {
  name: LineIconName;
  /** 20 in a 44 px icon button, 18 for the note's arrow (design/reference). */
  size?: number;
  color?: ColorName;
  accessibilityLabel?: string;
};

/** A line icon of the new design: bell, eye (show password), arrow (the note), back, and account (D045). */
export function LineIcon({ name, size = 20, color = 'ink', accessibilityLabel }: LineIconProps) {
  const icon = lineIcons[name];
  const stroke = colors[color];
  return (
    <View style={{ width: size, height: size }} {...decorative(accessibilityLabel)} testID={`line-icon-${name}`}>
      <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={icon.strokeWidth}>
        {icon.paths.map((d) => (
          <Path key={d} d={d} />
        ))}
        {'circle' in icon ? <Circle {...icon.circle} /> : null}
      </Svg>
    </View>
  );
}
