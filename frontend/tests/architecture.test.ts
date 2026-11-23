/**
 * Enforces the Dependency Rule (see README "Architecture"): source dependencies point inward only.
 * Like backend/tests/test_architecture.py, it reads every import in app/ and src/ and fails on any that
 * crosses a layer the wrong way. The last tests feed it made-up imports, to show it does catch violations.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';

const ROOT = resolve(__dirname, '..');

type Place =
  | { kind: 'route' }
  | { kind: 'container' }
  | { kind: 'shared'; area: string }
  | { kind: 'feature'; feature: string; layer: 'domain' | 'application' | 'data' | 'ui' }
  | { kind: 'asset' }
  | { kind: 'package'; name: string }
  | { kind: 'other'; path: string };

const LAYERS = ['domain', 'application', 'data', 'ui'] as const;

/** Where a project file lives. `path` is relative to frontend/, with forward slashes. */
export function placeOf(path: string): Place {
  const parts = path.split('/');
  if (parts[0] === 'app') return { kind: 'route' };
  if (parts[0] === 'assets') return { kind: 'asset' };
  if (parts[0] === 'src' && (parts[1] === 'container' || parts[1] === 'container.ts')) return { kind: 'container' };
  if (parts[0] === 'src' && parts[1] === 'shared' && parts[2]) return { kind: 'shared', area: parts[2] };
  if (parts[0] === 'src' && parts[1] === 'features' && parts[2]) {
    const layer = LAYERS.find((candidate) => candidate === parts[3]);
    if (layer) return { kind: 'feature', feature: parts[2], layer };
  }
  return { kind: 'other', path };
}

/** Where an import points, seen from the file that has it. */
export function targetOf(fromFile: string, specifier: string): Place {
  let path: string;
  if (specifier.startsWith('@/')) {
    path = `src/${specifier.slice(2)}`;
  } else if (specifier.startsWith('.')) {
    path = relative(ROOT, resolve(ROOT, dirname(fromFile), specifier)).split(sep).join('/');
  } else {
    const [scopeOrName = '', name] = specifier.split('/');
    return { kind: 'package', name: scopeOrName.startsWith('@') ? `${scopeOrName}/${name}` : scopeOrName };
  }
  return placeOf(path.replace(/\.(tsx?|js)$/, ''));
}

/** Shared code with no UI: what the inner layers may use. */
const UI_FREE_SHARED = new Set(['format']);
/** Shared infrastructure a data layer may use. */
const DATA_SHARED = new Set(['api', 'storage', 'format']);

/** Returns why the import is not allowed, or null if it is. */
export function ruleBroken(from: Place, to: Place): string | null {
  if (to.kind === 'other') return null;

  if (from.kind === 'feature') {
    switch (from.layer) {
      case 'domain':
        if (to.kind === 'feature' && to.layer === 'domain') return null;
        return 'domain may only import domain code (no packages, no other layers)';
      case 'application':
        if (to.kind === 'feature' && to.layer === 'domain') return null;
        if (to.kind === 'feature' && to.layer === 'application' && to.feature === from.feature) return null;
        if (to.kind === 'shared' && UI_FREE_SHARED.has(to.area)) return null;
        return "application may only import domain, its own application code and UI-free shared code";
      case 'data':
        if (to.kind === 'package' || to.kind === 'asset') return null;
        if (to.kind === 'feature' && to.layer === 'domain') return null;
        if (to.kind === 'feature' && (to.layer === 'application' || to.layer === 'data') && to.feature === from.feature) {
          return null;
        }
        if (to.kind === 'shared' && DATA_SHARED.has(to.area)) return null;
        return 'data may only import domain, its own application and data code, and shared api/storage/format';
      case 'ui':
        if (to.kind === 'feature' && to.layer === 'data') return 'ui must not import data (go through the container)';
        if (to.kind === 'route') return 'ui must not import routes';
        return null;
    }
  }

  if (from.kind === 'shared') {
    if (to.kind === 'feature' || to.kind === 'container' || to.kind === 'route') {
      return 'shared must not depend on features, the container or routes';
    }
    if (UI_FREE_SHARED.has(from.area) && to.kind === 'package') return 'shared/format must stay free of packages';
    return null;
  }

  if (from.kind === 'route') {
    if (to.kind === 'feature' && to.layer !== 'ui') return 'routes may only import features/*/ui';
    if (to.kind === 'container') return 'routes must not import the container';
    return null;
  }

  if (from.kind === 'container') {
    return to.kind === 'route' ? 'the container must not import routes' : null;
  }

  return null;
}

const IMPORT_PATTERNS = [
  /(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]/g,
  /import\s*['"]([^'"]+)['"]/g,
  /require\(\s*['"]([^'"]+)['"]\s*\)/g,
  /import\(\s*['"]([^'"]+)['"]\s*\)/g,
];

function importsIn(source: string): string[] {
  return IMPORT_PATTERNS.flatMap((pattern) => [...source.matchAll(pattern)].map((match) => match[1] as string));
}

function sourceFiles(dir: string): string[] {
  return readdirSync(join(ROOT, dir)).flatMap((name) => {
    const path = `${dir}/${name}`;
    if (statSync(join(ROOT, path)).isDirectory()) return sourceFiles(path);
    return /\.(tsx?|js)$/.test(name) ? [path] : [];
  });
}

export function violationsIn(files: { path: string; imports: string[] }[]): string[] {
  return files.flatMap(({ path, imports }) =>
    imports.flatMap((specifier) => {
      const problem = ruleBroken(placeOf(path), targetOf(path, specifier));
      return problem ? [`${path} imports "${specifier}": ${problem}`] : [];
    }),
  );
}

const projectFiles = [...sourceFiles('app'), ...sourceFiles('src')].map((path) => ({
  path,
  imports: importsIn(readFileSync(join(ROOT, path), 'utf8')),
}));

describe('the Dependency Rule', () => {
  it('finds the project files', () => {
    expect(projectFiles.length).toBeGreaterThan(20);
    expect(projectFiles.some((file) => file.path === 'src/container.ts')).toBe(true);
  });

  it.each(['domain', 'application', 'data', 'ui'])('%s layers only import what they may', (layer) => {
    const files = projectFiles.filter((file) => {
      const place = placeOf(file.path);
      return place.kind === 'feature' && place.layer === layer;
    });
    expect(violationsIn(files)).toEqual([]);
  });

  it('shared code does not depend on features', () => {
    expect(violationsIn(projectFiles.filter((file) => placeOf(file.path).kind === 'shared'))).toEqual([]);
  });

  it('routes only use feature ui and shared code', () => {
    expect(violationsIn(projectFiles.filter((file) => placeOf(file.path).kind === 'route'))).toEqual([]);
  });

  it('only the container imports a data layer', () => {
    const importers = projectFiles
      .filter((file) => file.imports.some((specifier) => {
        const target = targetOf(file.path, specifier);
        return target.kind === 'feature' && target.layer === 'data';
      }))
      .map((file) => file.path)
      .filter((path) => {
        const place = placeOf(path);
        // A data layer may import its own other data files.
        return !(place.kind === 'feature' && place.layer === 'data');
      });
    expect(importers).toEqual(['src/container.ts']);
  });
});

describe('the architecture test itself', () => {
  it.each([
    ['src/features/auth/domain/types.ts', 'react'],
    ['src/features/auth/domain/types.ts', '../application/interfaces'],
    ['src/features/auth/application/authService.ts', 'expo-secure-store'],
    ['src/features/auth/application/authService.ts', '../data/apiAuthRepository'],
    ['src/features/auth/application/authService.ts', '@/shared/api/httpClient'],
    ['src/features/auth/ui/SignInScreen.tsx', '../data/apiAuthRepository'],
    ['src/features/home/data/homeRepository.ts', '@/features/auth/data/apiAuthRepository'],
    ['src/shared/ui/Button.tsx', '@/features/auth/ui/SessionProvider'],
    ['src/shared/format/money.ts', 'react-native'],
    ['app/(tabs)/index.tsx', '@/features/home/application/homeService'],
    ['app/(tabs)/index.tsx', '@/container'],
  ])('rejects %s importing %s', (path, specifier) => {
    expect(violationsIn([{ path, imports: [specifier] }])).toHaveLength(1);
  });

  it.each([
    ['src/features/home/domain/summary.ts', '@/features/auth/domain/types'],
    ['src/features/auth/application/authService.ts', '../domain/types'],
    ['src/features/auth/data/apiAuthRepository.ts', '@/shared/api/httpClient'],
    ['src/features/auth/ui/SessionProvider.tsx', '@/container'],
    ['src/features/home/ui/HomeScreen.tsx', '@/features/auth/ui/SessionProvider'],
    ['app/(tabs)/index.tsx', '@/features/home/ui/HomeScreen'],
    ['app/(tabs)/index.tsx', 'expo-router'],
  ])('allows %s importing %s', (path, specifier) => {
    expect(violationsIn([{ path, imports: [specifier] }])).toEqual([]);
  });
});
