import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CardsPayload } from '../../api/chat';
import { ChatCards } from './ChatCards';
import { type CardSetState, INITIAL_CARD_STATE } from './cardState';

const DOCTORS: CardsPayload = {
  language: 'en',
  type: 'doctors',
  items: [
    { slot_id: 1, doctor_name: 'Dr. Sara Nabil', specialty: 'Dermatology', clinic: 'Cairo Clinic', location: 'Cairo', start_at: '2026-11-15T10:00:00Z' },
    { slot_id: 2, doctor_name: 'Dr. Omar Hassan', specialty: 'Dermatology', clinic: 'Nile Medical', location: 'Cairo', start_at: '2026-11-16T14:00:00Z' },
  ],
};

const VISIT = { visit_id: 5, start_at: '2026-11-12T10:00:00Z', doctor_name: 'Dr. Sara Nabil', specialty: 'Dermatology', clinic: 'Cairo Clinic' };
const OTHER_VISIT = { ...VISIT, visit_id: 6, doctor_name: 'Dr. Lina Fares' };

function renderCards(cards: CardsPayload, state: CardSetState = INITIAL_CARD_STATE, locked = false) {
  const handlers = { onBook: vi.fn(), onCancelVisit: vi.fn(), onFileComplaint: vi.fn(), onShowOther: vi.fn() };
  render(<ChatCards cards={cards} state={state} locked={locked} {...handlers} />);
  return handlers;
}

function buttons(testId: string): HTMLButtonElement[] {
  return screen.getAllByTestId(testId) as HTMLButtonElement[];
}

describe('doctor cards', () => {
  it('C8: shows the start time in UTC with the suffix', () => {
    renderCards(DOCTORS);
    expect(screen.getByText('Sun 15 Nov, 10:00 UTC')).toBeTruthy();
  });

  it('D6: Book calls the booking handler with the slot id', () => {
    const handlers = renderCards(DOCTORS);
    fireEvent.click(buttons('book-btn')[1]);
    expect(handlers.onBook).toHaveBeenCalledWith(2);
  });

  it('F13: every card is disabled while a turn streams', () => {
    renderCards(DOCTORS, INITIAL_CARD_STATE, true);
    expect(buttons('book-btn').every(b => b.disabled)).toBe(true);
  });

  it('D6: booking shows a spinner and disables the other cards', () => {
    renderCards(DOCTORS, { ...INITIAL_CARD_STATE, busyId: 1 });
    const [first, second] = buttons('book-btn');
    expect(first.textContent).toContain('Booking');
    expect(first.disabled).toBe(true);
    expect(second.disabled).toBe(true);
  });

  it('D6: a booked card shows the badge and siblings are disabled', () => {
    renderCards(DOCTORS, { ...INITIAL_CARD_STATE, doneId: 1 });
    expect(screen.getByTestId('booked-badge').textContent).toBe('Booked');
    expect(buttons('book-btn')).toHaveLength(1);
    expect(buttons('book-btn')[0].disabled).toBe(true);
  });

  it('D7: a taken slot offers other options and leaves siblings bookable', () => {
    const handlers = renderCards(DOCTORS, { ...INITIAL_CARD_STATE, failure: { id: 1, kind: 'slot_taken' } });
    expect(screen.getByText('This slot was just taken')).toBeTruthy();
    fireEvent.click(screen.getByTestId('show-other-btn'));
    expect(handlers.onShowOther).toHaveBeenCalledOnce();
    expect(buttons('book-btn')[0].disabled).toBe(false);
  });

  it('a failed booking shows the error with Retry', () => {
    const handlers = renderCards(DOCTORS, { ...INITIAL_CARD_STATE, failure: { id: 2, kind: 'error' } });
    expect(screen.getByText('Could not book. Try again.')).toBeTruthy();
    fireEvent.click(screen.getByTestId('card-retry-btn'));
    expect(handlers.onBook).toHaveBeenCalledWith(2);
  });
});

describe('cancel cards', () => {
  const CANCEL: CardsPayload = { language: 'en', type: 'cancel_confirm', items: [VISIT, OTHER_VISIT] };

  it('D8: the button names the action and calls cancel with the visit id', () => {
    const handlers = renderCards(CANCEL);
    const [first] = buttons('cancel-confirm-btn');
    expect(first.textContent).toBe('Yes, cancel visit');
    fireEvent.click(first);
    expect(handlers.onCancelVisit).toHaveBeenCalledWith(5);
  });

  it('D8: cancelling shows a spinner and disables the other cards', () => {
    renderCards(CANCEL, { ...INITIAL_CARD_STATE, busyId: 5 });
    expect(buttons('cancel-confirm-btn')[0].textContent).toContain('Cancelling');
    expect(buttons('cancel-confirm-btn').every(b => b.disabled)).toBe(true);
  });

  it('D8: a cancelled card shows the badge', () => {
    renderCards(CANCEL, { ...INITIAL_CARD_STATE, doneId: 5 });
    expect(screen.getByTestId('cancelled-badge')).toBeTruthy();
    expect(buttons('cancel-confirm-btn')[0].disabled).toBe(true);
  });

  it('D8: a visit that is no longer cancellable says so', () => {
    renderCards(CANCEL, { ...INITIAL_CARD_STATE, failure: { id: 5, kind: 'not_cancellable' } });
    expect(screen.getByText('This visit can no longer be cancelled')).toBeTruthy();
  });

  it('F13: cancel cards are disabled while a turn streams', () => {
    renderCards(CANCEL, INITIAL_CARD_STATE, true);
    expect(buttons('cancel-confirm-btn').every(b => b.disabled)).toBe(true);
  });
});

describe('complaint cards', () => {
  const COMPLAINT: CardsPayload = { language: 'en', type: 'visits_for_complaint', items: [VISIT, OTHER_VISIT] };

  it('E6: Select expands the form and a description is required before submit', () => {
    const handlers = renderCards(COMPLAINT);
    fireEvent.click(buttons('select-visit-btn')[0]);
    const submit = screen.getByTestId('submit-complaint-btn') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByTestId('complaint-desc'), { target: { value: '   ' } });
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByTestId('complaint-desc'), { target: { value: 'Long wait' } });
    fireEvent.click(submit);
    expect(handlers.onFileComplaint).toHaveBeenCalledWith(5, 'Long wait');
  });

  it('E6: a filed complaint shows the badge', () => {
    renderCards(COMPLAINT, { ...INITIAL_CARD_STATE, doneId: 5 });
    expect(screen.getByTestId('filed-badge').textContent).toBe('Complaint filed');
  });

  it('a failed complaint keeps the text and offers Retry', () => {
    const onFileComplaint = vi.fn();
    const props = { cards: COMPLAINT, locked: false, onBook: vi.fn(), onCancelVisit: vi.fn(), onFileComplaint, onShowOther: vi.fn() };
    const { rerender } = render(<ChatCards {...props} state={INITIAL_CARD_STATE} />);
    fireEvent.click(buttons('select-visit-btn')[0]);
    fireEvent.change(screen.getByTestId('complaint-desc'), { target: { value: 'Rude staff' } });
    rerender(<ChatCards {...props} state={{ ...INITIAL_CARD_STATE, failure: { id: 5, kind: 'error' } }} />);
    expect(screen.getByText('Could not file the complaint. Try again.')).toBeTruthy();
    expect((screen.getByTestId('complaint-desc') as HTMLTextAreaElement).value).toBe('Rude staff');
    fireEvent.click(screen.getByTestId('card-retry-btn'));
    expect(onFileComplaint).toHaveBeenCalledWith(5, 'Rude staff');
  });

  it('F13: an open complaint form is locked while a turn streams', () => {
    const props = { cards: COMPLAINT, state: INITIAL_CARD_STATE, onBook: vi.fn(), onCancelVisit: vi.fn(), onFileComplaint: vi.fn(), onShowOther: vi.fn() };
    const { rerender } = render(<ChatCards {...props} locked={false} />);
    fireEvent.click(buttons('select-visit-btn')[0]);
    fireEvent.change(screen.getByTestId('complaint-desc'), { target: { value: 'Long wait' } });
    rerender(<ChatCards {...props} locked />);
    expect((screen.getByTestId('complaint-desc') as HTMLTextAreaElement).disabled).toBe(true);
    expect((screen.getByTestId('submit-complaint-btn') as HTMLButtonElement).disabled).toBe(true);
    expect(buttons('select-visit-btn').every(b => b.disabled)).toBe(true);
  });

  it('F13: complaint cards are disabled while a turn streams', () => {
    renderCards(COMPLAINT, INITIAL_CARD_STATE, true);
    expect(buttons('select-visit-btn').every(b => b.disabled)).toBe(true);
  });
});

describe('Arabic cards', () => {
  it('F17: labels and dates are Arabic, right to left, and the database names stay as stored', () => {
    renderCards({ ...DOCTORS, language: 'ar' });
    const container = screen.getByTestId('chat-cards');
    expect(container.getAttribute('dir')).toBe('rtl');
    expect(screen.getAllByTestId('doctor-name').map(name => name.textContent)).toEqual(['Dr. Sara Nabil', 'Dr. Omar Hassan']);
    expect(screen.getAllByText('Dermatology')).toHaveLength(2);
    expect(screen.getByText('Cairo Clinic, Cairo').tagName).toBe('BDI');
    expect(screen.getByText('الأحد 15 نوفمبر، 10:00 UTC')).toBeTruthy();
    expect(buttons('book-btn').map(b => b.textContent)).toEqual(['احجز', 'احجز']);
  });

  it('F17: card states and the complaint form are Arabic too', () => {
    renderCards({ ...DOCTORS, language: 'ar' }, { ...INITIAL_CARD_STATE, doneId: 1 });
    expect(screen.getByTestId('booked-badge').textContent).toBe('تم الحجز');
  });

  it('F17: an Arabic complaint card asks what happened in Arabic', () => {
    renderCards({ language: 'ar', type: 'visits_for_complaint', items: [VISIT] });
    fireEvent.click(screen.getByTestId('select-visit-btn'));
    expect(screen.getByText('ماذا حدث؟')).toBeTruthy();
    expect(screen.getByTestId('submit-complaint-btn').textContent).toBe('أرسل الشكوى');
  });

  it('F17: English cards are left to right with English labels', () => {
    renderCards(DOCTORS);
    expect(screen.getByTestId('chat-cards').getAttribute('dir')).toBe('ltr');
    expect(buttons('book-btn').map(b => b.textContent)).toEqual(['Book', 'Book']);
  });
});
