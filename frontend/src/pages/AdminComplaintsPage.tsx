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
      <div className="max-w-4xl mx-auto p-4">
        <h2 className="text-xl font-bold mb-4">Complaints</h2>
        <div className="flex gap-4 items-center mb-4">
          <select
            className="border rounded p-2 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            data-testid="complaint-status-filter"
          >
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
          <span className="text-sm text-gray-500">Total: {total}</span>
        </div>
        <table className="w-full text-sm" data-testid="admin-complaints-table">
          <thead>
            <tr className="border-b">
              <th className="text-left py-1">ID</th>
              <th className="text-left py-1">Visit</th>
              <th className="text-left py-1">Description</th>
              <th className="text-left py-1">Status</th>
              <th className="text-right py-1">Actions</th>
            </tr>
          </thead>
          <tbody>
            {complaints.map((c) => (
              <tr key={c.id} className="border-b">
                <td className="py-1">{c.id}</td>
                <td className="py-1">{c.visit_id}</td>
                <td className="py-1 max-w-xs truncate">{c.description}</td>
                <td className="py-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    c.status === 'open' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-600'
                  }`} data-testid="complaint-status-badge">
                    {c.status}
                  </span>
                </td>
                <td className="py-1 text-right space-x-2">
                  {c.status === 'open' && (
                    <>
                      <button className="text-brand-700 text-sm" onClick={() => setReplyTarget(c.id)} data-testid="reply-btn">Reply</button>
                      <button className="text-red-600 text-sm" onClick={() => void handleClose(c.id)} data-testid="close-btn">Close</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex gap-2 mt-4">
          <button className="border rounded px-3 py-1 text-sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - limit))}>Prev</button>
          <button className="border rounded px-3 py-1 text-sm" disabled={offset + limit >= total} onClick={() => setOffset((o) => o + limit)}>Next</button>
        </div>

        <Dialog open={replyTarget !== null} title={`Reply to Complaint #${replyTarget ?? ''}`} onClose={() => setReplyTarget(null)}>
          <form onSubmit={(e) => void handleReply(e)}>
            <textarea className="border rounded w-full p-2 mb-2" rows={3} value={replyBody} onChange={(e) => setReplyBody(e.target.value)} data-testid="reply-body" required />
            <div className="flex gap-2 justify-end">
              <button type="button" className="px-3 py-1 border rounded text-sm" onClick={() => setReplyTarget(null)}>Cancel</button>
              <button type="submit" className="bg-brand-400 text-brand-900 px-3 py-1 rounded text-sm">Send</button>
            </div>
          </form>
        </Dialog>
      </div>
    </div>
  );
}
