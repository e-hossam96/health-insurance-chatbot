import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import type { KbDocument, KbDocumentList } from '../api/kb';
import { AdminKbPage } from './AdminKbPage';

vi.mock('../api/AuthContext', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/auth', () => ({ logout: vi.fn(), setMode: vi.fn() }));

vi.mock('../api/kb', async importOriginal => {
  const actual = await importOriginal<typeof import('../api/kb')>();
  return { ...actual, getKbDocuments: vi.fn(), uploadKbDocument: vi.fn(), reindexKbDocument: vi.fn(), deleteKbDocument: vi.fn() };
});

const kbApi = await import('../api/kb');
const getKbDocuments = vi.mocked(kbApi.getKbDocuments);
const uploadKbDocument = vi.mocked(kbApi.uploadKbDocument);
const reindexKbDocument = vi.mocked(kbApi.reindexKbDocument);
const deleteKbDocument = vi.mocked(kbApi.deleteKbDocument);

const LIMIT = 10 * 1024 * 1024;

function doc(overrides: Partial<KbDocument>): KbDocument {
  return {
    id: 1,
    filename: 'handbook.pdf',
    file_type: 'pdf',
    file_size_bytes: 2_200_000,
    status: 'ready',
    error_message: null,
    uploaded_by: 'admin1',
    created_at: '2026-11-14T23:30:00Z',
    ...overrides,
  };
}

function list(items: KbDocument[]): KbDocumentList {
  return { items, total: items.length, max_upload_bytes: LIMIT };
}

async function tickUntil(text: string): Promise<void> {
  for (let tick = 0; tick < 5 && screen.queryByText(text) === null; tick += 1) {
    await act(async () => vi.advanceTimersByTime(1000));
  }
  expect(await screen.findByText(text)).toBeTruthy();
}

function renderPage(pollMs = 3000): void {
  render(
    <MemoryRouter>
      <AdminKbPage pollMs={pollMs} />
    </MemoryRouter>,
  );
}

function pick(files: File[]): void {
  fireEvent.change(screen.getByTestId('kb-file-input'), { target: { files } });
}

describe('AdminKbPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getKbDocuments.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('G2: shows the upload limit from config and the document rows', async () => {
    getKbDocuments.mockResolvedValue(
      list([
        doc({}),
        doc({ id: 2, filename: 'faq.docx', file_type: 'docx', file_size_bytes: 80 * 1024, status: 'processing' }),
        doc({ id: 3, filename: 'old.txt', file_type: 'txt', file_size_bytes: 4096, status: 'failed', error_message: 'No extractable text (scanned PDFs are not supported)', uploaded_by: 'admin2' }),
      ]),
    );
    renderPage();
    expect(await screen.findByText('pdf, txt, docx - max 10 MB')).toBeTruthy();
    expect(screen.getAllByTestId('kb-status').map(s => s.textContent)).toEqual(['Ready', 'Processing', 'Failed']);
    expect(screen.getByText('2.1 MB')).toBeTruthy();
    expect(screen.getByText('80 KB')).toBeTruthy();
    expect(screen.getAllByText('14 Nov')).toHaveLength(3);
    expect(screen.getAllByTestId('kb-reindex')).toHaveLength(1);
    expect(screen.getAllByTestId('kb-retry')).toHaveLength(1);
  });

  it('G5: a failed row shows its error message on demand', async () => {
    getKbDocuments.mockResolvedValue(list([doc({ status: 'failed', error_message: 'Ingestion timed out after 600 s' })]));
    renderPage();
    fireEvent.click(await screen.findByTestId('kb-error-toggle'));
    expect(screen.getByTestId('kb-error-message').textContent).toBe('Ingestion timed out after 600 s');
  });

  it('G1 G2 G3: upload errors name the file and the reason', async () => {
    getKbDocuments.mockResolvedValue(list([]));
    uploadKbDocument
      .mockRejectedValueOnce(new kbApi.KbUploadError('unsupported_type', 'Only pdf, txt and docx files are supported.'))
      .mockRejectedValueOnce(new kbApi.KbUploadError('duplicate_document', 'This file was already uploaded.'))
      .mockRejectedValueOnce(new kbApi.KbUploadError('file_too_large', 'The file is larger than 10 MB.'));
    renderPage();
    await screen.findByTestId('kb-dropzone');
    pick([new File(['a'], 'slides.pptx'), new File(['b'], 'copy.pdf'), new File(['c'], 'big.pdf')]);
    const errors = await screen.findByTestId('kb-errors');
    expect(errors.textContent).toContain('slides.pptx: unsupported type (use pdf, txt or docx).');
    expect(errors.textContent).toContain('copy.pdf: already uploaded.');
    expect(errors.textContent).toContain('big.pdf: too large (max 10 MB).');
  });

  it('G2: a file over the limit is refused before it is sent', async () => {
    getKbDocuments.mockResolvedValue({ items: [], total: 0, max_upload_bytes: 4 });
    renderPage();
    await screen.findByText('pdf, txt, docx - max 4 B');
    pick([new File(['too many bytes'], 'big.txt')]);
    expect((await screen.findByTestId('kb-errors')).textContent).toBe('big.txt: too large (max 4 B).');
    expect(uploadKbDocument).not.toHaveBeenCalled();
  });

  it('G5: each file is uploaded on its own and the list reloads', async () => {
    getKbDocuments.mockResolvedValueOnce(list([])).mockResolvedValue(list([doc({ status: 'uploaded' }), doc({ id: 2, filename: 'faq.docx', status: 'uploaded' })]));
    uploadKbDocument.mockResolvedValue(doc({ status: 'uploaded' }));
    renderPage();
    await screen.findByTestId('kb-dropzone');
    const files = [new File(['a'], 'handbook.pdf'), new File(['b'], 'faq.docx')];
    pick(files);
    await waitFor(() => expect(screen.getAllByTestId('kb-row')).toHaveLength(2));
    expect(uploadKbDocument.mock.calls.map(c => c[0].name)).toEqual(['handbook.pdf', 'faq.docx']);
    expect(screen.queryByTestId('kb-errors')).toBeNull();
  });

  it('G5: the list polls while a row is uploaded or processing and stops when all are done', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    getKbDocuments
      .mockResolvedValueOnce(list([doc({ status: 'uploaded' })]))
      .mockResolvedValueOnce(list([doc({ status: 'processing' })]))
      .mockResolvedValue(list([doc({ status: 'ready' })]));
    renderPage(1000);
    expect(await screen.findByText('Uploaded')).toBeTruthy();
    // the interval is registered by an effect after the row renders, so tick until the next status shows
    await tickUntil('Processing');
    await tickUntil('Ready');
    const callsWhenDone = getKbDocuments.mock.calls.length;
    await act(async () => vi.advanceTimersByTime(5000));
    expect(getKbDocuments.mock.calls.length).toBe(callsWhenDone);
  });

  it('G6: Retry and Re-index call reindex', async () => {
    getKbDocuments.mockResolvedValue(list([doc({ id: 4, status: 'failed', error_message: 'x' }), doc({ id: 5, filename: 'b.pdf' })]));
    reindexKbDocument.mockResolvedValue(doc({ status: 'uploaded' }));
    renderPage();
    fireEvent.click(await screen.findByTestId('kb-retry'));
    await waitFor(() => expect(reindexKbDocument).toHaveBeenCalledWith(4));
    fireEvent.click(screen.getByTestId('kb-reindex'));
    await waitFor(() => expect(reindexKbDocument).toHaveBeenCalledWith(5));
  });

  it('G9: delete asks for confirmation first', async () => {
    getKbDocuments.mockResolvedValue(list([doc({ id: 9 })]));
    deleteKbDocument.mockResolvedValue();
    renderPage();
    fireEvent.click(await screen.findByTestId('kb-delete'));
    expect(deleteKbDocument).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('No'));
    expect(screen.queryByTestId('kb-confirm')).toBeNull();
    fireEvent.click(screen.getByTestId('kb-delete'));
    fireEvent.click(screen.getByTestId('kb-confirm-yes'));
    await waitFor(() => expect(deleteKbDocument).toHaveBeenCalledWith(9));
  });

  it('G9: a failed delete shows why and keeps the row', async () => {
    getKbDocuments.mockResolvedValue(list([doc({ id: 9 })]));
    deleteKbDocument.mockRejectedValue(new Error('The search index is unavailable. The document was kept.'));
    renderPage();
    fireEvent.click(await screen.findByTestId('kb-delete'));
    fireEvent.click(screen.getByTestId('kb-confirm-yes'));
    expect((await screen.findByTestId('kb-errors')).textContent).toBe('The search index is unavailable. The document was kept.');
    expect(screen.getAllByTestId('kb-row')).toHaveLength(1);
  });
});
