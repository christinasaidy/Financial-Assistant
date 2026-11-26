import type { ArtNode } from '@/shared/ui/art/ArtSvg';
import * as iconArt from '@/shared/ui/art/iconArt.generated';

function gradients(node: ArtNode): ArtNode[] {
  const own = node.tag === 'linearGradient' ? [node] : [];
  return own.concat(node.children.flatMap(gradients));
}

function allArt(module: Record<string, unknown>): ArtNode[] {
  const found: ArtNode[] = [];
  const visit = (value: unknown) => {
    if (value && typeof value === 'object') {
      if ('tag' in value && 'children' in value) found.push(value as ArtNode);
      else Object.values(value).forEach(visit);
    }
  };
  visit(module);
  return found;
}

describe('converted artwork keeps each fade running top to bottom', () => {
  const art = allArt(iconArt);
  const fades = art.flatMap(gradients);

  it('finds the printed fades', () => {
    expect(fades.length).toBeGreaterThan(0);
  });

  it('keeps x1, y1, x2 and y2 on every gradient (a vertical fade: same x, y2 below y1)', () => {
    for (const fade of fades) {
      const { x1, y1, x2, y2 } = fade.props;
      expect([x1, y1, x2, y2]).not.toContain(undefined);
      expect(x1).toBe(x2);
      expect(Number(y2)).toBeGreaterThan(Number(y1));
    }
  });
});
