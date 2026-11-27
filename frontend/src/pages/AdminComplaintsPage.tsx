import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';
import { useConfirm } from '../components/ConfirmDialog';
import { errorMessage } from '../api/client';
import { Header } from '../components/Header';
import {
  type AdminComplaint,
  type AdminComplaintDetail,
  closeComplaint,
  getAdminComplaint,
  getAdminComplaints,
  replyToComplaint,
} from '../api/admin';
import { formatUtc } from '../api/chat';
import { formatUtcDay } from '../api/kb';

const PAGE_SIZE = 50;

function replyCountLabel(count: number): string {
  if (count === 0) return 'no reply';
  return count === 1 ? '1 reply' : `${count} replies`;
}

function StatusBadge({ status }: { status: string }): ReactNode {
  return (
    <span className={`badge capitalize ${status === 'open' ? 'new' : ''}`} data-testid="complaint-status-badge">
      {status}
    </span>
  );
}

export function AdminComplaintsPage(): ReactNode {
  const [complaints, setComplaints] = useState<AdminComplaint[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminComplaintDetail | null>(null);
  const [replyBody, setReplyBody] = useState('');
  const [closeAfterSend, setCloseAfterSend] = useState(false);
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState('');
  const { confirm, confirmDialog } = useConfirm();

  const loadList = useCallback(() => {
    const params: { limit: number; offset: number; status?: string } = { limit: PAGE_SIZE, offset };
    if (statusFilter) params.status = statusFilter;
    getAdminComplaints(params).then((data) => {
      setComplaints(data.items);
      setTotal(data.total);
    }).catch(() => {});
  }, [offset, statusFilter]);

  const loadDetail = useCallback((id: number) => {
    getAdminComplaint(id).then(setDetail).catch(() => setDetail(null));
  }, []);

  useEffect(loadList, [loadList]);

  useEffect(() => {
    if (selectedId !== null) loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  function select(id: number): void {
    setReplyError('');
    setReplyBody('');
    setCloseAfterSend(false);
    setSelectedId(id);
  }

  function refresh(id: number): void {
    loadList();
    loadDetail(id);
  }

  async function handleReply(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (detail === null) return;
    setReplyError('');
    setSending(true);
    try {
      await replyToComplaint(detail.id, replyBody, closeAfterSend);
      setReplyBody('');
      setCloseAfterSend(false);
      refresh(detail.id);
    } catch (err: unknown) {
      setReplyError(errorMessage(err, 'Could not send the reply.'));
    } finally {
      setSending(false);
    }
  }

  function askClose(id: number): void {
    confirm({
      title: `Close complaint #${id}?`,
      message: 'Closed complaints can no longer receive replies.',
      confirmLabel: 'Close complaint',
      failureText: 'Could not close the complaint.',
      run: async () => {
        await closeComplaint(id);
        refresh(id);
      },
    });
  }

  const isClosed = detail?.status === 'closed';

  return (
    <div>
      <Header />
      <div className="page">
        <h1 className="page-title">Complaints</h1>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <section aria-label="Complaint list">
            <div className="mb-4 flex items-center gap-4">
              <select
                className="input w-auto py-2 text-sm"
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
                data-testid="complaint-status-filter"
                aria-label="Status"
              >
                <option value="">All statuses</option>
                <option value="open">Open</option>
                <option value="closed">Closed</option>
              </select>
              <span className="text-sm text-muted">Total: {total}</span>
            </div>
            <ul className="card divide-y divide-line p-0" data-testid="admin-complaints-table">
              {complaints.length === 0 && <li className="p-4 text-sm text-muted">No complaints yet.</li>}
              {complaints.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={`w-full p-4 text-left hover:bg-surface ${selectedId === c.id ? 'bg-surface shadow-[inset_3px_0_0_var(--accent)]' : ''}`}
                    aria-current={selectedId === c.id ? 'true' : undefined}
                    onClick={() => select(c.id)}
                    data-testid="complaint-item"
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-medium">#{c.id} {c.patient_name}</span>
                      <StatusBadge status={c.status} />
                    </span>
                    <span className="mt-1 block text-sm text-muted">
                      {formatUtcDay(c.created_at)} - {replyCountLabel(c.reply_count)}
                    </span>
                    <span className="mt-1 block truncate text-sm">{c.description}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex gap-2">
              <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}>Prev</button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((o) => o + PAGE_SIZE)}>Next</button>
            </div>
          </section>

          <section aria-label="Complaint detail" className="card" data-testid="complaint-detail">
            {detail === null ? (
              <p className="text-sm text-muted">Select a complaint to read it and reply.</p>
            ) : (
              <>
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="text-lg font-semibold">Complaint #{detail.id}</h3>
                  <StatusBadge status={detail.status} />
                </div>
                <p className="text-sm"><span className="text-muted">Patient:</span> {detail.patient_name}</p>
                <p className="text-sm" data-testid="complaint-visit">
                  <span className="text-muted">Visit:</span> {formatUtc(detail.visit.start_at)}, {detail.visit.doctor_name}, {detail.visit.specialty}, {detail.visit.clinic} ({detail.visit.location})
                </p>
                <blockquote className="my-4 whitespace-pre-wrap border-l-2 border-line pl-3" data-testid="complaint-description">
                  {detail.description}
                  <span className="ml-2 text-sm text-muted">({formatUtcDay(detail.created_at)})</span>
                </blockquote>
                <h4 className="mb-2 font-semibold">Replies</h4>
                {detail.replies.length === 0 ? (
                  <p className="mb-4 text-sm text-muted">No reply yet</p>
                ) : (
                  <ul className="mb-4 space-y-2" data-testid="complaint-replies">
                    {detail.replies.map((r) => (
                      <li key={r.id} className="text-sm">
                        <span className="font-medium">{r.admin_username}</span>{' '}
                        <span className="text-muted">({formatUtc(r.created_at)}):</span>{' '}
                        <span className="whitespace-pre-wrap">{r.body}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <form onSubmit={(e) => void handleReply(e)}>
                  <textarea
                    className="input mb-2"
                    rows={3}
                    placeholder={isClosed ? "Closed complaints can't receive replies." : 'Write a reply...'}
                    aria-label="Reply"
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    disabled={isClosed || sending}
                    data-testid="reply-body"
                    required
                  />
                  {isClosed && <p className="mb-2 text-sm text-muted" data-testid="reply-closed-note">Closed complaints can't receive replies.</p>}
                  <label className="mb-3 flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={closeAfterSend}
                      onChange={(e) => setCloseAfterSend(e.target.checked)}
                      disabled={isClosed || sending}
                      data-testid="close-after-send"
                    />
                    Close complaint after sending
                  </label>
                  {replyError && <p className="alert error mb-3" role="alert" data-testid="reply-error">{replyError}</p>}
                  <div className="flex justify-between gap-2">
                    <button type="submit" className="btn btn-sm" disabled={isClosed || sending} data-testid="send-reply">Send reply</button>
                    {!isClosed && (
                      <button type="button" className="btn btn-danger-ghost btn-sm" onClick={() => askClose(detail.id)} data-testid="close-btn">
                        Close complaint
                      </button>
                    )}
                  </div>
                </form>
              </>
            )}
          </section>
        </div>
        {confirmDialog}
      </div>
    </div>
  );
}
