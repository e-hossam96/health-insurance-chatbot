import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { useConfirm } from '../components/ConfirmDialog';
import { Header } from '../components/Header';
import { type AdminVisit, type AdminVisitQuery, getAdminVisits, completeVisit } from '../api/admin';
import { formatUtc } from '../api/chat';

const PAGE_SIZE = 50;

function parseVisitId(raw: string | null): number | undefined {
  const value = Number(raw);
  return raw !== null && Number.isInteger(value) && value > 0 ? value : undefined;
}

export function AdminVisitsPage(): ReactNode {
  const [searchParams, setSearchParams] = useSearchParams();
  const visitId = parseVisitId(searchParams.get('visit'));
  const [visits, setVisits] = useState<AdminVisit[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [patientInput, setPatientInput] = useState('');
  const [patient, setPatient] = useState('');
  const { confirm, confirmDialog } = useConfirm();

  useEffect(() => {
    const timer = setTimeout(() => { setPatient(patientInput.trim()); setOffset(0); }, 300);
    return () => clearTimeout(timer);
  }, [patientInput]);

  const load = useCallback(() => {
    const params: AdminVisitQuery = { limit: PAGE_SIZE, offset };
    if (statusFilter) params.status = statusFilter;
    if (patient) params.patient = patient;
    if (visitId !== undefined) params.visitId = visitId;
    getAdminVisits(params).then((data) => {
      setVisits(data.items);
      setTotal(data.total);
    }).catch(() => {});
  }, [offset, statusFilter, patient, visitId]);

  useEffect(load, [load]);

  function askComplete(visit: AdminVisit): void {
    confirm({
      title: `Mark ${visit.patient_name}'s visit as completed?`,
      message: `${visit.doctor_name}, ${formatUtc(visit.start_at)}. Completed visits are final and can then receive complaints.`,
      confirmLabel: 'Mark completed',
      tone: 'primary',
      failureText: 'Could not complete the visit.',
      run: async () => {
        await completeVisit(visit.id);
        load();
      },
    });
  }

  return (
    <div>
      <Header />
      <div className="page">
        <h1 className="page-title">Visits</h1>
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <select
            className="input w-auto py-2 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            data-testid="status-filter"
            aria-label="Status"
          >
            <option value="">All statuses</option>
            <option value="scheduled">Scheduled</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <input
            className="input w-56 py-2 text-sm"
            placeholder="Search patient"
            aria-label="Search patient"
            value={patientInput}
            onChange={(e) => setPatientInput(e.target.value)}
            data-testid="patient-search"
          />
          {visitId !== undefined && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSearchParams({})} data-testid="clear-visit-filter">
              Showing visit #{visitId} - show all
            </button>
          )}
          <span className="text-sm text-muted">Total: {total}</span>
        </div>
        <div className="table-wrap">
        <table className="table" data-testid="admin-visits-table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Location</th>
              <th>Clinic</th>
              <th>Specialty</th>
              <th>Doctor</th>
              <th>When</th>
              <th>Status</th>
              <th className="text-right!">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visits.length === 0 && (
              <tr><td colSpan={8} className="text-muted" data-testid="visits-empty">No visits match these filters.</td></tr>
            )}
            {visits.map((v) => (
              <tr key={v.id} data-testid="visit-row">
                <td>{v.patient_name}</td>
                <td>{v.location}</td>
                <td>{v.clinic}</td>
                <td>{v.specialty}</td>
                <td>{v.doctor_name}</td>
                <td className="whitespace-nowrap">{formatUtc(v.start_at)}</td>
                <td>
                  <span className={`badge capitalize ${
                    v.status === 'scheduled' ? 'accent' :
                    v.status === 'completed' ? 'success' :
                    ''
                  }`} data-testid="visit-status-badge">
                    {v.status}
                  </span>
                </td>
                <td>
                  <div className="row-actions">
                    {v.status === 'scheduled' && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => askComplete(v)}
                        data-testid="complete-btn"
                      >
                        Mark completed
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        <div className="mt-4 flex gap-2">
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}>Prev</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((o) => o + PAGE_SIZE)}>Next</button>
        </div>
        {confirmDialog}
      </div>
    </div>
  );
}
