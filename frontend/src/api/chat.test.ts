import { describe, expect, it } from 'vitest';
import { type StreamEvent, createSseParser, formatUtc, intentLabel, relativeTime } from './chat';

function parseAll(chunks: string[]): StreamEvent[] {
  const events: StreamEvent[] = [];
  const parser = createSseParser(e => events.push(e));
  for (const chunk of chunks) parser.push(chunk);
  parser.end();
  return events;
}

const STREAM = [
  'event: session\ndata: {"session_id": 7}\n\n',
  'event: intent\ndata: {"intent": "visit.book"}\n\n',
  'event: token\ndata: {"text": "Here "}\n\n',
  'event: token\ndata: {"text": "you go"}\n\n',
  'event: cards\ndata: {"type": "doctors", "items": [{"slot_id": 1, "doctor_name": "Dr. Sara", "specialty": "Dermatology", "clinic": "Cairo Clinic", "location": "Cairo", "start_at": "2026-12-15T10:00:00Z"}]}\n\n',
  'event: done\ndata: {}\n\n',
].join('');

describe('stream parser', () => {
  it('F12: parses every event type in order, cards after the last token', () => {
    const events = parseAll([STREAM]);
    expect(events.map(e => e.event)).toEqual(['session', 'intent', 'token', 'token', 'cards', 'done']);
    expect(events[0]).toEqual({ event: 'session', session_id: 7 });
    expect(events[1]).toEqual({ event: 'intent', intent: 'visit.book' });
    const cards = events[4];
    expect(cards.event === 'cards' && cards.cards.type).toBe('doctors');
    expect(cards.event === 'cards' && cards.cards.items[0]).toMatchObject({ slot_id: 1, doctor_name: 'Dr. Sara' });
  });

  it('F12: an event split across chunks at any byte boundary parses the same', () => {
    const whole = parseAll([STREAM]);
    for (let cut = 1; cut < STREAM.length; cut += 1) {
      expect(parseAll([STREAM.slice(0, cut), STREAM.slice(cut)])).toEqual(whole);
    }
  });

  it('F12: one character per chunk parses the same', () => {
    expect(parseAll(STREAM.split(''))).toEqual(parseAll([STREAM]));
  });

  it('accepts CRLF line endings and ignores comment lines', () => {
    const crlf = ': keep-alive\r\nevent: token\r\ndata: {"text": "hi"}\r\n\r\n';
    expect(parseAll([crlf])).toEqual([{ event: 'token', text: 'hi' }]);
  });

  it('parses the error event', () => {
    const events = parseAll(['event: error\ndata: {"code": "turn_error", "message": "Something went wrong."}\n\n']);
    expect(events).toEqual([{ event: 'error', code: 'turn_error', message: 'Something went wrong.' }]);
  });

  it('flushes a final event that has no trailing blank line', () => {
    expect(parseAll(['event: done\ndata: {}'])).toEqual([{ event: 'done' }]);
  });

  it('ignores unknown event names', () => {
    expect(parseAll(['event: mystery\ndata: {}\n\nevent: done\ndata: {}\n\n'])).toEqual([{ event: 'done' }]);
  });
});

describe('intent label map', () => {
  it('F6: maps every intent code to its sidebar label and null to New chat', () => {
    expect(intentLabel('visit.book')).toBe('Book a visit');
    expect(intentLabel('visit.check')).toBe('My visits');
    expect(intentLabel('visit.cancel')).toBe('Cancel a visit');
    expect(intentLabel('complaint.file')).toBe('File a complaint');
    expect(intentLabel('complaint.check')).toBe('My complaints');
    expect(intentLabel('qa.db')).toBe('Clinic question');
    expect(intentLabel('qa.kb')).toBe('Insurance question');
    expect(intentLabel('other')).toBe('Chat');
    expect(intentLabel(null)).toBe('New chat');
  });

  it('F6: an unknown code falls back to Chat instead of leaking the raw code', () => {
    expect(intentLabel('visit.unknown')).toBe('Chat');
  });
});

describe('time formatting', () => {
  it('C8: the tests run in a non-UTC zone so a local-time formatter would fail', () => {
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('Asia/Tokyo');
    expect(new Date('2026-11-15T10:00:00Z').getTimezoneOffset()).toBe(-540);
  });

  it('C8: shows the UTC wall time with a UTC suffix and no conversion', () => {
    expect(formatUtc('2026-11-15T10:00:00Z')).toBe('Sun 15 Nov, 10:00 UTC');
    expect(formatUtc('2026-11-15T23:30:00+00:00')).toBe('Sun 15 Nov, 23:30 UTC');
  });

  it('relative time uses the injected clock', () => {
    const now = new Date('2026-11-15T12:00:00Z');
    expect(relativeTime('2026-11-15T11:59:30Z', now)).toBe('just now');
    expect(relativeTime('2026-11-15T11:45:00Z', now)).toBe('15 min ago');
    expect(relativeTime('2026-11-15T09:00:00Z', now)).toBe('3 h ago');
    expect(relativeTime('2026-11-14T10:00:00Z', now)).toBe('Yesterday');
    expect(relativeTime('2026-11-10T10:00:00Z', now)).toBe('5 days ago');
  });
});
