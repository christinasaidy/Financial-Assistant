import type { AskResult, AssistantMode, Conversation, ModeStatus, Rating } from '../domain';

/** A conversation as the list gives it: no messages. */
export type ConversationSummary = Omit<Conversation, 'messages'>;

/**
 * The port of the Assistant feature: what AssistantService needs from the backend. The data layer implements it
 * (apiAssistantRepository.ts); tests use a fake. Implementations throw AssistantError.
 */
export interface AssistantRepository {
  /** Answers a question; a new conversation in `mode` when `conversationId` is null. Waits for the answer. */
  ask(question: string, conversationId: number | null, mode: AssistantMode, idempotencyKey: string): Promise<AskResult>;
  /** The user's conversations, newest activity first. */
  conversations(): Promise<ConversationSummary[]>;
  /** One conversation with every message. */
  conversation(id: number): Promise<Conversation>;
  /** Rates an answer, or clears its rating with null. */
  rate(messageId: number, rating: Rating | null): Promise<void>;
  /** Whether each mode can answer this user now. */
  modes(): Promise<ModeStatus[]>;
}
