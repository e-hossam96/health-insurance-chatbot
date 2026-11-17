import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { formatUtc } from '../api/chat';
import { CloseIcon } from './icons';
import { useConfirm } from './ConfirmDialog';
import { type VisitItem, type ComplaintItem, getMyVisits, getMyComplaints, cancelVisit } from '../api/visits';

function statusBadge(status: string): ReactNode {
  const colors: Record<string, string> = {
    scheduled: 'accent',
    completed: 'success',
    cancelled: '',
    open: 'warn',
    closed: '',
  };
  return (
    <span className={`badge capitalize ${colors[status] ?? ''}`} data-testid="status-badge">
      {status}
    </span>
  );
}

export function VisitsDrawer({ open, onClose }: { open: boolean; onClose: () => void }): ReactNode {
  const [visits, setVisits] = useState<VisitItem[]>([]);
  const [complaints, setComplaints] = useState<ComplaintItem[]>([]);
  const [tab, setTab] = useState<'visits' | 'complaints'>('visits');
  const { confirm, confirmDialog } = useConfirm();

  const load = useCallback(() => {
    getMyVisits().then(setVisits).catch(() => {});
    getMyComplaints().then(setComplaints).catch(() => {});
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  function askCancel(visit: VisitItem): void {
    confirm({
      title: 'Cancel this visit?',
      message: `${visit.doctor_name}, ${formatUtc(visit.start_at)}. The slot is released for other members.`,
      confirmLabel: 'Cancel visit',
      failureText: 'Cannot cancel this visit.',
      run: async () => {
        await cancelVisit(visit.id);
        load();
      },
    });
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-overlay backdrop-blur-[2px]" onClick={onClose} />
      <div className="w-96 max-w-full overflow-y-auto border-l border-line bg-card shadow-raised" data-testid="visits-drawer">
        <div className="p-5">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">My visits & complaints</h2>
            <button type="button" onClick={onClose} className="btn btn-ghost btn-sm px-2" aria-label="Close"><CloseIcon /></button>
          </div>

          <div className="segmented mb-4">
            <button
              type="button"
              aria-pressed={tab === 'visits'}
              onClick={() => setTab('visits')}
              data-testid="drawer-tab-visits"
            >
              Visits
            </button>
            <button
              type="button"
              aria-pressed={tab === 'complaints'}
              onClick={() => setTab('complaints')}
              data-testid="drawer-tab-complaints"
            >
              Complaints
            </button>
          </div>

          {tab === 'visits' && (
            <div data-testid="visits-list">
              {visits.length === 0 && <p className="text-sm text-muted">No visits yet.</p>}
              {visits.map((v) => (
                <div key={v.id} className="mb-3 rounded-card border border-line bg-surface p-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-sm font-semibold">{v.doctor_name}</p>
                      <p className="text-xs text-muted">{v.specialty} · {v.clinic} · {v.location}</p>
                      <p className="mt-1 text-xs font-medium text-accent">{formatUtc(v.start_at)}</p>
                    </div>
                    {statusBadge(v.status)}
                  </div>
                  {v.status === 'scheduled' && (
                    <button
                      type="button"
                      className="btn btn-danger-ghost btn-sm -ml-3 mt-2"
                      onClick={() => askCancel(v)}
                      data-testid="cancel-visit-btn"
                    >
                      Cancel visit
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {tab === 'complaints' && (
            <div data-testid="complaints-list">
              {complaints.length === 0 && <p className="text-sm text-muted">No complaints yet.</p>}
              {complaints.map((c) => (
                <div key={c.id} className="mb-3 rounded-card border border-line bg-surface p-4">
                  <div className="flex justify-between items-start mb-1">
                    <p className="text-sm font-semibold">Visit #{c.visit_id}</p>
                    {statusBadge(c.status)}
                  </div>
                  <p className="text-sm">{c.description}</p>
                  {c.replies.length > 0 && (
                    <div className="mt-3 border-l-2 border-accent-soft pl-3">
                      {c.replies.map((r) => (
                        <p key={r.id} className="mb-1 text-xs text-muted">
                          <span className="font-semibold text-fg">Support team:</span> {r.body}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {confirmDialog}
    </div>
  );
}
