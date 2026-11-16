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

const BUTTON = 'mt-2 text-xs px-3 py-1 rounded disabled:opacity-50';
const LINK_BUTTON = 'ml-1 text-xs text-brand-700 underline disabled:opacity-50';

function Spinner(): ReactNode {
  return <span className="inline-block h-3 w-3 mr-1 align-middle animate-spin rounded-full border-2 border-brand-900 border-t-transparent" />;
}

function Badge({ text, tone, testId }: { text: string; tone: 'green' | 'red'; testId: string }): ReactNode {
  const colors = tone === 'green' ? 'text-green-700 bg-green-100' : 'text-red-700 bg-red-100';
  return (
    <span className={`inline-block mt-2 text-xs px-2 py-1 rounded ${colors}`} data-testid={testId}>
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
    <div className="mt-2" data-testid={testId}>
      <span className="text-xs text-red-600">{text}</span>
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
    <div className="border border-gray-200 rounded-lg p-3 w-56 bg-white" data-testid="doctor-card">
      <div className="font-medium text-sm">{item.doctor_name}</div>
      <div className="text-xs text-gray-500">{item.specialty}</div>
      <div className="text-xs text-gray-500">{item.clinic}, {item.location}</div>
      <div className="text-xs text-gray-600 mt-1">{formatUtc(item.start_at)}</div>
      {status === 'done' && <Badge text="Booked" tone="green" testId="booked-badge" />}
      {status === 'slot_taken' && (
        <div className="mt-2" data-testid="slot-taken">
          <span className="text-xs text-red-600">This slot was just taken</span>
          <button type="button" onClick={onShowOther} disabled={disabled} className={LINK_BUTTON} data-testid="show-other-btn">
            Show other options
          </button>
        </div>
      )}
      {status === 'error' && (
        <FailureLine text="Could not book. Try again." actionLabel="Retry" disabled={disabled} onAction={onBook} testId="card-error" />
      )}
      {(status === 'default' || status === 'busy') && (
        <button type="button" onClick={onBook} disabled={disabled} className={`${BUTTON} bg-brand-400 text-brand-900 hover:bg-brand-500`} data-testid="book-btn">
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
    <div className="border border-gray-200 rounded-lg p-3 w-56 bg-white" data-testid="cancel-card">
      <div className="text-xs text-gray-600">{formatUtc(item.start_at)}</div>
      <div className="font-medium text-sm">{item.doctor_name}</div>
      <div className="text-xs text-gray-500">{item.specialty}</div>
      <div className="text-xs text-gray-500">{item.clinic}</div>
      {status === 'done' && <Badge text="Cancelled" tone="red" testId="cancelled-badge" />}
      {status === 'not_cancellable' && (
        <FailureLine text="This visit can no longer be cancelled" disabled={disabled} testId="not-cancellable" />
      )}
      {status === 'error' && (
        <FailureLine text="Could not cancel. Try again." actionLabel="Retry" disabled={disabled} onAction={onCancel} testId="card-error" />
      )}
      {(status === 'default' || status === 'busy') && (
        <button type="button" onClick={onCancel} disabled={disabled} className={`${BUTTON} bg-red-600 text-white hover:bg-red-700`} data-testid="cancel-confirm-btn">
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
    <div className="border border-gray-200 rounded-lg p-3 w-64 bg-white" data-testid="complaint-card">
      <div className="text-xs text-gray-600">{formatUtc(item.start_at)}</div>
      <div className="font-medium text-sm">{item.doctor_name}</div>
      <div className="text-xs text-gray-500">{item.clinic}</div>
      {status === 'done' && <Badge text="Complaint filed" tone="green" testId="filed-badge" />}
      {status !== 'done' && !expanded && (
        <button type="button" onClick={() => setExpanded(true)} disabled={disabled} className={`${BUTTON} bg-brand-400 text-brand-900 hover:bg-brand-500`} data-testid="select-visit-btn">
          Select
        </button>
      )}
      {status !== 'done' && expanded && (
        <div className="mt-2">
          <label className="text-xs text-gray-700" htmlFor={`complaint-${item.visit_id}`}>What happened?</label>
          <textarea
            id={`complaint-${item.visit_id}`}
            value={description}
            onChange={e => setDescription(e.target.value)}
            disabled={disabled}
            className="w-full border border-gray-300 rounded p-1 text-sm"
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
          <div className="flex gap-2 mt-1">
            <button
              type="button"
              onClick={() => onFile(description)}
              disabled={!canSubmit}
              className="text-xs bg-brand-400 text-brand-900 px-3 py-1 rounded disabled:opacity-50"
              data-testid="submit-complaint-btn"
            >
              {status === 'busy' && <Spinner />}
              {status === 'busy' ? 'Submitting…' : 'Submit complaint'}
            </button>
            <button type="button" onClick={() => setExpanded(false)} disabled={disabled} className="text-xs text-gray-500 disabled:opacity-50">
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
