/**
 * The Assistant screen with a fake backend, against design/screens/07 and 08. Today is 26 November 2026.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AssistantService } from '@/features/assistant/application/assistantService';
import { AssistantScreen } from '@/features/assistant/ui/AssistantScreen';

import { FakeAssistantRepository } from './fakes';

const today = () => new Date(2026, 10, 26, 15, 0);
const metrics = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 59, bottom: 34, left: 0, right: 0 } };

async function renderAssistant(repository = new FakeAssistantRepository()) {
  await render(
    <SafeAreaProvider initialMetrics={metrics}>
      <AssistantScreen service={new AssistantService(repository, () => 'key')} today={today} />
    </SafeAreaProvider>,
  );
  await waitFor(() => expect(screen.queryByLabelText('Loading')).toBeNull());
  return repository;
}

async function type(text: string) {
  await fireEvent.changeText(screen.getByLabelText('Message'), text);
}

describe('Assistant with Claude Sonnet (screen 07)', () => {
  it('opens the latest Standard conversation: the day, the question bubble and the answer card', async () => {
    await renderAssistant();
    expect(screen.getByRole('tab', { name: 'Assistant, Claude Sonnet' }).props.accessibilityState).toMatchObject({ selected: true });
    expect(screen.getByText('Today · 26 Nov')).toBeTruthy();
    expect(screen.getByText('How much did I spend on eating out this month?')).toBeTruthy();
    const card = within(screen.getByTestId('message-2'));
    expect(card.getByText('Assistant')).toBeTruthy();
    // The amount is its own bold piece; the Markdown stars are gone.
    expect(card.getByText('$71.50')).toBeTruthy();
    expect(card.queryByText(/\*\*/)).toBeNull();
    expect(screen.getByPlaceholderText('Ask about your spending…')).toBeTruthy();
  });

  it('suggests questions, including last month', async () => {
    await renderAssistant();
    expect(screen.getByRole('button', { name: 'Where can I cut back?' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Compare to October' })).toBeTruthy();
  });

  it('asks: the question shows at once, a thinking card waits, then the answer comes', async () => {
    const repository = new FakeAssistantRepository();
    let release: () => void = () => undefined;
    repository.hold = new Promise((resolve) => (release = resolve));
    await renderAssistant(repository);

    await type('And transport?');
    await fireEvent.press(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByText('And transport?')).toBeTruthy();
    expect(screen.getByTestId('answer-pending')).toBeTruthy();
    expect(screen.getByLabelText('Message').props.value).toBe('');
    expect(screen.queryByRole('button', { name: 'Where can I cut back?' })).toBeNull();

    await act(async () => release());
    await waitFor(() => expect(screen.getByText(/Answer to: And transport\? \(\$12\.00\)/)).toBeTruthy());
    expect(screen.queryByTestId('answer-pending')).toBeNull();
    expect(repository.calls).toContain('ask 7 standard And transport?');
  });

  it('asks a suggestion with one tap', async () => {
    const repository = await renderAssistant();
    await fireEvent.press(screen.getByRole('button', { name: 'Where can I cut back?' }));
    await waitFor(() => expect(repository.calls).toContain('ask 7 standard Where can I cut back?'));
  });

  it('gives the question back and says why when the backend refuses', async () => {
    const repository = new FakeAssistantRepository();
    repository.refuseWith = "You have reached today's limit of Standard questions; try again tomorrow";
    await renderAssistant(repository);
    await type('And transport?');
    await fireEvent.press(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(screen.getByTestId('assistant-notice').props.children).toBe(repository.refuseWith));
    expect(screen.getByLabelText('Message').props.value).toBe('And transport?');
    expect(screen.queryByText('And transport?', { exact: true })).toBeNull();
  });

  it('starts a new conversation with +: empty, and the first question creates it', async () => {
    const repository = await renderAssistant();
    await fireEvent.press(screen.getByRole('button', { name: 'New conversation' }));
    expect(screen.queryByText('How much did I spend on eating out this month?')).toBeNull();
    await type('Hi');
    await fireEvent.press(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(repository.calls).toContain('ask new standard Hi'));
  });

  it('cannot send an empty question, nor while a mode cannot answer', async () => {
    const repository = new FakeAssistantRepository();
    repository.modeList = [
      { mode: 'standard', available: false, reason: 'daily_limit' },
      { mode: 'beta', available: true, reason: null },
    ];
    await renderAssistant(repository);
    await waitFor(() => expect(screen.getByTestId('assistant-notice')).toBeTruthy());
    await type('And transport?');
    expect(screen.getByRole('button', { name: 'Send' }).props.accessibilityState).toMatchObject({ disabled: true });
  });
});

describe('Arabizi Beta with the fine-tuned Qwen (screen 08)', () => {
  async function openBeta(repository = new FakeAssistantRepository()) {
    await renderAssistant(repository);
    await fireEvent.press(screen.getByRole('tab', { name: 'Arabizi Beta, Fine-tuned Qwen' }));
    await waitFor(() => expect(screen.getByText('addeh sraft 3al akl hal shahr?')).toBeTruthy());
    return repository;
  }

  it('shows the BETA note, Arabizi in mono, the Arabizi placeholder and no suggestions', async () => {
    await openBeta();
    expect(screen.getByText('Ask in Lebanese Arabizi. Answers come straight from your receipts.')).toBeTruthy();
    expect(screen.getByText('Arabizi · Beta')).toBeTruthy();
    expect(screen.getByPlaceholderText('Es2al bel arabizi… e.g. addeh dafa3et?')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Where can I cut back?' })).toBeNull();
  });

  it('shows and hides the query that ran', async () => {
    await openBeta();
    expect(screen.queryByText(/SELECT SUM/)).toBeNull();
    await fireEvent.press(screen.getByRole('button', { name: 'Show query' }));
    expect(screen.getByText(/SELECT SUM\(amount_usd\)/)).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Hide query' }));
    expect(screen.queryByText(/SELECT SUM/)).toBeNull();
  });

  it('asks "Was this right?" on the latest answer and stores the rating', async () => {
    const repository = await openBeta();
    await fireEvent.press(screen.getByRole('button', { name: 'Yes, correct' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Yes, correct' }).props.accessibilityState).toMatchObject({ selected: true }));
    expect(repository.calls).toContain('rate 4 up');
  });

  it('keeps each mode’s conversation when switching back', async () => {
    await openBeta();
    await fireEvent.press(screen.getByRole('tab', { name: 'Assistant, Claude Sonnet' }));
    expect(screen.getByText('How much did I spend on eating out this month?')).toBeTruthy();
  });

  it('asks Beta questions in the Beta conversation', async () => {
    const repository = await openBeta();
    await type('w el transport?');
    await fireEvent.press(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(repository.calls).toContain('ask 8 beta w el transport?'));
  });
});

describe('Assistant offline', () => {
  it('says it cannot reach Fatourati, and opens on Try again', async () => {
    const repository = new FakeAssistantRepository();
    repository.offline = true;
    await renderAssistant(repository);
    expect(screen.getByText("Can't reach Fatourati. Check your connection and try again.")).toBeTruthy();
    repository.offline = false;
    await fireEvent.press(screen.getByRole('link', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByText('How much did I spend on eating out this month?')).toBeTruthy());
  });
});
