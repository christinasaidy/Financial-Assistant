/**
 * The paper of DESIGN.md §3: the crease texture, the torn bottom edge, a sheet that combines them, the
 * perforation line above the tab bar, and the rules drawn on paper.
 */
import { useState, type ReactNode } from 'react';
import { Image, StyleSheet, View, type LayoutChangeEvent, type StyleProp, type ViewStyle } from 'react-native';
import Svg, { Circle, Line, Path } from 'react-native-svg';

import { colors, crease as creaseTokens, shadow as shadowTokens, tornEdge, type ColorName } from '../theme';

const CREASE = require('../../../assets/paper/crease.jpg');
/** crease.jpg is 520 × 1024 px. */
const CREASE_RATIO = 1024 / 520;

type Size = { width: number; height: number };

function useSize(): [Size, (event: LayoutChangeEvent) => void] {
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const measure = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setSize((old) => (old.width === width && old.height === height ? old : { width, height }));
  };
  return [size, measure];
}

/** The tiles' starts along one side, like CSS `background-position: p%` with `repeat`. */
function tileStarts(length: number, tile: number, position: number): number[] {
  if (length <= 0 || tile <= 0) return [];
  const anchor = (length - tile) * position;
  const first = anchor - Math.ceil(anchor / tile) * tile;
  const starts: number[] = [];
  for (let start = first; start < length; start += tile) starts.push(start);
  return starts;
}

export type CreaseProps = {
  /** 0.6 on main screens, 0.69 on the sign-in slips and the launch sheet (DESIGN.md §3). */
  opacity: number;
  /** Tile width in px: 300 by default; the sign-in slips use 360, its form sheet 520. */
  tileWidth?: number;
  /** Where the tiling starts, as CSS background-position fractions (0.5, 0.5 is "center"). */
  position?: { x: number; y: number };
};

/**
 * The crease texture, tiled, with the overlay blend: mid-grey disappears and only the folds show. It is
 * drawn on top of the sheet's content, so the folds run through the ink; it never takes taps. The sheet
 * around it must isolate the blend (PaperSheet does).
 */
export function Crease({ opacity, tileWidth = creaseTokens.tileWidth, position = { x: 0.5, y: 0.5 } }: CreaseProps) {
  const [size, measure] = useSize();
  const tileHeight = tileWidth * CREASE_RATIO;
  const xs = tileStarts(size.width, tileWidth, position.x);
  const ys = tileStarts(size.height, tileHeight, position.y);
  return (
    <View
      pointerEvents="none"
      onLayout={measure}
      style={[StyleSheet.absoluteFill, { mixBlendMode: creaseTokens.blend, opacity }]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      testID="crease"
    >
      {ys.flatMap((top) =>
        xs.map((left) => (
          <Image
            key={`${left}:${top}`}
            source={CREASE}
            style={{ position: 'absolute', left, top, width: tileWidth, height: tileHeight }}
          />
        )),
      )}
    </View>
  );
}

export type Tear = { tooth: number; height: number };

/** The torn edges of DESIGN.md §3: invoice sheets, sign-in slips, the launch sheet. */
export const tears = {
  sheet: { tooth: tornEdge.tooth, height: tornEdge.height },
  slip: { tooth: tornEdge.slipTooth, height: tornEdge.slipHeight },
  launch: { tooth: tornEdge.launchTooth, height: tornEdge.launchHeight },
} as const satisfies Record<string, Tear>;

/** A zigzag torn edge under a sheet, in the sheet's colour (DESIGN.md §3, TornEdge). */
export function TornEdge({ color, tooth, height }: Tear & { color: string }) {
  const [size, measure] = useSize();
  const width = size.width;
  const d = `M0 0 H${width} V0${zigzag(width, tooth, height)}`;
  return (
    <View onLayout={measure} style={{ height }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {width > 0 ? (
        <Svg width={width} height={height}>
          <Path d={`${d} Z`} fill={color} />
        </Svg>
      ) : null}
    </View>
  );
}

function zigzag(width: number, tooth: number, height: number): string {
  let d = '';
  for (let x = width; x > 0; x -= tooth) d += ` L${x - tooth / 2} ${height} L${Math.max(x - tooth, 0)} 0`;
  return d;
}

/**
 * The gaps between the teeth, painted in the colour behind the sheet. Drawn over the crease, so the crease
 * runs into the teeth as in the design (its CSS masks the creased sheet into the zigzag).
 */
function Notches({ color, tooth, height }: Tear & { color: string }) {
  const [size, measure] = useSize();
  const width = size.width;
  return (
    <View onLayout={measure} style={[styles.notches, { height }]} pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {width > 0 ? (
        <Svg width={width} height={height}>
          <Path d={`M${width} 0${zigzag(width, tooth, height)} L0 ${height} L${width} ${height} Z`} fill={color} />
        </Svg>
      ) : null}
    </View>
  );
}

export type PaperSheetProps = {
  children?: ReactNode;
  /** The paper colour; `paper` by default. */
  color?: ColorName;
  /** The crease's opacity, or null for none. */
  crease?: number | null;
  creaseTileWidth?: number;
  creasePosition?: CreaseProps['position'];
  /** The torn bottom edge, or null for a straight one. */
  tear?: Tear | null;
  /**
   * The colour behind the sheet. Given, the teeth are part of the creased sheet and the gaps between them
   * are painted in it; without it (slips lying on other slips), the teeth are plain paper under the sheet.
   */
  on?: ColorName;
  /** The sheet's drop shadow (it follows the torn edge); the design's sheet shadow by default. */
  shadow?: ViewStyle | null;
  /** The sheet itself: padding, flex. */
  style?: StyleProp<ViewStyle>;
  /** The wrapper that carries the shadow: margins, position, rotation. */
  outerStyle?: StyleProp<ViewStyle>;
  testID?: string;
};

/**
 * A sheet of paper: its content, the crease on top, the torn edge under it, and a drop shadow around both
 * (DESIGN.md §3, CreasedPaper). Sheets have no border radius.
 */
export function PaperSheet({
  children,
  color = 'paper',
  crease = creaseTokens.main,
  creaseTileWidth,
  creasePosition,
  tear = tears.sheet,
  on,
  shadow = shadowTokens.sheet,
  style,
  outerStyle,
  testID,
}: PaperSheetProps) {
  return (
    <View style={[shadow, outerStyle]} testID={testID}>
      <View style={[styles.sheet, { backgroundColor: colors[color] }, style, tear && on ? { paddingBottom: bottomPadding(style) + tear.height } : null]}>
        {children}
        {crease !== null ? <Crease opacity={crease} tileWidth={creaseTileWidth} position={creasePosition} /> : null}
        {tear && on ? <Notches color={colors[on]} {...tear} /> : null}
      </View>
      {tear && !on ? <TornEdge color={colors[color]} {...tear} /> : null}
    </View>
  );
}

function bottomPadding(style: StyleProp<ViewStyle>): number {
  const flat = StyleSheet.flatten(style) ?? {};
  const value = flat.paddingBottom ?? flat.paddingVertical ?? flat.padding ?? 0;
  return typeof value === 'number' ? value : 0;
}

/** The perforation above the tab bar: dots of radius 2.5 every 12 px, centred, 10 px tall (DESIGN.md §3). */
export function Perforation() {
  const [size, measure] = useSize();
  const centre = size.width / 2;
  const dots: number[] = [];
  for (let x = centre - Math.ceil(centre / 12) * 12; x <= size.width + 3; x += 12) dots.push(x);
  return (
    <View onLayout={measure} style={{ height: 10 }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {size.width > 0 ? (
        <Svg width={size.width} height={10}>
          {dots.map((x) => (
            <Circle key={x} cx={x} cy={5} r={2.5} fill={colors.perfDot} />
          ))}
        </Svg>
      ) : null}
    </View>
  );
}

/**
 * A dashed line, like CSS `border: dashed` (dashes three times the width long). React Native cannot dash
 * one side of a border, so it is drawn.
 */
export function DashedLine({ color = 'dashed', width = 1, style }: { color?: ColorName; width?: number; style?: StyleProp<ViewStyle> }) {
  const [size, measure] = useSize();
  return (
    <View onLayout={measure} style={[{ height: width, alignSelf: 'stretch' }, style]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" testID="dashed-line">
      {size.width > 0 ? (
        <Svg width={size.width} height={width}>
          <Line x1={0} y1={width / 2} x2={size.width} y2={width / 2} stroke={colors[color]} strokeWidth={width} strokeDasharray={[3 * width, 3 * width]} />
        </Svg>
      ) : null}
    </View>
  );
}

/** The 3 px double ink rule above a total (CSS `3px double`: two 1 px lines, 1 px apart). */
export function DoubleRule({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.double, style]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" />;
}

const styles = StyleSheet.create({
  sheet: { isolation: 'isolate', overflow: 'hidden', borderRadius: 0 },
  notches: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  double: { height: 3, borderTopWidth: 1, borderBottomWidth: 1, borderColor: colors.ink, alignSelf: 'stretch' },
});
