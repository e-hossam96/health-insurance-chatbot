import { type ReactNode, useCallback, useState } from 'react';
import { errorMessage } from '../api/client';
import { Dialog } from './Dialog';

export type ConfirmRequest = {
  title: string;
  message?: ReactNode;
  confirmLabel: string;
  tone?: 'danger' | 'primary';
  failureText: string;
  blocked?: string;
  run: () => Promise<unknown>;
};

function failureMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : errorMessage(err, fallback);
}

export function useConfirm(): { confirm: (request: ConfirmRequest) => void; confirmDialog: ReactNode } {
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const confirm = useCallback((next: ConfirmRequest): void => {
    setError('');
    setRequest(next);
  }, []);

  const cancel = useCallback((): void => {
    if (!busy) setRequest(null);
  }, [busy]);

  async function proceed(): Promise<void> {
    if (request === null) return;
    setBusy(true);
    setError('');
    try {
      await request.run();
      setRequest(null);
    } catch (err: unknown) {
      setError(failureMessage(err, request.failureText));
    } finally {
      setBusy(false);
    }
  }

  const tone = request?.tone ?? 'danger';
  const confirmDialog = (
    <Dialog open={request !== null} title={request?.title ?? ''} onClose={cancel} panelClassName="w-full max-w-md">
      <div data-testid="confirm-dialog">
        {request?.message && <div className="mb-4 text-sm text-muted">{request.message}</div>}
        {request?.blocked && (
          <p className="alert error mb-4" role="alert" data-testid="confirm-blocked">
            {request.blocked}
          </p>
        )}
        {error && (
          <p className="alert error mb-4" role="alert" data-testid="confirm-error">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-secondary btn-sm" onClick={cancel} disabled={busy} autoFocus data-testid="confirm-cancel">
            Cancel
          </button>
          <button
            type="button"
            className={`btn btn-sm ${tone === 'danger' ? 'btn-danger' : ''}`}
            onClick={() => void proceed()}
            disabled={busy || request?.blocked !== undefined}
            data-testid="confirm-yes"
          >
            {busy && <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}
            {request?.confirmLabel}
          </button>
        </div>
      </div>
    </Dialog>
  );

  return { confirm, confirmDialog };
}
