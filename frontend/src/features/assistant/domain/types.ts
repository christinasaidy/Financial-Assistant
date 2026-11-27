/**
 * What the Assistant screen works with (design/screens/07 and 08). Plain types: no React, no HTTP.
 */

/** Standard: Claude Sonnet. Beta: the fine-tuned Qwen, for Lebanese Arabizi. Each conversation is one mode. */
export type AssistantMode = 'standard' | 'beta';

export type MessageRole = 'user' | 'assistant';

/** What an answer is: an answer from the data, a clarifying question, "I can't answer that", a short reply, or an error. */
export type AnswerKind = 'answer' | 'clarify' | 'unsupported' | 'reply' | 'error';

export type Rating = 'up' | 'down';

export type Message = {
  id: number;
  role: MessageRole;
  content: string;
  /** A date-time. */
  createdAt: string;
  /** Answers only. */
  kind: AnswerKind | null;
  /** The query that ran, for "Show query" (Beta answers). */
  sql: string | null;
  rating: Rating | null;
  /** When the answer is a table instead of a sentence. */
  table: { columns: string[]; rows: (string | null)[][] } | null;
};

export type Conversation = {
  id: number;
  mode: AssistantMode;
  /** A date-time; the newest conversation of a mode is the one the screen opens. */
  lastMessageAt: string;
  messages: Message[];
};

/** Whether a mode can answer this user now (GET /assistant/modes). */
export type ModeStatus = {
  mode: AssistantMode;
  available: boolean;
  /** When unavailable: not_configured, daily_limit or monthly_cap. */
  reason: string | null;
};

/** The answer to a question, and the conversation it is in (a new one when none was given). */
export type AskResult = { conversationId: number; answer: Message };
