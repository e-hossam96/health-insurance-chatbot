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

const STATUS_LABELS: Record<KbStatus, string> = {
  uploaded: 'Uploaded',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
};

const STATUS_STYLES: Record<KbStatus, string> = {
  uploaded: 'bg-gray-100 text-gray-700',
  processing: 'bg-blue-100 text-blue-700',
  ready: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
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
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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

  async function handleDelete(id: number): Promise<void> {
    setConfirmDelete(null);
    try {
      await deleteKbDocument(id);
      setErrors([]);
    } catch (error: unknown) {
      setErrors([error instanceof Error ? error.message : 'Delete failed.']);
    }
    await load();
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragging(false);
    void uploadFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 p-6 max-w-5xl w-full mx-auto space-y-4">
        <h1 className="text-xl font-semibold">Knowledge Base</h1>
        <div
          onDragOver={e => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`border-2 border-dashed rounded-lg p-6 text-center text-sm ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}`}
          data-testid="kb-dropzone"
        >
          Drag files here or{' '}
          <button type="button" onClick={() => inputRef.current?.click()} className="text-blue-600 underline">
            Browse
          </button>
          <span className="ml-2 text-gray-500" data-testid="kb-limit">
            pdf, txt, docx{maxBytes !== null ? ` - max ${formatBytes(maxBytes)}` : ''}
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
          <ul className="text-sm text-red-700 bg-red-50 rounded p-3 space-y-1" data-testid="kb-errors">
            {errors.map(message => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}

        <table className="w-full text-sm border-collapse" data-testid="kb-table">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="py-2">Filename</th>
              <th>Type</th>
              <th>Size</th>
              <th>Status</th>
              <th>Uploaded by</th>
              <th>Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 && (
              <tr>
                <td colSpan={7} className="py-6 text-center text-gray-500">No documents yet.</td>
              </tr>
            )}
            {documents.map(doc => (
              <KbRow
                key={doc.id}
                doc={doc}
                expanded={expanded === doc.id}
                confirming={confirmDelete === doc.id}
                onToggleError={() => setExpanded(expanded === doc.id ? null : doc.id)}
                onReindex={() => void handleReindex(doc.id)}
                onAskDelete={() => setConfirmDelete(doc.id)}
                onCancelDelete={() => setConfirmDelete(null)}
                onDelete={() => void handleDelete(doc.id)}
              />
            ))}
          </tbody>
        </table>
      </main>
    </div>
  );
}

function KbRow({ doc, expanded, confirming, onToggleError, onReindex, onAskDelete, onCancelDelete, onDelete }: {
  doc: KbDocument;
  expanded: boolean;
  confirming: boolean;
  onToggleError: () => void;
  onReindex: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
}): ReactNode {
  return (
    <>
      <tr className="border-b" data-testid="kb-row">
        <td className="py-2">{doc.filename}</td>
        <td>{doc.file_type}</td>
        <td>{formatBytes(doc.file_size_bytes)}</td>
        <td>
          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_STYLES[doc.status]}`} data-testid="kb-status">
            {STATUS_LABELS[doc.status]}
          </span>
          {doc.status === 'failed' && doc.error_message && (
            <button type="button" onClick={onToggleError} className="ml-1 text-xs text-gray-500" aria-label="Show error" data-testid="kb-error-toggle">
              (i)
            </button>
          )}
        </td>
        <td>{doc.uploaded_by}</td>
        <td>{formatUtcDay(doc.created_at)}</td>
        <td className="space-x-2 whitespace-nowrap">
          {doc.status === 'ready' && (
            <button type="button" onClick={onReindex} className="text-blue-600 underline" data-testid="kb-reindex">
              Re-index
            </button>
          )}
          {doc.status === 'failed' && (
            <button type="button" onClick={onReindex} className="text-blue-600 underline" data-testid="kb-retry">
              Retry
            </button>
          )}
          {confirming ? (
            <span data-testid="kb-confirm">
              Delete?{' '}
              <button type="button" onClick={onDelete} className="text-red-600 underline" data-testid="kb-confirm-yes">
                Yes
              </button>{' '}
              <button type="button" onClick={onCancelDelete} className="text-gray-600 underline">
                No
              </button>
            </span>
          ) : (
            <button type="button" onClick={onAskDelete} className="text-red-600 underline" data-testid="kb-delete">
              Delete
            </button>
          )}
        </td>
      </tr>
      {expanded && doc.error_message && (
        <tr>
          <td colSpan={7} className="pb-2 text-xs text-red-700" data-testid="kb-error-message">
            {doc.error_message}
          </td>
        </tr>
      )}
    </>
  );
}
