import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react';
import { Dialog } from '../components/Dialog';
import { errorMessage } from '../api/client';
import { Header } from '../components/Header';
import { type AdminComplaint, getAdminComplaints, replyToComplaint, closeComplaint } from '../api/admin';

export function AdminComplaintsPage(): ReactNode {
  const [complaints, setComplaints] = useState<AdminComplaint[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [replyTarget, setReplyTarget] = useState<number | null>(null);
  const [replyBody, setReplyBody] = useState('');
  const limit = 20;

  const load = useCallback(() => {
    const params: { limit: number; offset: number; status?: string } = { limit, offset };
    if (statusFilter) params.status = statusFilter;
    getAdminComplaints(params).then((data) => {
      setComplaints(data.items);
      setTotal(data.total);
    }).catch(() => {});
  }, [offset, statusFilter]);

  useEffect(load, [load]);

  async function handleReply(e: FormEvent): Promise<void> {
    e.preventDefault();
    if (replyTarget === null) return;
    try {
      await replyToComplaint(replyTarget, replyBody);
      setReplyTarget(null);
      setReplyBody('');
      load();
    } catch (err: unknown) {
      alert(errorMessage(err, 'Failed'));
    }
  }

  async function handleClose(id: number): Promise<void> {
    if (!confirm('Close this complaint?')) return;
    try {
      await closeComplaint(id);
      load();
    } catch (err: unknown) {
      alert(errorMessage(err, 'Failed'));
    }
  }

  return (
    <div>
      <Header />
      <div className="page">
        <h2 className="page-title">Complaints</h2>
        <div className="mb-4 flex items-center gap-4">
          <select
            className="input w-auto py-2 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            data-testid="complaint-status-filter"
          >
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
          <span className="text-sm text-muted">Total: {total}</span>
        </div>
        <div className="table-wrap">
        <table className="table" data-testid="admin-complaints-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Visit</th>
              <th>Description</th>
              <th>Status</th>
              <th className="text-right!">Actions</th>
            </tr>
          </thead>
          <tbody>
            {complaints.map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.visit_id}</td>
                <td className="max-w-xs truncate">{c.description}</td>
                <td>
                  <span className={`badge capitalize ${c.status === 'open' ? 'warn' : ''}`} data-testid="complaint-status-badge">
                    {c.status}
                  </span>
                </td>
                <td className="space-x-3 whitespace-nowrap text-right!">
                  {c.status === 'open' && (
                    <>
                      <button type="button" className="link-btn" onClick={() => setReplyTarget(c.id)} data-testid="reply-btn">Reply</button>
                      <button type="button" className="link-btn danger" onClick={() => void handleClose(c.id)} data-testid="close-btn">Close</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        <div className="mt-4 flex gap-2">
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - limit))}>Prev</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset + limit >= total} onClick={() => setOffset((o) => o + limit)}>Next</button>
        </div>

        <Dialog open={replyTarget !== null} title={`Reply to Complaint #${replyTarget ?? ''}`} onClose={() => setReplyTarget(null)}>
          <form onSubmit={(e) => void handleReply(e)}>
            <textarea className="input mb-4" rows={3} value={replyBody} onChange={(e) => setReplyBody(e.target.value)} data-testid="reply-body" required />
            <div className="flex justify-end gap-2">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReplyTarget(null)}>Cancel</button>
              <button type="submit" className="btn btn-sm">Send</button>
            </div>
          </form>
        </Dialog>
      </div>
    </div>
  );
}
