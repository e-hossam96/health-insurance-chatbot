import { type DragEvent, type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import {
  ACCEPTED_EXTENSIONS,
  type KbDocument,
  type KbStatus,
  KbUploadError,
  deleteKbDocument,
  formatBytes,
  formatUtcDay,
  getKbDocuments,
  needsPolling,
  reindexKbDocument,
  uploadKbDocument,
} from '../api/kb';
import { Header } from '../components/Header';
import { useConfirm } from '../components/ConfirmDialog';
import { InfoIcon, UploadIcon } from '../components/icons';

const STATUS_LABELS: Record<KbStatus, string> = {
  uploaded: 'Uploaded',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
};

const STATUS_STYLES: Record<KbStatus, string> = {
  uploaded: '',
  processing: 'new',
  ready: 'success',
  failed: 'danger',
};

function uploadErrorText(file: File, error: unknown, limit: number): string {
  if (error instanceof KbUploadError) {
    if (error.code === 'file_too_large') return `${file.name}: too large (max ${formatBytes(limit)}).`;
    if (error.code === 'unsupported_type') return `${file.name}: unsupported type (use pdf, txt or docx).`;
    if (error.code === 'duplicate_document') return `${file.name}: already uploaded.`;
    return `${file.name}: ${error.message}`;
  }
  return `${file.name}: upload failed.`;
}

export function AdminKbPage({ pollMs = 3000 }: { pollMs?: number }): ReactNode {
  const [documents, setDocuments] = useState<KbDocument[]>([]);
  const [maxBytes, setMaxBytes] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { confirm, confirmDialog } = useConfirm();

  const load = useCallback(async (): Promise<void> => {
    try {
      const data = await getKbDocuments();
      setDocuments(data.items);
      setMaxBytes(data.max_upload_bytes);
    } catch {
      setErrors(prev => (prev.includes('Could not load documents.') ? prev : [...prev, 'Could not load documents.']));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const polling = needsPolling(documents);
  useEffect(() => {
    if (!polling) return undefined;
    const timer = setInterval(() => void load(), pollMs);
    return () => clearInterval(timer);
  }, [polling, pollMs, load]);

  async function uploadFiles(files: File[]): Promise<void> {
    const limit = maxBytes ?? 0;
    const problems: string[] = [];
    for (const file of files) {
      if (limit > 0 && file.size > limit) {
        problems.push(`${file.name}: too large (max ${formatBytes(limit)}).`);
        continue;
      }
      try {
        await uploadKbDocument(file);
      } catch (error: unknown) {
        problems.push(uploadErrorText(file, error, limit));
      }
    }
    setErrors(problems);
    await load();
  }

  async function handleReindex(id: number): Promise<void> {
    try {
      await reindexKbDocument(id);
    } catch {
      setErrors(['Could not start re-indexing.']);
    }
    await load();
  }

  function askDelete(doc: KbDocument): void {
    confirm({
      title: `Delete ${doc.filename}?`,
      message: 'Its chunks are removed from search and the original file is deleted. This cannot be undone.',
      confirmLabel: 'Delete document',
      failureText: 'Delete failed.',
      run: async () => {
        await deleteKbDocument(doc.id);
        setErrors([]);
        await load();
      },
    });
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(false);
    void uploadFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="page flex-1 space-y-4">
        <h1 className="page-title">Knowledge base</h1>
        <div
          onDragOver={e => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex flex-col items-center gap-2 rounded-card border-2 border-dashed px-4 py-8 text-center text-sm transition-colors ${dragging ? 'border-accent bg-card' : 'border-line-strong bg-surface hover:border-accent'}`}
          data-testid="kb-dropzone"
        >
          <span className="inline-flex items-center gap-2 font-semibold">
            <span className="text-muted"><UploadIcon /></span>
            Drag files here or{' '}
            <button type="button" onClick={() => inputRef.current?.click()} className="link-btn underline">
              Browse
            </button>
          </span>
          <span className="text-muted" data-testid="kb-limit">
            pdf, txt, docx{maxBytes !== null ? ` · max ${formatBytes(maxBytes)}` : ''}
          </span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.join(',')}
            className="hidden"
            data-testid="kb-file-input"
            onChange={e => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = '';
              void uploadFiles(files);
            }}
          />
        </div>

        {errors.length > 0 && (
          <ul className="alert error space-y-1" data-testid="kb-errors">
            {errors.map(message => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}

        <div className="table-wrap">
        <table className="table" data-testid="kb-table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Type</th>
              <th>Size</th>
              <th>Status</th>
              <th>Uploaded by</th>
              <th>Date</th>
              <th className="text-right!">Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8! text-center! text-muted">No documents yet.</td>
              </tr>
            )}
            {documents.map(doc => (
              <KbRow
                key={doc.id}
                doc={doc}
                expanded={expanded === doc.id}
                onToggleError={() => setExpanded(expanded === doc.id ? null : doc.id)}
                onReindex={() => void handleReindex(doc.id)}
                onDelete={() => askDelete(doc)}
              />
            ))}
          </tbody>
        </table>
        </div>
        {confirmDialog}
      </main>
    </div>
  );
}

function KbRow({ doc, expanded, onToggleError, onReindex, onDelete }: {
  doc: KbDocument;
  expanded: boolean;
  onToggleError: () => void;
  onReindex: () => void;
  onDelete: () => void;
}): ReactNode {
  return (
    <>
      <tr data-testid="kb-row">
        <td className="font-medium">{doc.filename}</td>
        <td>{doc.file_type}</td>
        <td>{formatBytes(doc.file_size_bytes)}</td>
        <td>
          <span className={`badge ${STATUS_STYLES[doc.status]}`} data-testid="kb-status">
            {STATUS_LABELS[doc.status]}
          </span>
          {doc.status === 'failed' && doc.error_message && (
            <button
              type="button"
              onClick={onToggleError}
              className="btn btn-ghost btn-sm ml-1 px-1.5 py-1 align-middle"
              aria-label={expanded ? 'Hide error' : 'Show error'}
              aria-expanded={expanded}
              title={expanded ? 'Hide error' : 'Show error'}
              data-testid="kb-error-toggle"
            >
              <InfoIcon />
            </button>
          )}
        </td>
        <td>{doc.uploaded_by}</td>
        <td>{formatUtcDay(doc.created_at)}</td>
        <td>
          <div className="row-actions">
            {doc.status === 'ready' && (
              <button type="button" onClick={onReindex} className="btn btn-secondary btn-sm" data-testid="kb-reindex">
                Re-index
              </button>
            )}
            {doc.status === 'failed' && (
              <button type="button" onClick={onReindex} className="btn btn-secondary btn-sm" data-testid="kb-retry">
                Retry
              </button>
            )}
            <button type="button" onClick={onDelete} className="btn btn-danger-ghost btn-sm" data-testid="kb-delete">
              Delete
            </button>
          </div>
        </td>
      </tr>
      {expanded && doc.error_message && (
        <tr>
          <td colSpan={7} className="bg-danger-soft text-xs text-danger-fg" data-testid="kb-error-message">
            {doc.error_message}
          </td>
        </tr>
      )}
    </>
  );
}
