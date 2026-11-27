import { useEffect, useState } from 'react';

/** How long the launch screen stays at least, from the moment the app starts. */
export const LAUNCH_HOLD_MS = 1500;

/** When this app run started (the module loads once, as the app opens). */
const appStartedAt = Date.now();

/**
 * True while the launch screen should stay: until LAUNCH_HOLD_MS after the app started. Checking the saved
 * session takes a few milliseconds, so without this the launch screen only flashed. Measured from the app's
 * start, so returning to the launch route later (after signing out) does not wait again.
 */
export function useLaunchHold(holdMs: number = LAUNCH_HOLD_MS): boolean {
  const remaining = () => Math.max(0, appStartedAt + holdMs - Date.now());
  const [holding, setHolding] = useState(() => remaining() > 0);

  useEffect(() => {
    if (!holding) return undefined;
    const timer = setTimeout(() => setHolding(false), remaining());
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holding, holdMs]);

  return holding;
}
