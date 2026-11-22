import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getContainer } from '@/container';

import type { HomeService } from '../application/homeService';
import { HomeError } from '../domain/errors';
import type { HomeOverview } from '../domain/types';

export type HomeState =
  | { status: 'loading' }
  | { status: 'failed'; error: HomeError }
  /** `refreshError`: the last reload failed; the overview shown is from before. */
  | { status: 'loaded'; overview: HomeOverview; refreshError: HomeError | null };

export type HomeOverviewValue = {
  state: HomeState;
  /** True only while a pull-to-refresh runs (it drives the pull's own indicator). */
  refreshing: boolean;
  refresh: () => void;
  retry: () => void;
};

/** The app's HomeService from the container, unless a test passes one. */
export function useHomeService(service?: HomeService): HomeService {
  return useMemo(() => service ?? getContainer().home, [service]);
}

function asHomeError(error: unknown): HomeError {
  return error instanceof HomeError ? error : new HomeError('unexpected', String(error));
}

/**
 * Loads Home's overview for the current month, and loads it again each time Home comes back into view
 * (after a scan or a budget change on another tab), on pull-to-refresh and on Try again. A reload keeps
 * what is on screen until the new figures arrive; only the latest answer is used.
 */
export function useHomeOverview(service: HomeService): HomeOverviewValue {
  const [state, setState] = useState<HomeState>({ status: 'loading' });
  const [refreshing, setRefreshing] = useState(false);
  const latest = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (kind: 'focus' | 'pull' | 'retry') => {
      const request = ++latest.current;
      const current = () => mounted.current && request === latest.current;
      if (kind === 'pull') setRefreshing(true);
      if (kind === 'retry') setState((previous) => (previous.status === 'failed' ? { status: 'loading' } : previous));
      try {
        const overview = await service.loadOverview(new Date());
        if (current()) setState({ status: 'loaded', overview, refreshError: null });
      } catch (error) {
        if (current()) {
          const homeError = asHomeError(error);
          setState((previous) =>
            previous.status === 'loaded'
              ? { ...previous, refreshError: homeError }
              : { status: 'failed', error: homeError },
          );
        }
      } finally {
        if (kind === 'pull' && mounted.current) setRefreshing(false);
      }
    },
    [service],
  );

  useFocusEffect(
    useCallback(() => {
      void load('focus');
    }, [load]),
  );

  return {
    state,
    refreshing,
    refresh: useCallback(() => void load('pull'), [load]),
    retry: useCallback(() => void load('retry'), [load]),
  };
}
