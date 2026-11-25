import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { getContainer } from '@/container';
import { ThemeOverride } from '@/shared/theme';

import type { SettingsService } from '../application/settingsService';
import { defaultAppearance, forcedScheme, type Appearance } from '../domain/appearance';

export type AppearanceValue = {
  appearance: Appearance;
  /** Applies the choice at once and saves it on the phone. */
  setAppearance: (appearance: Appearance) => void;
};

const AppearanceContext = createContext<AppearanceValue | null>(null);

type Props = {
  children: ReactNode;
  /** Defaults to the app's SettingsService from the container; tests pass one built on a fake. */
  service?: SettingsService;
};

/**
 * Applies the appearance setting (D043) to the whole app (mounted once in app/_layout.tsx). It follows the
 * phone until the saved choice has loaded; the launch screen is yellow in both themes, so the switch does not
 * show. The tree is the same whatever the choice, so changing it never resets the screens.
 */
export function AppearanceProvider({ children, service }: Props) {
  const settings = useMemo(() => service ?? getContainer().settings, [service]);
  const [appearance, setState] = useState<Appearance>(defaultAppearance);
  // A choice made before the saved one has loaded wins over it.
  const chosen = useRef(false);

  useEffect(() => {
    let active = true;
    void settings.loadAppearance().then((saved) => {
      if (active && !chosen.current) setState(saved);
    });
    return () => {
      active = false;
    };
  }, [settings]);

  const value = useMemo<AppearanceValue>(
    () => ({
      appearance,
      setAppearance: (next) => {
        chosen.current = true;
        setState(next);
        void settings.setAppearance(next);
      },
    }),
    [appearance, settings],
  );

  return (
    <AppearanceContext.Provider value={value}>
      <ThemeOverride scheme={forcedScheme(appearance)}>{children}</ThemeOverride>
    </AppearanceContext.Provider>
  );
}

/** The appearance setting, from any screen inside AppearanceProvider. */
export function useAppearance(): AppearanceValue {
  const value = useContext(AppearanceContext);
  if (!value) throw new Error('useAppearance must be used inside <AppearanceProvider>');
  return value;
}
