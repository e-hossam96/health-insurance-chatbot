import { type ReactNode, useState } from 'react';
import { type CardLanguage, type CardsPayload, type DoctorCardItem, type VisitCardItem, formatUtc } from '../../api/chat';
import type { CardFailureKind, CardSetState } from './cardState';

type CardStatus = 'default' | 'busy' | 'done' | CardFailureKind;

function statusFor(state: CardSetState, id: number): CardStatus {
  if (state.doneId === id) return 'done';
  if (state.busyId === id) return 'busy';
  if (state.failure?.id === id) return state.failure.kind;
  return 'default';
}

type CardText = {
  book: string;
  booking: string;
  booked: string;
  slotTaken: string;
  showOther: string;
  bookFailed: string;
  retry: string;
  cancelVisit: string;
  cancelling: string;
  cancelled: string;
  notCancellable: string;
  cancelFailed: string;
  select: string;
  whatHappened: string;
  submitComplaint: string;
  submitting: string;
  complaintFiled: string;
  complaintFailed: string;
  close: string;
};

export const CARD_TEXT: Record<CardLanguage, CardText> = {
  en: {
    book: 'Book',
    booking: 'Booking…',
    booked: 'Booked',
    slotTaken: 'This slot was just taken',
    showOther: 'Show other options',
    bookFailed: 'Could not book. Try again.',
    retry: 'Retry',
    cancelVisit: 'Yes, cancel visit',
    cancelling: 'Cancelling…',
    cancelled: 'Cancelled',
    notCancellable: 'This visit can no longer be cancelled',
    cancelFailed: 'Could not cancel. Try again.',
    select: 'Select',
    whatHappened: 'What happened?',
    submitComplaint: 'Submit complaint',
    submitting: 'Submitting…',
    complaintFiled: 'Complaint filed',
    complaintFailed: 'Could not file the complaint. Try again.',
    close: 'Cancel',
  },
  ar: {
    book: 'احجز',
    booking: 'جارٍ الحجز…',
    booked: 'تم الحجز',
    slotTaken: 'حُجز هذا الموعد للتو',
    showOther: 'اعرض خيارات أخرى',
    bookFailed: 'تعذّر الحجز. حاول مرة أخرى.',
    retry: 'أعد المحاولة',
    cancelVisit: 'نعم، ألغِ الموعد',
    cancelling: 'جارٍ الإلغاء…',
    cancelled: 'تم الإلغاء',
    notCancellable: 'لم يعد بالإمكان إلغاء هذا الموعد',
    cancelFailed: 'تعذّر الإلغاء. حاول مرة أخرى.',
    select: 'اختر',
    whatHappened: 'ماذا حدث؟',
    submitComplaint: 'أرسل الشكوى',
    submitting: 'جارٍ الإرسال…',
    complaintFiled: 'تم تقديم الشكوى',
    complaintFailed: 'تعذّر تقديم الشكوى. حاول مرة أخرى.',
    close: 'إلغاء',
  },
};

export const SHOW_OTHER_OPTIONS: Record<CardLanguage, string> = {
  en: 'Show me other options.',
  ar: 'اعرض لي خيارات أخرى.',
};

const BUTTON = 'btn btn-sm mt-3';
const LINK_BUTTON = 'link-btn ms-1 text-xs';
const CARD = 'card p-4 text-sm';

function Spinner(): ReactNode {
  return <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

function Badge({ text, tone, testId }: { text: string; tone: 'green' | 'neutral'; testId: string }): ReactNode {
  const colors = tone === 'green' ? 'success' : '';
  return (
    <span className={`badge mt-3 ${colors}`} data-testid={testId}>
      {text}
    </span>
  );
}

function FailureLine({ text, actionLabel, disabled, onAction, testId }: {
  text: string;
  actionLabel?: string;
  disabled: boolean;
  onAction?: () => void;
  testId: string;
}): ReactNode {
  return (
    <div className="mt-3" data-testid={testId}>
      <span className="text-xs text-danger">{text}</span>
      {actionLabel && onAction && (
        <button type="button" onClick={onAction} disabled={disabled} className={LINK_BUTTON} data-testid="card-retry-btn">
          {actionLabel}
        </button>
      )}
    </div>
  );
}

function DoctorCard({ item, language, status, disabled, onBook, onShowOther }: {
  item: DoctorCardItem;
  language: CardLanguage;
  status: CardStatus;
  disabled: boolean;
  onBook: () => void;
  onShowOther: () => void;
}): ReactNode {
  const text = CARD_TEXT[language];
  return (
    <div className={`${CARD} w-60`} data-testid="doctor-card">
      <div className="font-semibold" data-testid="doctor-name"><bdi>{item.doctor_name}</bdi></div>
      <div className="text-xs text-muted"><bdi>{item.specialty}</bdi></div>
      <div className="text-xs text-muted"><bdi>{item.clinic}, {item.location}</bdi></div>
      <div className="mt-2 text-xs font-medium text-accent">{formatUtc(item.start_at, language)}</div>
      {status === 'done' && <Badge text={text.booked} tone="green" testId="booked-badge" />}
      {status === 'slot_taken' && (
        <div className="mt-3" data-testid="slot-taken">
          <span className="text-xs text-danger">{text.slotTaken}</span>
          <button type="button" onClick={onShowOther} disabled={disabled} className={LINK_BUTTON} data-testid="show-other-btn">
            {text.showOther}
          </button>
        </div>
      )}
      {status === 'error' && (
        <FailureLine text={text.bookFailed} actionLabel={text.retry} disabled={disabled} onAction={onBook} testId="card-error" />
      )}
      {(status === 'default' || status === 'busy') && (
        <button type="button" onClick={onBook} disabled={disabled} className={BUTTON} data-testid="book-btn">
          {status === 'busy' && <Spinner />}
          {status === 'busy' ? text.booking : text.book}
        </button>
      )}
    </div>
  );
}

function CancelCard({ item, language, status, disabled, onCancel }: {
  item: VisitCardItem;
  language: CardLanguage;
  status: CardStatus;
  disabled: boolean;
  onCancel: () => void;
}): ReactNode {
  const text = CARD_TEXT[language];
  return (
    <div className={`${CARD} w-60`} data-testid="cancel-card">
      <div className="text-xs font-medium text-accent">{formatUtc(item.start_at, language)}</div>
      <div className="font-semibold"><bdi>{item.doctor_name}</bdi></div>
      <div className="text-xs text-muted"><bdi>{item.specialty}</bdi></div>
      <div className="text-xs text-muted"><bdi>{item.clinic}</bdi></div>
      {status === 'done' && <Badge text={text.cancelled} tone="neutral" testId="cancelled-badge" />}
      {status === 'not_cancellable' && (
        <FailureLine text={text.notCancellable} disabled={disabled} testId="not-cancellable" />
      )}
      {status === 'error' && (
        <FailureLine text={text.cancelFailed} actionLabel={text.retry} disabled={disabled} onAction={onCancel} testId="card-error" />
      )}
      {(status === 'default' || status === 'busy') && (
        <button type="button" onClick={onCancel} disabled={disabled} className={`${BUTTON} btn-danger`} data-testid="cancel-confirm-btn">
          {status === 'busy' && <Spinner />}
          {status === 'busy' ? text.cancelling : text.cancelVisit}
        </button>
      )}
    </div>
  );
}

function ComplaintCard({ item, language, status, disabled, onFile }: {
  item: VisitCardItem;
  language: CardLanguage;
  status: CardStatus;
  disabled: boolean;
  onFile: (description: string) => void;
}): ReactNode {
  const [description, setDescription] = useState('');
  const [expanded, setExpanded] = useState(false);
  const canSubmit = !disabled && description.trim() !== '';
  const text = CARD_TEXT[language];

  return (
    <div className={`${CARD} w-72`} data-testid="complaint-card">
      <div className="text-xs font-medium text-accent">{formatUtc(item.start_at, language)}</div>
      <div className="font-semibold"><bdi>{item.doctor_name}</bdi></div>
      <div className="text-xs text-muted"><bdi>{item.clinic}</bdi></div>
      {status === 'done' && <Badge text={text.complaintFiled} tone="green" testId="filed-badge" />}
      {status !== 'done' && !expanded && (
        <button type="button" onClick={() => setExpanded(true)} disabled={disabled} className={`${BUTTON} btn-secondary`} data-testid="select-visit-btn">
          {text.select}
        </button>
      )}
      {status !== 'done' && expanded && (
        <div className="mt-3">
          <label className="mb-1 block text-xs font-semibold" htmlFor={`complaint-${item.visit_id}`}>{text.whatHappened}</label>
          <textarea
            id={`complaint-${item.visit_id}`}
            dir="auto"
            value={description}
            onChange={e => setDescription(e.target.value)}
            disabled={disabled}
            className="input px-2.5 py-2 text-sm"
            rows={3}
            data-testid="complaint-desc"
          />
          {status === 'error' && (
            <FailureLine
              text={text.complaintFailed}
              actionLabel={text.retry}
              disabled={!canSubmit}
              onAction={() => onFile(description)}
              testId="card-error"
            />
          )}
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={() => onFile(description)}
              disabled={!canSubmit}
              className="btn btn-sm"
              data-testid="submit-complaint-btn"
            >
              {status === 'busy' && <Spinner />}
              {status === 'busy' ? text.submitting : text.submitComplaint}
            </button>
            <button type="button" onClick={() => setExpanded(false)} disabled={disabled} className="btn btn-ghost btn-sm">
              {text.close}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function ChatCards({ cards, state, locked, onBook, onCancelVisit, onFileComplaint, onShowOther }: {
  cards: CardsPayload;
  state: CardSetState;
  locked: boolean;
  onBook: (slotId: number) => void;
  onCancelVisit: (visitId: number) => void;
  onFileComplaint: (visitId: number, description: string) => void;
  onShowOther: () => void;
}): ReactNode {
  const disabled = locked || state.busyId !== null || state.doneId !== null;

  return (
    <div dir={cards.language === 'ar' ? 'rtl' : 'ltr'} lang={cards.language} className="rise flex flex-wrap gap-3" data-testid="chat-cards">
      {cards.type === 'doctors' && cards.items.map(item => (
        <DoctorCard
          key={item.slot_id}
          item={item}
          language={cards.language}
          status={statusFor(state, item.slot_id)}
          disabled={disabled}
          onBook={() => onBook(item.slot_id)}
          onShowOther={onShowOther}
        />
      ))}
      {cards.type === 'cancel_confirm' && cards.items.map(item => (
        <CancelCard
          key={item.visit_id}
          item={item}
          language={cards.language}
          status={statusFor(state, item.visit_id)}
          disabled={disabled}
          onCancel={() => onCancelVisit(item.visit_id)}
        />
      ))}
      {cards.type === 'visits_for_complaint' && cards.items.map(item => (
        <ComplaintCard
          key={item.visit_id}
          item={item}
          language={cards.language}
          status={statusFor(state, item.visit_id)}
          disabled={disabled}
          onFile={description => onFileComplaint(item.visit_id, description)}
        />
      ))}
    </div>
  );
}
