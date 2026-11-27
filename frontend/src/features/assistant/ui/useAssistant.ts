import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getContainer } from '@/container';

import type { AssistantService } from '../application/assistantService';
import { AssistantError, type AssistantMode, type Message, type ModeStatus, type Rating } from '../domain';

export type ModeState = {
  status: 'loading' | 'ready' | 'failed';
  conversationId: number | null;
  messages: Message[];
  /** The question being answered, already shown as the user's bubble. */
  pending: boolean;
  /** Why the last question or the conversation could not be loaded, ready to show. */
  error: string | null;
};

const fresh: ModeState = { status: 'loading', conversationId: null, messages: [], pending: false, error: null };

/** The app's AssistantService from the container, unless a test passes one. */
export function useAssistantService(service?: AssistantService): AssistantService {
  return useMemo(() => service ?? getContainer().assistant, [service]);
}

function sentence(error: unknown): string {
  if (error instanceof AssistantError) {
    if (error.code === 'network') return "Can't reach Fatourati. Check your connection and try again.";
    if (error.code === 'refused') return error.message;
  }
  return 'The assistant could not answer this time. Try again in a moment.';
}

/**
 * The Assistant's conversations: one per mode, each opened at its newest conversation the first time the mode
 * is shown, kept while switching. Asking shows the question at once and waits for the answer; if it fails, the
 * question comes back for the field and the reason is shown.
 */
export function useAssistant(service: AssistantService) {
  const [mode, setMode] = useState<AssistantMode>('standard');
  const [states, setStates] = useState<Record<AssistantMode, ModeState>>({ standard: fresh, beta: fresh });
  const [modes, setModes] = useState<ModeStatus[]>([]);
  const started = useRef<Record<AssistantMode, boolean>>({ standard: false, beta: false });
  const mounted = useRef(true);

  const update = useCallback((target: AssistantMode, change: (state: ModeState) => ModeState) => {
    if (mounted.current) setStates((current) => ({ ...current, [target]: change(current[target]) }));
  }, []);

  const open = useCallback(
    async (target: AssistantMode) => {
      update(target, (state) => ({ ...state, status: 'loading', error: null }));
      try {
        const conversation = await service.latest(target);
        update(target, (state) => ({
          ...state,
          status: 'ready',
          conversationId: conversation?.id ?? null,
          messages: conversation?.messages ?? [],
        }));
      } catch (error) {
        update(target, (state) => ({ ...state, status: 'failed', error: sentence(error) }));
      }
    },
    [service, update],
  );

  useEffect(() => {
    mounted.current = true;
    void service.modes().then((found) => mounted.current && setModes(found));
    return () => {
      mounted.current = false;
    };
  }, [service]);

  useEffect(() => {
    if (started.current[mode]) return;
    started.current[mode] = true;
    void open(mode);
  }, [mode, open]);

  /** Asks the current mode. Returns the question when it failed, so the field can show it again. */
  const ask = useCallback(
    async (question: string): Promise<string | null> => {
      const target = mode;
      const state = states[target];
      if (state.pending || !question.trim()) return null;
      const asked: Message = {
        id: -Date.now(),
        role: 'user',
        content: question.trim(),
        createdAt: new Date().toISOString(),
        kind: null,
        sql: null,
        rating: null,
        table: null,
      };
      update(target, (current) => ({ ...current, pending: true, error: null, messages: [...current.messages, asked] }));
      try {
        const result = await service.ask(question, state.conversationId, target);
        update(target, (current) => ({
          ...current,
          pending: false,
          conversationId: result.conversationId,
          messages: [...current.messages, result.answer],
        }));
        return null;
      } catch (error) {
        update(target, (current) => ({
          ...current,
          pending: false,
          error: sentence(error),
          messages: current.messages.filter((message) => message.id !== asked.id),
        }));
        return question;
      }
    },
    [mode, states, service, update],
  );

  const rate = useCallback(
    async (message: Message, rating: Rating) => {
      const target = mode;
      try {
        const next = await service.rate(message.id, rating, message.rating);
        update(target, (current) => ({
          ...current,
          messages: current.messages.map((item) => (item.id === message.id ? { ...item, rating: next } : item)),
        }));
      } catch (error) {
        update(target, (current) => ({ ...current, error: sentence(error) }));
      }
    },
    [mode, service, update],
  );

  /** "+": a new, empty conversation in the current mode (it is created by the first question). */
  const newConversation = useCallback(() => {
    update(mode, (current) => (current.pending ? current : { ...fresh, status: 'ready' }));
  }, [mode, update]);

  return {
    mode,
    setMode,
    state: states[mode],
    modeStatus: modes.find((status) => status.mode === mode),
    ask,
    rate,
    newConversation,
    retry: () => void open(mode),
  };
}
