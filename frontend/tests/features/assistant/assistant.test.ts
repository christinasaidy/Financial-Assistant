import { AssistantService } from '@/features/assistant/application/assistantService';
import { ApiAssistantRepository, ASK_TIMEOUT_MS } from '@/features/assistant/data/apiAssistantRepository';
import { answerPieces, byDay, ratableAnswerId, relativeDay, unavailableSentence } from '@/features/assistant/domain';
import { createHttpClient } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';
import { betaTalk, FakeAssistantRepository, message, standardTalk } from './fakes';

describe('answer text', () => {
  it('draws amounts in bold mono and Markdown **bold** without its stars', () => {
    expect(answerPieces('You’ve spent **$71.50** on eating out, $8.50 under your $80 budget.')).toEqual([
      { text: 'You’ve spent ', style: 'plain' },
      { text: '$71.50', style: 'amount' },
      { text: ' on eating out, ', style: 'plain' },
      { text: '$8.50', style: 'amount' },
      { text: ' under your ', style: 'plain' },
      { text: '$80', style: 'amount' },
      { text: ' budget.', style: 'plain' },
    ]);
    expect(answerPieces('Zaatar w Zeit: 450,000 LBP, **mostly lunch**')).toEqual([
      { text: 'Zaatar w Zeit: ', style: 'plain' },
      { text: '450,000 LBP', style: 'amount' },
      { text: ', ', style: 'plain' },
      { text: 'mostly lunch', style: 'bold' },
    ]);
  });

  it('groups messages by day and names today and yesterday', () => {
    const today = new Date(2026, 10, 26, 15, 0);
    const messages = [
      message(1, 'user', 'a', new Date(2026, 10, 25, 9).toISOString()),
      message(2, 'assistant', 'b', new Date(2026, 10, 25, 9, 1).toISOString()),
      message(3, 'user', 'c', new Date(2026, 10, 26, 9).toISOString()),
    ];
    expect(byDay(messages).map((group) => [group.day, group.messages.length])).toEqual([
      ['2026-11-25', 2],
      ['2026-11-26', 1],
    ]);
    expect(relativeDay(messages[0]!.createdAt, today)).toBe('Yesterday');
    expect(relativeDay(messages[2]!.createdAt, today)).toBe('Today');
    expect(relativeDay(new Date(2026, 10, 20).toISOString(), today)).toBeNull();
  });

  it('asks "Was this right?" only on Beta’s latest data answer', () => {
    expect(ratableAnswerId(betaTalk.messages, 'beta')).toBe(4);
    expect(ratableAnswerId(standardTalk.messages, 'standard')).toBeNull();
    expect(ratableAnswerId([...betaTalk.messages, message(9, 'user', 'w el transport?', '2026-11-26T10:01:00Z')], 'beta')).toBeNull();
    expect(ratableAnswerId([message(5, 'assistant', 'hi', '2026-11-26T10:00:00Z', { kind: 'reply' })], 'beta')).toBeNull();
  });

  it('says why a mode cannot answer', () => {
    expect(unavailableSentence({ mode: 'standard', available: true, reason: null })).toBeNull();
    expect(unavailableSentence({ mode: 'standard', available: false, reason: 'daily_limit' })).toMatch(/tomorrow/);
    expect(unavailableSentence({ mode: 'beta', available: false, reason: 'not_configured' })).toBe('This assistant is not set up on this server yet.');
  });
});

describe('AssistantService', () => {
  it('opens each mode’s newest conversation, or none', async () => {
    const repository = new FakeAssistantRepository();
    const service = new AssistantService(repository, () => 'key');
    expect((await service.latest('beta'))?.id).toBe(8);
    expect((await service.latest('standard'))?.id).toBe(7);
    repository.conversationsById.clear();
    expect(await service.latest('beta')).toBeNull();
  });

  it('asks with a fresh idempotency key, trimmed, and refuses an empty question', async () => {
    const repository = new FakeAssistantRepository();
    const service = new AssistantService(repository, () => 'key-1');
    const result = await service.ask('  And transport?  ', 7, 'standard');
    expect(repository.calls).toContain('ask 7 standard And transport?');
    expect(result.conversationId).toBe(7);
    await expect(service.ask('   ', 7, 'standard')).rejects.toMatchObject({ code: 'refused' });
  });

  it('rates, and the same rating again clears it', async () => {
    const repository = new FakeAssistantRepository();
    const service = new AssistantService(repository);
    expect(await service.rate(4, 'up', null)).toBe('up');
    expect(await service.rate(4, 'up', 'up')).toBeNull();
    expect(repository.calls).toEqual(['rate 4 up', 'rate 4 none']);
  });
});

describe('ApiAssistantRepository', () => {
  function repositoryWith(...replies: Parameters<typeof fetchMock>) {
    const { fetchFn, requests } = fetchMock(...replies);
    const http = createHttpClient({ baseUrl: 'http://192.168.1.23:8000', getToken: () => 'jwt', onUnauthorized: jest.fn(), fetchFn });
    return { repository: new ApiAssistantRepository(http), requests };
  }

  const answerDto = {
    id: 41,
    role: 'assistant',
    content: 'Transport is at $63.00.',
    created_at: '2026-11-26T09:00:00Z',
    kind: 'answer',
    sql: 'SELECT 1',
    rating: null,
    source_receipts: [],
    columns: null,
    rows: null,
    conversation_id: 7,
    assistant_mode: 'standard',
  };

  it('starts a conversation in a mode, sends the idempotency key, and waits long for the answer', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: answerDto });
    const result = await repository.ask('How much?', null, 'standard', 'k-1');
    expect(requests[0]).toMatchObject({
      url: 'http://192.168.1.23:8000/assistant/ask',
      method: 'POST',
      headers: { 'Idempotency-Key': 'k-1' },
      body: { question: 'How much?', assistant_mode: 'standard' },
    });
    expect(result).toEqual({
      conversationId: 7,
      answer: { id: 41, role: 'assistant', content: 'Transport is at $63.00.', createdAt: '2026-11-26T09:00:00Z', kind: 'answer', sql: 'SELECT 1', rating: null, table: null },
    });
    expect(ASK_TIMEOUT_MS).toBeGreaterThan(15_000);
  });

  it('continues a conversation by its id only (its mode is fixed)', async () => {
    const { repository, requests } = repositoryWith({ status: 200, body: answerDto });
    await repository.ask('And transport?', 7, 'standard', 'k-2');
    expect(requests[0]?.body).toEqual({ question: 'And transport?', conversation_id: 7 });
  });

  it('shows the backend’s sentence when it refuses (today’s limit)', async () => {
    const { repository } = repositoryWith({ status: 429, body: { detail: "You have reached today's limit of Standard questions; try again tomorrow" } });
    await expect(repository.ask('x', 7, 'standard', 'k')).rejects.toMatchObject({
      code: 'refused',
      message: "You have reached today's limit of Standard questions; try again tomorrow",
    });
  });

  it('rates with PUT, clears with DELETE, and reads the modes', async () => {
    const { repository, requests } = repositoryWith(
      { status: 204 },
      { status: 204 },
      { status: 200, body: [{ mode: 'standard', available: false, models: [], reason: 'daily_limit' }] },
    );
    await repository.rate(41, 'down');
    await repository.rate(41, null);
    expect(await repository.modes()).toEqual([{ mode: 'standard', available: false, reason: 'daily_limit' }]);
    expect(requests.map((request) => `${request.method} ${request.url}`)).toEqual([
      'PUT http://192.168.1.23:8000/assistant/messages/41/rating',
      'DELETE http://192.168.1.23:8000/assistant/messages/41/rating',
      'GET http://192.168.1.23:8000/assistant/modes',
    ]);
    expect(requests[0]?.body).toEqual({ rating: 'down' });
  });
});
