import { formatDate, formatTime, monthName, parseApiDate, toApiMonth } from '@/shared/format/dates';

describe('dates', () => {
  it('formats dd/mm/yyyy', () => {
    expect(formatDate(new Date(2026, 10, 18, 18, 42))).toBe('18/11/2026');
    expect(formatDate(new Date(2026, 0, 5))).toBe('05/01/2026');
  });

  it('formats a 24-hour time', () => {
    expect(formatTime(new Date(2026, 10, 18, 18, 42))).toBe('18:42');
    expect(formatTime(new Date(2026, 10, 18, 7, 5))).toBe('07:05');
    expect(formatTime(new Date(2026, 10, 18, 0, 0))).toBe('00:00');
  });

  it('reads an API date as that calendar day, whatever the time zone', () => {
    const date = parseApiDate('2026-11-18');
    expect([date.getFullYear(), date.getMonth(), date.getDate()]).toEqual([2026, 10, 18]);
    expect(formatDate('2026-11-18')).toBe('18/11/2026');
  });

  it('reads an API date-time as an instant', () => {
    expect(parseApiDate('2026-11-18T16:42:00Z').getTime()).toBe(Date.UTC(2026, 10, 18, 16, 42));
  });

  it('refuses text that is not a date', () => {
    expect(() => parseApiDate('yesterday')).toThrow('Not a date');
  });

  it('names the month and builds the API month', () => {
    expect(monthName('2026-11-18')).toBe('November');
    expect(toApiMonth(new Date(2026, 2, 1))).toBe('2026-03');
  });
});
