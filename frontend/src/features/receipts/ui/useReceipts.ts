import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getContainer } from '@/container';

import type { ReceiptsService } from '../application/receiptsService';
import { ReceiptsError, type ReceiptMonth, type ReceiptPage } from '../domain';

export type Loadable<T> = { status: 'loading' } | { status: 'failed'; error: ReceiptsError } | { status: 'loaded'; data: T };

/** The app's ReceiptsService from the container, unless a test passes one. */
export function useReceiptsService(service?: ReceiptsService): ReceiptsService {
  return useMemo(() => service ?? getContainer().receipts, [service]);
}

function asError(error: unknown): ReceiptsError {
  return error instanceof ReceiptsError ? error : new ReceiptsError('unexpected', String(error));
}

/**
 * The month on the Receipts tab and its receipts: starts on the current month, moves back or forward, and loads
 * again whenever the tab comes back into view (after a scan or a change on a receipt's page).
 */
export function useReceiptMonth(service: ReceiptsService, today: () => Date = () => new Date()) {
  const [month, setMonth] = useState(() => {
    const now = today();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [state, setState] = useState<Loadable<ReceiptMonth>>({ status: 'loading' });
  const latest = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (target: Date) => {
      const request = ++latest.current;
      try {
        const data = await service.loadMonth(target);
        if (mounted.current && request === latest.current) setState({ status: 'loaded', data });
      } catch (error) {
        if (mounted.current && request === latest.current) setState({ status: 'failed', error: asError(error) });
      }
    },
    [service],
  );

  useFocusEffect(
    useCallback(() => {
      void load(month);
    }, [load, month]),
  );

  const go = (by: number) => {
    setState({ status: 'loading' });
    setMonth((current) => new Date(current.getFullYear(), current.getMonth() + by, 1));
  };

  return {
    month,
    state,
    previous: () => go(-1),
    next: () => go(1),
    retry: () => {
      setState({ status: 'loading' });
      void load(month);
    },
  };
}

/** One receipt's page; loads again when it comes back into view (after changing its category or items). */
export function useReceiptPage(service: ReceiptsService, id: number) {
  const [state, setState] = useState<Loadable<ReceiptPage>>({ status: 'loading' });
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await service.loadReceipt(id);
      if (mounted.current) setState({ status: 'loaded', data });
    } catch (error) {
      if (mounted.current) setState({ status: 'failed', error: asError(error) });
    }
  }, [service, id]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  return {
    state,
    retry: () => {
      setState({ status: 'loading' });
      void load();
    },
  };
}
