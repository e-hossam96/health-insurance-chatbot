import { type ReactNode, useCallback, useEffect, useState } from 'react';
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
      const apiErr = err as { error?: { message?: string } };
      alert(apiErr.error?.message ?? 'Failed');
    }
  }

  return (
    <div>
      <Header />
      <div className="max-w-4xl mx-auto p-4">
        <h2 className="text-xl font-bold mb-4">Visits</h2>
        <div className="flex gap-4 items-center mb-4">
          <select
            className="border rounded p-2 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            data-testid="status-filter"
          >
            <option value="">All statuses</option>
            <option value="scheduled">Scheduled</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <span className="text-sm text-gray-500">Total: {total}</span>
        </div>
        <table className="w-full text-sm" data-testid="admin-visits-table">
          <thead>
            <tr className="border-b">
              <th className="text-left py-1">ID</th>
              <th className="text-left py-1">Status</th>
              <th className="text-right py-1">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visits.map((v) => (
              <tr key={v.id} className="border-b">
                <td className="py-1">{v.id}</td>
                <td className="py-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    v.status === 'scheduled' ? 'bg-brand-100 text-brand-800' :
                    v.status === 'completed' ? 'bg-green-100 text-green-800' :
                    'bg-gray-100 text-gray-600'
                  }`} data-testid="visit-status-badge">
                    {v.status}
                  </span>
                </td>
                <td className="py-1 text-right">
                  {v.status === 'scheduled' && (
                    <button
                      className="text-green-600 text-sm"
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
        <div className="flex gap-2 mt-4">
          <button className="border rounded px-3 py-1 text-sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - limit))}>Prev</button>
          <button className="border rounded px-3 py-1 text-sm" disabled={offset + limit >= total} onClick={() => setOffset((o) => o + limit)}>Next</button>
        </div>
      </div>
    </div>
  );
}
