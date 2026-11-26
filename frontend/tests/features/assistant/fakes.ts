import type { AssistantRepository, ConversationSummary } from '@/features/assistant/application/interfaces';
import { AssistantError, type AskResult, type AssistantMode, type Conversation, type Message, type ModeStatus, type Rating } from '@/features/assistant/domain';

export function message(id: number, role: Message['role'], content: string, createdAt: string, extra: Partial<Message> = {}): Message {
  return { id, role, content, createdAt, kind: role === 'assistant' ? 'answer' : null, sql: null, rating: null, table: null, ...extra };
}

/** A Standard conversation from the design (screen 07). */
export const standardTalk: Conversation = {
  id: 7,
  mode: 'standard',
  lastMessageAt: '2026-11-26T09:01:00Z',
  messages: [
    message(1, 'user', 'How much did I spend on eating out this month?', '2026-11-26T09:00:00Z'),
    message(2, 'assistant', 'You’ve spent **$71.50** on eating out in November, $8.50 under your $80 budget with 4 days to go.', '2026-11-26T09:00:05Z'),
  ],
};

/** A Beta conversation from the design (screen 08). */
export const betaTalk: Conversation = {
  id: 8,
  mode: 'beta',
  lastMessageAt: '2026-11-26T10:00:05Z',
  messages: [
    message(3, 'user', 'addeh sraft 3al akl hal shahr?', '2026-11-26T10:00:00Z'),
    message(4, 'assistant', 'Sraft $71.50 3al akl hal shahr.', '2026-11-26T10:00:05Z', {
      sql: "SELECT SUM(amount_usd)\nFROM receipts\nWHERE category = 'Eating out'",
    }),
  ],
};

/** An in-memory assistant backend. `answer` decides what each question gets back. */
export class FakeAssistantRepository implements AssistantRepository {
  conversationsById = new Map<number, Conversation>([
    [7, structuredClone(standardTalk)],
    [8, structuredClone(betaTalk)],
  ]);
  modeList: ModeStatus[] = [
    { mode: 'standard', available: true, reason: null },
    { mode: 'beta', available: true, reason: null },
  ];
  offline = false;
  refuseWith: string | null = null;
  /** Holds the next answer until released, to see the waiting state. */
  hold: Promise<void> | null = null;
  calls: string[] = [];
  private nextId = 100;

  async ask(question: string, conversationId: number | null, mode: AssistantMode, key: string): Promise<AskResult> {
    this.record(`ask ${conversationId ?? 'new'} ${mode} ${question}`);
    if (!key) throw new Error('no idempotency key');
    if (this.hold) await this.hold;
    if (this.refuseWith) throw new AssistantError('refused', this.refuseWith);
    const id = conversationId ?? this.nextId++;
    const answer = message(this.nextId++, 'assistant', `Answer to: ${question} ($12.00)`, '2026-11-26T11:00:00Z', {
      sql: mode === 'beta' ? 'SELECT 1' : null,
    });
    const existing = this.conversationsById.get(id) ?? { id, mode, lastMessageAt: '', messages: [] };
    existing.messages.push(message(this.nextId++, 'user', question, '2026-11-26T11:00:00Z'), answer);
    this.conversationsById.set(id, existing);
    return { conversationId: id, answer };
  }

  async conversations(): Promise<ConversationSummary[]> {
    this.record('conversations');
    return [...this.conversationsById.values()].map(({ id, mode, lastMessageAt }) => ({ id, mode, lastMessageAt }));
  }

  async conversation(id: number): Promise<Conversation> {
    this.record(`conversation ${id}`);
    const found = this.conversationsById.get(id);
    if (!found) throw new AssistantError('refused', 'No such conversation');
    return structuredClone(found);
  }

  async rate(messageId: number, rating: Rating | null): Promise<void> {
    this.record(`rate ${messageId} ${rating ?? 'none'}`);
  }

  async modes(): Promise<ModeStatus[]> {
    this.record('modes');
    return this.modeList;
  }

  private record(call: string): void {
    this.calls.push(call);
    if (this.offline) throw new AssistantError('network', 'Could not reach the server');
  }
}
