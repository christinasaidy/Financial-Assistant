import { ApiError, NetworkError, type HttpClient } from '@/shared/api/httpClient';

import type { AssistantRepository, ConversationSummary } from '../application/interfaces';
import { AssistantError, type AnswerKind, type AskResult, type AssistantMode, type Conversation, type Message, type ModeStatus, type Rating } from '../domain';

/** The backend's shapes (backend/app/api/assistant/routes.py), snake_case. */
export type MessageDto = {
  id: number;
  role: string;
  content: string;
  created_at: string;
  kind: string | null;
  sql: string | null;
  rating: string | null;
  columns?: string[] | null;
  rows?: (string | null)[][] | null;
};

export type ConversationDto = {
  id: number;
  title: string;
  created_at: string;
  last_message_at: string;
  message_count: number;
  assistant_mode: string;
};

export type AnswerDto = MessageDto & { conversation_id: number; assistant_mode: string };

export type ModeDto = { mode: string; available: boolean; models: string[]; reason?: string | null };

const KINDS: readonly AnswerKind[] = ['answer', 'clarify', 'unsupported', 'reply', 'error'];

/** Sonnet can take a while to answer, with its tools; the client's 15 s is for everything else. */
export const ASK_TIMEOUT_MS = 90_000;

function toMode(value: string): AssistantMode {
  return value === 'standard' ? 'standard' : 'beta';
}

export function toMessage(dto: MessageDto): Message {
  return {
    id: dto.id,
    role: dto.role === 'user' ? 'user' : 'assistant',
    content: dto.content,
    createdAt: dto.created_at,
    kind: KINDS.find((kind) => kind === dto.kind) ?? null,
    sql: dto.sql,
    rating: dto.rating === 'up' || dto.rating === 'down' ? dto.rating : null,
    table: dto.columns && dto.rows ? { columns: dto.columns, rows: dto.rows } : null,
  };
}

function toSummary(dto: ConversationDto): ConversationSummary {
  return { id: dto.id, mode: toMode(dto.assistant_mode), lastMessageAt: dto.last_message_at };
}

/** HTTP failure -> the error the screen understands. A 4xx carries the backend's sentence (today's limit, ...). */
export function toAssistantError(error: unknown): AssistantError {
  if (error instanceof AssistantError) return error;
  if (error instanceof NetworkError) return new AssistantError('network', error.message);
  if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401) {
    return new AssistantError('refused', error.detail);
  }
  if (error instanceof ApiError) return new AssistantError('unexpected', error.detail);
  return new AssistantError('unexpected', error instanceof Error ? error.message : String(error));
}

/**
 * AssistantRepository against the Fatourati backend: POST /assistant/ask, GET /assistant/conversations(/{id}),
 * PUT and DELETE /assistant/messages/{id}/rating, GET /assistant/modes.
 */
export class ApiAssistantRepository implements AssistantRepository {
  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  ask(question: string, conversationId: number | null, mode: AssistantMode, idempotencyKey: string): Promise<AskResult> {
    return this.call(async () => {
      const dto = await this.http.request<AnswerDto>('/assistant/ask', {
        method: 'POST',
        body: conversationId === null ? { question, assistant_mode: mode } : { question, conversation_id: conversationId },
        headers: { 'Idempotency-Key': idempotencyKey },
        timeoutMs: ASK_TIMEOUT_MS,
      });
      return { conversationId: dto.conversation_id, answer: toMessage(dto) };
    });
  }

  conversations(): Promise<ConversationSummary[]> {
    return this.call(async () => (await this.http.request<ConversationDto[]>('/assistant/conversations')).map(toSummary));
  }

  conversation(id: number): Promise<Conversation> {
    return this.call(async () => {
      const dto = await this.http.request<ConversationDto & { messages: MessageDto[] }>(`/assistant/conversations/${id}`);
      return { ...toSummary(dto), messages: dto.messages.map(toMessage) };
    });
  }

  rate(messageId: number, rating: Rating | null): Promise<void> {
    return this.call(async () => {
      if (rating === null) await this.http.request(`/assistant/messages/${messageId}/rating`, { method: 'DELETE' });
      else await this.http.request(`/assistant/messages/${messageId}/rating`, { method: 'PUT', body: { rating } });
    });
  }

  modes(): Promise<ModeStatus[]> {
    return this.call(async () =>
      (await this.http.request<ModeDto[]>('/assistant/modes')).map((dto) => ({
        mode: toMode(dto.mode),
        available: dto.available,
        reason: dto.reason ?? null,
      })),
    );
  }

  private async call<T>(run: () => Promise<T>): Promise<T> {
    try {
      return await run();
    } catch (error) {
      throw toAssistantError(error);
    }
  }
}
