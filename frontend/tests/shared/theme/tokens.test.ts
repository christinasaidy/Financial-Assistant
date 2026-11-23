/**
 * tokens.ts is copied by hand from DESIGN.md (D005 asks how the two are kept in step): this test reads
 * DESIGN.md's front matter and fails if a value differs.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { colorTokens, fontFamilies, rounded, spacing } from '@/shared/theme/tokens';
import { textStyles, textVariants } from '@/shared/theme/textStyles';

// Windows checkouts may have CRLF line endings.
const design = readFileSync(join(__dirname, '../../../docs/design/DESIGN.md'), 'utf8').replace(/\r\n/g, '\n');
const frontMatter = design.split('---')[1] ?? '';

/** The `key: value` lines of one top-level YAML block, comments removed. */
function block(name: string): Map<string, string> {
  const lines = frontMatter.split('\n');
  const start = lines.findIndex((line) => line === `${name}:`);
  const entries = new Map<string, string>();
  for (const line of lines.slice(start + 1)) {
    if (/^\S/.test(line) && !line.startsWith('#')) break;
    const match = /^\s+([\w-]+):\s*(?:"([^"]*)"|([^\s#]+))/.exec(line);
    if (match) entries.set(match[1] as string, (match[2] ?? match[3] ?? '').trim());
  }
  return entries;
}

/** The typography block: style name -> its properties. */
function typography(): Map<string, Map<string, string>> {
  const styles = new Map<string, Map<string, string>>();
  let current: Map<string, string> | null = null;
  const lines = frontMatter.split('\n');
  const start = lines.findIndex((line) => line === 'typography:');
  for (const line of lines.slice(start + 1)) {
    if (/^\S/.test(line) && !line.startsWith('#')) break;
    const styleMatch = /^ {2}([\w-]+):/.exec(line);
    const propMatch = /^ {4}(\w+):\s*([^#]+)/.exec(line);
    if (styleMatch) {
      current = new Map();
      styles.set(styleMatch[1] as string, current);
    } else if (propMatch && current) {
      current.set(propMatch[1] as string, (propMatch[2] as string).trim());
    }
  }
  return styles;
}

const px = (value: string | undefined) => Number(String(value).replace('px', ''));

describe('tokens.ts matches DESIGN.md', () => {
  const colors = block('colors');

  it('has every colour, light and dark', () => {
    const fromDesign = [...colors.keys()].filter((key) => !key.endsWith('-dark'));
    expect(Object.keys(colorTokens).sort()).toEqual(fromDesign.sort());
    for (const [name, value] of Object.entries(colorTokens)) {
      expect([name, value.light]).toEqual([name, colors.get(name)]);
      expect([name, value.dark]).toEqual([name, colors.get(`${name}-dark`)]);
    }
  });

  it('has the spacing scale and square corners', () => {
    const fromDesign = Object.fromEntries([...block('spacing')].map(([key, value]) => [key, px(value)]));
    expect(spacing).toEqual(fromDesign);
    expect(rounded.none).toBe(px(block('rounded').get('none')));
  });

  it('has the nine text styles with their sizes and line heights', () => {
    const fromDesign = typography();
    for (const variant of textVariants) {
      const style = fromDesign.get(variant);
      expect(style).toBeDefined();
      const ours = textStyles[variant];
      expect([variant, ours.fontSize, ours.lineHeight]).toEqual([
        variant,
        px(style?.get('fontSize')),
        px(style?.get('lineHeight')),
      ]);
      const bold = style?.get('fontWeight') === '700';
      const mono = style?.get('fontFamily') === 'DejaVu Sans Mono';
      const family = mono ? (bold ? fontFamilies.monoBold : fontFamilies.mono) : bold ? fontFamilies.sansBold : fontFamilies.sans;
      expect([variant, ours.fontFamily]).toEqual([variant, family]);
      const spacingEm = style?.get('letterSpacing');
      if (spacingEm) expect(ours.letterSpacing).toBeCloseTo(parseFloat(spacingEm) * ours.fontSize);
    }
  });
});
