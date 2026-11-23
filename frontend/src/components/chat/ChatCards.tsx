import { type ReactNode, useState } from 'react';
import { type CardsPayload, type DoctorCardItem, type VisitCardItem, formatUtc } from '../../api/chat';
import type { CardFailureKind, CardSetState } from './cardState';

type CardStatus = 'default' | 'busy' | 'done' | CardFailureKind;

function statusFor(state: CardSetState, id: number): CardStatus {
  if (state.doneId === id) return 'done';
  if (state.busyId === id) return 'busy';
  if (state.failure?.id === id) return state.failure.kind;
  return 'default';
}

const BUTTON = 'btn btn-sm mt-3';
const LINK_BUTTON = 'link-btn ml-1 text-xs';
const CARD = 'card rise p-4 text-sm';

function Spinner(): ReactNode {
  return <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

function Badge({ text, tone, testId }: { text: string; tone: 'green' | 'red'; testId: string }): ReactNode {
  const colors = tone === 'green' ? 'success' : 'danger';
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

function DoctorCard({ item, status, disabled, onBook, onShowOther }: {
  item: DoctorCardItem;
  status: CardStatus;
  disabled: boolean;
  onBook: () => void;
  onShowOther: () => void;
}): ReactNode {
  return (
    <div className={`${CARD} w-60`} data-testid="doctor-card">
      <div className="font-semibold" data-testid="doctor-name">{item.doctor_name}</div>
      <div className="text-xs text-muted">{item.specialty}</div>
      <div className="text-xs text-muted">{item.clinic}, {item.location}</div>
      <div className="mt-2 text-xs font-medium text-accent">{formatUtc(item.start_at)}</div>
      {status === 'done' && <Badge text="Booked" tone="green" testId="booked-badge" />}
      {status === 'slot_taken' && (
        <div className="mt-3" data-testid="slot-taken">
          <span className="text-xs text-danger">This slot was just taken</span>
          <button type="button" onClick={onShowOther} disabled={disabled} className={LINK_BUTTON} data-testid="show-other-btn">
            Show other options
          </button>
        </div>
      )}
      {status === 'error' && (
        <FailureLine text="Could not book. Try again." actionLabel="Retry" disabled={disabled} onAction={onBook} testId="card-error" />
      )}
      {(status === 'default' || status === 'busy') && (
        <button type="button" onClick={onBook} disabled={disabled} className={BUTTON} data-testid="book-btn">
          {status === 'busy' && <Spinner />}
          {status === 'busy' ? 'Booking…' : 'Book'}
        </button>
      )}
    </div>
  );
}

function CancelCard({ item, status, disabled, onCancel }: {
  item: VisitCardItem;
  status: CardStatus;
  disabled: boolean;
  onCancel: () => void;
}): ReactNode {
  return (
    <div className={`${CARD} w-60`} data-testid="cancel-card">
      <div className="text-xs font-medium text-accent">{formatUtc(item.start_at)}</div>
      <div className="font-semibold">{item.doctor_name}</div>
      <div className="text-xs text-muted">{item.specialty}</div>
      <div className="text-xs text-muted">{item.clinic}</div>
      {status === 'done' && <Badge text="Cancelled" tone="red" testId="cancelled-badge" />}
      {status === 'not_cancellable' && (
        <FailureLine text="This visit can no longer be cancelled" disabled={disabled} testId="not-cancellable" />
      )}
      {status === 'error' && (
        <FailureLine text="Could not cancel. Try again." actionLabel="Retry" disabled={disabled} onAction={onCancel} testId="card-error" />
      )}
      {(status === 'default' || status === 'busy') && (
        <button type="button" onClick={onCancel} disabled={disabled} className={`${BUTTON} btn-danger`} data-testid="cancel-confirm-btn">
          {status === 'busy' && <Spinner />}
          {status === 'busy' ? 'Cancelling…' : 'Yes, cancel visit'}
        </button>
      )}
    </div>
  );
}

function ComplaintCard({ item, status, disabled, onFile }: {
  item: VisitCardItem;
  status: CardStatus;
  disabled: boolean;
  onFile: (description: string) => void;
}): ReactNode {
  const [description, setDescription] = useState('');
  const [expanded, setExpanded] = useState(false);
  const canSubmit = !disabled && description.trim() !== '';

  return (
    <div className={`${CARD} w-72`} data-testid="complaint-card">
      <div className="text-xs font-medium text-accent">{formatUtc(item.start_at)}</div>
      <div className="font-semibold">{item.doctor_name}</div>
      <div className="text-xs text-muted">{item.clinic}</div>
      {status === 'done' && <Badge text="Complaint filed" tone="green" testId="filed-badge" />}
      {status !== 'done' && !expanded && (
        <button type="button" onClick={() => setExpanded(true)} disabled={disabled} className={`${BUTTON} btn-secondary`} data-testid="select-visit-btn">
          Select
        </button>
      )}
      {status !== 'done' && expanded && (
        <div className="mt-3">
          <label className="mb-1 block text-xs font-semibold" htmlFor={`complaint-${item.visit_id}`}>What happened?</label>
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
              text="Could not file the complaint. Try again."
              actionLabel="Retry"
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
              {status === 'busy' ? 'Submitting…' : 'Submit complaint'}
            </button>
            <button type="button" onClick={() => setExpanded(false)} disabled={disabled} className="btn btn-ghost btn-sm">
              Cancel
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
    <div className="flex flex-wrap gap-3" data-testid="chat-cards">
      {cards.type === 'doctors' && cards.items.map(item => (
        <DoctorCard
          key={item.slot_id}
          item={item}
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
          status={statusFor(state, item.visit_id)}
          disabled={disabled}
          onCancel={() => onCancelVisit(item.visit_id)}
        />
      ))}
      {cards.type === 'visits_for_complaint' && cards.items.map(item => (
        <ComplaintCard
          key={item.visit_id}
          item={item}
          status={statusFor(state, item.visit_id)}
          disabled={disabled}
          onFile={description => onFileComplaint(item.visit_id, description)}
        />
      ))}
    </div>
  );
}
