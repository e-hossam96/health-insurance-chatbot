import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { type VisitItem, type ComplaintItem, getMyVisits, getMyComplaints, cancelVisit } from '../api/visits';

function statusBadge(status: string): ReactNode {
  const colors: Record<string, string> = {
    scheduled: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    cancelled: 'bg-gray-100 text-gray-600',
    open: 'bg-yellow-100 text-yellow-800',
    closed: 'bg-gray-100 text-gray-600',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] ?? 'bg-gray-100'}`} data-testid="status-badge">
      {status}
    </span>
  );
}

export function VisitsDrawer({ open, onClose }: { open: boolean; onClose: () => void }): ReactNode {
  const [visits, setVisits] = useState<VisitItem[]>([]);
  const [complaints, setComplaints] = useState<ComplaintItem[]>([]);
  const [tab, setTab] = useState<'visits' | 'complaints'>('visits');

  const load = useCallback(() => {
    getMyVisits().then(setVisits).catch(() => {});
    getMyComplaints().then(setComplaints).catch(() => {});
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  async function handleCancel(visitId: number): Promise<void> {
    if (!confirm('Cancel this visit?')) return;
    try {
      await cancelVisit(visitId);
      load();
    } catch {
      alert('Cannot cancel this visit.');
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="bg-black/40 flex-1" onClick={onClose} />
      <div className="w-96 bg-white shadow-lg overflow-y-auto" data-testid="visits-drawer">
        <div className="p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-bold">My visits & complaints</h2>
            <button onClick={onClose} className="text-gray-500">&times;</button>
          </div>

          <div className="flex gap-2 mb-4">
            <button
              className={`px-3 py-1 text-sm rounded ${tab === 'visits' ? 'bg-blue-600 text-white' : 'border'}`}
              onClick={() => setTab('visits')}
              data-testid="drawer-tab-visits"
            >
              Visits
            </button>
            <button
              className={`px-3 py-1 text-sm rounded ${tab === 'complaints' ? 'bg-blue-600 text-white' : 'border'}`}
              onClick={() => setTab('complaints')}
              data-testid="drawer-tab-complaints"
            >
              Complaints
            </button>
          </div>

          {tab === 'visits' && (
            <div data-testid="visits-list">
              {visits.length === 0 && <p className="text-sm text-gray-500">No visits yet.</p>}
              {visits.map((v) => (
                <div key={v.id} className="border rounded p-3 mb-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium text-sm">{v.doctor_name}</p>
                      <p className="text-xs text-gray-500">{v.specialty} · {v.clinic} · {v.location}</p>
                      <p className="text-xs text-gray-400">{new Date(v.start_at).toLocaleString()}</p>
                    </div>
                    {statusBadge(v.status)}
                  </div>
                  {v.status === 'scheduled' && (
                    <button
                      className="mt-2 text-xs text-red-600"
                      onClick={() => void handleCancel(v.id)}
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
              {complaints.length === 0 && <p className="text-sm text-gray-500">No complaints yet.</p>}
              {complaints.map((c) => (
                <div key={c.id} className="border rounded p-3 mb-2">
                  <div className="flex justify-between items-start mb-1">
                    <p className="text-sm font-medium">Visit #{c.visit_id}</p>
                    {statusBadge(c.status)}
                  </div>
                  <p className="text-sm">{c.description}</p>
                  {c.replies.length > 0 && (
                    <div className="mt-2 pl-3 border-l-2 border-gray-200">
                      {c.replies.map((r) => (
                        <p key={r.id} className="text-xs text-gray-600 mb-1">
                          <span className="font-medium">Support team:</span> {r.body}
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
    </div>
  );
}
