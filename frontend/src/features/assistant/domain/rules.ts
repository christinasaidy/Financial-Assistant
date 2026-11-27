/**
 * The Assistant screen's rules, as pure functions.
 */
import type { AssistantMode, Message, ModeStatus } from './types';

/** A piece of an answer's text: amounts are drawn in bold Geist Mono, **bold** words in bold (design/reference/07). */
export type TextPiece = { text: string; style: 'plain' | 'amount' | 'bold' };

/** "$71.50", "$ 80", "450,000 LBP", "3,150,000 LL", "89,500 LBP". */
const AMOUNT = /(\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:LBP|LL)\b)/g;

function splitAmounts(text: string, outside: TextPiece['style']): TextPiece[] {
  const pieces: TextPiece[] = [];
  let last = 0;
  for (const match of text.matchAll(AMOUNT)) {
    const start = match.index ?? 0;
    if (start > last) pieces.push({ text: text.slice(last, start), style: outside });
    pieces.push({ text: match[0], style: 'amount' });
    last = start + match[0].length;
  }
  if (last < text.length) pieces.push({ text: text.slice(last), style: outside });
  return pieces;
}

/**
 * An answer's text in pieces: Markdown **bold** becomes bold (the markers are dropped), and every amount is an
 * amount piece. Other text is plain.
 */
export function answerPieces(text: string): TextPiece[] {
  const pieces: TextPiece[] = [];
  const parts = text.split(/\*\*(.+?)\*\*/g);
  parts.forEach((part, index) => {
    if (part === '') return;
    if (index % 2 === 1) {
      for (const piece of splitAmounts(part, 'bold')) pieces.push(piece);
    } else {
      pieces.push(...splitAmounts(part, 'plain'));
    }
  });
  return pieces;
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** Which day a message belongs to, for the "Today · 26 Nov" separators: the local date, "2026-11-26". */
export function dayKey(createdAt: string): string {
  const date = new Date(createdAt);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** "Today", "Yesterday", or nothing, before the date of a day separator. */
export function relativeDay(createdAt: string, today: Date): 'Today' | 'Yesterday' | null {
  const date = new Date(createdAt);
  if (sameDay(date, today)) return 'Today';
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  return sameDay(date, yesterday) ? 'Yesterday' : null;
}

/** Messages grouped by day, in order, for the separators. */
export function byDay(messages: readonly Message[]): { day: string; first: string; messages: Message[] }[] {
  const groups: { day: string; first: string; messages: Message[] }[] = [];
  for (const message of messages) {
    const day = dayKey(message.createdAt);
    const group = groups[groups.length - 1];
    if (group && group.day === day) group.messages.push(message);
    else groups.push({ day, first: message.createdAt, messages: [message] });
  }
  return groups;
}

/** The Beta answer that asks "Was this right?": the latest one that answered from the data. */
export function ratableAnswerId(messages: readonly Message[], mode: AssistantMode): number | null {
  if (mode !== 'beta') return null;
  const last = messages[messages.length - 1];
  return last && last.role === 'assistant' && last.kind === 'answer' ? last.id : null;
}

/** Why a mode cannot be asked now, in words; null when it can. */
export function unavailableSentence(status: ModeStatus | undefined): string | null {
  if (!status || status.available) return null;
  switch (status.reason) {
    case 'daily_limit':
      return 'You have asked today’s Standard questions. Try again tomorrow, or ask the Arabizi Beta.';
    case 'monthly_cap':
      return 'The Standard assistant is resting until next month. The Arabizi Beta still answers.';
    default:
      return 'This assistant is not set up on this server yet.';
  }
}
