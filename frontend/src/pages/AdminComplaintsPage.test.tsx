import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { AdminComplaintsPage } from './AdminComplaintsPage';
import { closeComplaint, getAdminComplaint, getAdminComplaints, replyToComplaint } from '../api/admin';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/auth', () => ({
  logout: vi.fn(),
  setMode: vi.fn(),
}));

const XSS = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>';

function detailFor(id: number, status: string, description: string): object {
  return {
    id,
    description,
    status,
    created_at: '2026-11-13T08:00:00Z',
    patient_name: 'Omar K.',
    visit: { id: 2, start_at: '2026-11-12T10:00:00Z', doctor_name: 'Dr. Omar Hassan', specialty: 'Cardiology', clinic: 'Nile Medical', location: 'Giza' },
    replies: status === 'open'
      ? [{ id: 9, body: 'We have contacted the clinic.', created_at: '2026-11-14T09:00:00Z', admin_username: 'admin1' }]
      : [],
  };
}

vi.mock('../api/admin', () => ({
  getAdminComplaints: vi.fn(),
  getAdminComplaint: vi.fn(),
  replyToComplaint: vi.fn(),
  closeComplaint: vi.fn(),
}));

function renderPage(): void {
  render(
    <MemoryRouter>
      <AdminComplaintsPage />
    </MemoryRouter>,
  );
}

async function openComplaint(index: number): Promise<void> {
  fireEvent.click((await screen.findAllByTestId('complaint-item'))[index] as HTMLElement);
  await screen.findByText(/Complaint #/);
}

describe('AdminComplaintsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getAdminComplaints as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        { id: 1, visit_id: 2, description: 'Bad service', status: 'open', created_at: '2026-11-13T08:00:00Z', patient_name: 'Omar K.', reply_count: 1 },
        { id: 2, visit_id: 3, description: 'Rude doctor', status: 'closed', created_at: '2026-11-02T08:00:00Z', patient_name: 'Lina F.', reply_count: 2 },
        { id: 3, visit_id: 4, description: XSS, status: 'closed', created_at: '2026-11-01T08:00:00Z', patient_name: 'Sara N.', reply_count: 0 },
      ],
      total: 3,
    });
    (getAdminComplaint as ReturnType<typeof vi.fn>).mockImplementation((id: number) =>
      Promise.resolve(id === 1 ? detailFor(1, 'open', 'Bad service') : detailFor(id, 'closed', id === 3 ? XSS : 'Rude doctor')));
    (replyToComplaint as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 10, body: 'x', complaint_status: 'open' });
  });

  it('AP5: lists complaints with patient, date, reply count and status, open ones by default', async () => {
    renderPage();
    const items = await screen.findAllByTestId('complaint-item');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('#1 Omar K.');
    expect(items[0]).toHaveTextContent('13 Nov - 1 reply');
    expect(items[1]).toHaveTextContent('2 replies');
    expect(items[2]).toHaveTextContent('no reply');
    expect(screen.getAllByTestId('complaint-status-badge')).toHaveLength(3);
    expect(getAdminComplaints).toHaveBeenCalledWith({ limit: 50, offset: 0, status: 'open' });
  });

  it('AP5: the detail shows the patient, the visit, the description and the reply thread', async () => {
    renderPage();
    await openComplaint(0);
    expect(getAdminComplaint).toHaveBeenCalledWith(1);
    const detail = screen.getByTestId('complaint-detail');
    expect(detail).toHaveTextContent('Patient: Omar K.');
    expect(screen.getByTestId('complaint-visit').textContent).toBe('Visit: Thu 12 Nov, 10:00 UTC, Dr. Omar Hassan, Cardiology, Nile Medical (Giza)');
    expect(screen.getByTestId('complaint-replies')).toHaveTextContent('admin1 (Sat 14 Nov, 09:00 UTC): We have contacted the clinic.');
  });

  it('E4: Close is its own confirmed action', async () => {
    renderPage();
    await openComplaint(0);
    fireEvent.click(screen.getByTestId('close-btn'));
    expect(screen.getByRole('dialog')).toHaveTextContent('Close complaint #1?');
    expect(closeComplaint).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('confirm-yes'));
    await waitFor(() => expect(closeComplaint).toHaveBeenCalledWith(1));
  });

  it('E4: a reply leaves the complaint open unless "Close complaint after sending" is ticked', async () => {
    renderPage();
    await openComplaint(0);
    fireEvent.change(screen.getByTestId('reply-body'), { target: { value: 'First reply.' } });
    fireEvent.click(screen.getByTestId('send-reply'));
    await waitFor(() => expect(replyToComplaint).toHaveBeenCalledWith(1, 'First reply.', false));

    fireEvent.change(screen.getByTestId('reply-body'), { target: { value: 'Final reply.' } });
    fireEvent.click(screen.getByTestId('close-after-send'));
    fireEvent.click(screen.getByTestId('send-reply'));
    await waitFor(() => expect(replyToComplaint).toHaveBeenCalledWith(1, 'Final reply.', true));
  });

  it('E5: a rejected reply shows the reason next to the reply box', async () => {
    (replyToComplaint as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ error: { message: "Closed complaints can't receive replies." } });
    renderPage();
    await openComplaint(0);
    fireEvent.change(screen.getByTestId('reply-body'), { target: { value: 'Sorry about that.' } });
    fireEvent.submit(screen.getByTestId('reply-body').closest('form') as HTMLFormElement);
    expect((await screen.findByTestId('reply-error')).textContent).toBe("Closed complaints can't receive replies.");
  });

  it('E5: a closed complaint has its reply box disabled with the reason', async () => {
    renderPage();
    await openComplaint(1);
    expect(screen.getByTestId('reply-body')).toBeDisabled();
    expect(screen.getByTestId('send-reply')).toBeDisabled();
    expect(screen.getByTestId('reply-closed-note').textContent).toBe("Closed complaints can't receive replies.");
    expect(screen.queryByTestId('close-btn')).toBeNull();
    expect(screen.getByTestId('complaint-detail')).toHaveTextContent('No reply yet');
  });

  it('AP5: an open complaint can receive a reply', async () => {
    renderPage();
    await openComplaint(0);
    expect(screen.getByTestId('send-reply')).toBeEnabled();
    expect(screen.getByTestId('reply-body')).toBeEnabled();
  });

  it('F17: a complaint written by a user is shown as text, never as HTML', async () => {
    const { container } = render(
      <MemoryRouter>
        <AdminComplaintsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/onerror/)).toBeTruthy());
    fireEvent.click(screen.getAllByTestId('complaint-item')[2] as HTMLElement);
    await waitFor(() => expect(screen.getByTestId('complaint-description')).toHaveTextContent('onerror'));
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });
});
