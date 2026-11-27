import { AssistantError, type AskResult, type AssistantMode, type Conversation, type ModeStatus, type Rating } from '../domain';
import type { AssistantRepository } from './interfaces';

function asAssistantError(error: unknown): AssistantError {
  if (error instanceof AssistantError) return error;
  return new AssistantError('unexpected', error instanceof Error ? error.message : String(error));
}

/** A key that makes a retried question come back with its first answer instead of being answered twice. */
export function newIdempotencyKey(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 12)}`;
}

/**
 * The Assistant use cases: open a mode's latest conversation, ask, rate an answer, and see which modes can
 * answer. Depends only on the AssistantRepository interface. Throws AssistantError.
 */
export class AssistantService {
  private readonly repository: AssistantRepository;
  private readonly makeKey: () => string;

  constructor(repository: AssistantRepository, makeKey: () => string = newIdempotencyKey) {
    this.repository = repository;
    this.makeKey = makeKey;
  }

  /** The mode's newest conversation with its messages, or null when the user has none in that mode. */
  async latest(mode: AssistantMode): Promise<Conversation | null> {
    try {
      const newest = (await this.repository.conversations())
        .filter((conversation) => conversation.mode === mode)
        .sort((a, b) => b.lastMessageAt.localeCompare(a.lastMessageAt))[0];
      return newest ? await this.repository.conversation(newest.id) : null;
    } catch (error) {
      throw asAssistantError(error);
    }
  }

  /** Asks in the conversation, or starts a new one in `mode`. Questions are trimmed; empty ones are refused. */
  async ask(question: string, conversationId: number | null, mode: AssistantMode): Promise<AskResult> {
    const text = question.trim();
    if (!text) throw new AssistantError('refused', 'Type a question first.');
    try {
      return await this.repository.ask(text, conversationId, mode, this.makeKey());
    } catch (error) {
      throw asAssistantError(error);
    }
  }

  /** Rates an answer; the same rating again clears it. */
  async rate(messageId: number, rating: Rating, current: Rating | null): Promise<Rating | null> {
    const next = current === rating ? null : rating;
    try {
      await this.repository.rate(messageId, next);
      return next;
    } catch (error) {
      throw asAssistantError(error);
    }
  }

  /** Which modes can answer now; when this cannot be read, both are treated as available (the ask will say). */
  async modes(): Promise<ModeStatus[]> {
    try {
      return await this.repository.modes();
    } catch {
      return [
        { mode: 'standard', available: true, reason: null },
        { mode: 'beta', available: true, reason: null },
      ];
    }
  }
}
