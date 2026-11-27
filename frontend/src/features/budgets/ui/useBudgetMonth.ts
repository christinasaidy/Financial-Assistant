import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getContainer } from '@/container';

import type { BudgetsService } from '../application/budgetsService';
import { BudgetsError, shiftMonth, type BudgetMonth } from '../domain';

export type BudgetMonthState =
  | { status: 'loading' }
  | { status: 'failed'; error: BudgetsError }
  | { status: 'loaded'; data: BudgetMonth };

/** The app's BudgetsService from the container, unless a test passes one. */
export function useBudgetsService(service?: BudgetsService): BudgetsService {
  return useMemo(() => service ?? getContainer().budgets, [service]);
}

function firstOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

/**
 * The month on screen and its budgets: starts on the current month, moves a month back or forward, and
 * loads again whenever Budgets comes back into view (after saving a budget in the form sheet). Only the
 * latest answer is used, so tapping through months quickly never shows an older one.
 */
export function useBudgetMonth(service: BudgetsService, today: () => Date = () => new Date()) {
  const [month, setMonth] = useState(() => firstOfMonth(today()));
  const [state, setState] = useState<BudgetMonthState>({ status: 'loading' });
  const latest = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (target: Date, showLoading: boolean) => {
      const request = ++latest.current;
      if (showLoading) setState({ status: 'loading' });
      try {
        const data = await service.loadMonth(target);
        if (mounted.current && request === latest.current) setState({ status: 'loaded', data });
      } catch (error) {
        if (mounted.current && request === latest.current) {
          setState({ status: 'failed', error: error instanceof BudgetsError ? error : new BudgetsError('unexpected', String(error)) });
        }
      }
    },
    [service],
  );

  // On focus, and when the month changes: load the month on screen. A reload keeps what is shown until
  // the answer comes; a new month shows the spinner (set in `go`).
  useFocusEffect(
    useCallback(() => {
      void load(month, false);
    }, [load, month]),
  );

  const go = (by: number) => {
    setState({ status: 'loading' });
    setMonth((current) => shiftMonth(current, by));
  };

  return {
    month,
    state,
    previous: () => go(-1),
    next: () => go(1),
    retry: () => void load(month, true),
  };
}
