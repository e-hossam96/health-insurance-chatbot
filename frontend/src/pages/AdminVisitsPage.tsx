import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { errorMessage } from '../api/client';
import { Header } from '../components/Header';
import { type AdminVisit, getAdminVisits, completeVisit } from '../api/admin';

export function AdminVisitsPage(): ReactNode {
  const [visits, setVisits] = useState<AdminVisit[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const limit = 20;

  const load = useCallback(() => {
    const params: { limit: number; offset: number; status?: string } = { limit, offset };
    if (statusFilter) params.status = statusFilter;
    getAdminVisits(params).then((data) => {
      setVisits(data.items);
      setTotal(data.total);
    }).catch(() => {});
  }, [offset, statusFilter]);

  useEffect(load, [load]);

  async function handleComplete(visitId: number): Promise<void> {
    if (!confirm('Mark this visit as completed?')) return;
    try {
      await completeVisit(visitId);
      load();
    } catch (err: unknown) {
      alert(errorMessage(err, 'Failed'));
    }
  }

  return (
    <div>
      <Header />
      <div className="page">
        <h2 className="page-title">Visits</h2>
        <div className="mb-4 flex items-center gap-4">
          <select
            className="input w-auto py-2 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            data-testid="status-filter"
          >
            <option value="">All statuses</option>
            <option value="scheduled">Scheduled</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <span className="text-sm text-muted">Total: {total}</span>
        </div>
        <div className="table-wrap">
        <table className="table" data-testid="admin-visits-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th className="text-right!">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visits.map((v) => (
              <tr key={v.id}>
                <td>{v.id}</td>
                <td>
                  <span className={`badge capitalize ${
                    v.status === 'scheduled' ? 'accent' :
                    v.status === 'completed' ? 'success' :
                    ''
                  }`} data-testid="visit-status-badge">
                    {v.status}
                  </span>
                </td>
                <td className="text-right!">
                  {v.status === 'scheduled' && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleComplete(v.id)}
                      data-testid="complete-btn"
                    >
                      Complete
                    </button>
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
      </div>
    </div>
  );
}
