import type { ComponentType } from 'react';
import Svg, { Circle, Defs, LinearGradient, Mask, Path, Rect, Stop } from 'react-native-svg';

/**
 * One SVG element as scripts/convert-svgs.mjs writes it: the tag, its attributes in camelCase, and its
 * children. Colours stay "currentColor"; ArtSvg sets the actual colour on the root.
 */
export type ArtNode = {
  tag: string;
  props: Record<string, string | number>;
  children: ArtNode[];
};

// Only the elements the Figma exports use. The converter refuses any other element, so nothing is dropped silently.
const ELEMENTS: Record<string, ComponentType<Record<string, unknown>>> = {
  defs: Defs as ComponentType<Record<string, unknown>>,
  linearGradient: LinearGradient as unknown as ComponentType<Record<string, unknown>>,
  stop: Stop as unknown as ComponentType<Record<string, unknown>>,
  mask: Mask as unknown as ComponentType<Record<string, unknown>>,
  rect: Rect as unknown as ComponentType<Record<string, unknown>>,
  path: Path as unknown as ComponentType<Record<string, unknown>>,
  circle: Circle as unknown as ComponentType<Record<string, unknown>>,
};

function renderNode(node: ArtNode, key: number) {
  const Element = ELEMENTS[node.tag];
  if (!Element) throw new Error(`ArtSvg cannot draw <${node.tag}>`);
  return (
    <Element key={key} {...node.props}>
      {node.children.length > 0 ? node.children.map(renderNode) : undefined}
    </Element>
  );
}

type Props = {
  art: ArtNode;
  width: number;
  height: number;
  /** The ink colour ("currentColor" in the drawing). */
  color: string;
};

/** Draws converted artwork (icons, wordmark) with react-native-svg, masks and fades included. */
export function ArtSvg({ art, width, height, color }: Props) {
  const { width: _w, height: _h, ...rootProps } = art.props;
  return (
    <Svg width={width} height={height} color={color} {...rootProps}>
      {art.children.map(renderNode)}
    </Svg>
  );
}
