/**
 * The app's tokens come from the design handoff (design/theme.ts). This test keeps them honest: every design
 * colour is used untouched, and every colour the app adds is one the reference screens really use.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { colors, fonts } from '@/shared/theme';

import { colors as designColors, fonts as designFonts } from '../../../design/theme';

const referenceDir = join(__dirname, '../../../design/reference');
const reference = readdirSync(referenceDir)
  .map((file) => readFileSync(join(referenceDir, file), 'utf8'))
  .join('\n')
  .toLowerCase()
  .replace(/\s+/g, '');

describe('design tokens', () => {
  it('keeps every colour of design/theme.ts exactly', () => {
    for (const [name, value] of Object.entries(designColors)) {
      expect(colors[name as keyof typeof colors]).toBe(value);
    }
  });

  it('only adds colours that the reference screens use', () => {
    const added = Object.entries(colors).filter(([name]) => !(name in designColors));
    expect(added.length).toBeGreaterThan(0);
    for (const [name, value] of added) {
      const hex = value.toLowerCase().replace(/\s+/g, '');
      const short = /^#ffffff$/.test(hex) ? ['#fff', '#ffffff'] : [hex];
      const plain = hex.replace(/^rgba\((.*)\)$/, '$1').replace(/0\.(\d+)/g, '.$1');
      expect({ name, found: short.some((form) => reference.includes(form)) || reference.includes(plain) }).toEqual({ name, found: true });
    }
  });

  it('uses the font names design/theme.ts gives', () => {
    expect(fonts).toEqual(designFonts);
  });
});
