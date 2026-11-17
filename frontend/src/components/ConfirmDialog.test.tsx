import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { type ConfirmRequest, useConfirm } from './ConfirmDialog';

function Harness({ request }: { request: ConfirmRequest }): ReactNode {
  const { confirm, confirmDialog } = useConfirm();
  return (
    <>
      <button type="button" onClick={() => confirm(request)}>Delete row</button>
      {confirmDialog}
    </>
  );
}

function request(run: () => Promise<unknown>, tone?: 'danger' | 'primary'): ConfirmRequest {
  return { title: 'Delete Cairo?', message: 'This cannot be undone.', confirmLabel: 'Delete', failureText: 'Failed to delete', run, tone };
}

describe('useConfirm', () => {
  it('shows nothing and runs nothing until asked', () => {
    const run = vi.fn(() => Promise.resolve());
    render(<Harness request={request(run)} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(run).not.toHaveBeenCalled();
  });

  it('opens a labelled dialog with the safe choice focused', async () => {
    const user = userEvent.setup();
    render(<Harness request={request(() => Promise.resolve())} />);
    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    expect(screen.getByRole('dialog', { name: 'Delete Cairo?' })).toHaveTextContent('This cannot be undone.');
    expect(screen.getByTestId('confirm-cancel')).toHaveFocus();
    expect(screen.getByTestId('confirm-yes')).toHaveClass('btn-danger');
  });

  it('runs the action on confirm and closes', async () => {
    const user = userEvent.setup();
    const run = vi.fn(() => Promise.resolve());
    render(<Harness request={request(run)} />);
    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    await user.click(screen.getByTestId('confirm-yes'));
    expect(run).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('closes without running on Cancel, Escape or a click on the backdrop', async () => {
    const user = userEvent.setup();
    const run = vi.fn(() => Promise.resolve());
    render(<Harness request={request(run)} />);

    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    await user.click(screen.getByTestId('confirm-cancel'));
    expect(screen.queryByRole('dialog')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    const backdrop = screen.getByRole('dialog').parentElement as HTMLElement;
    await user.click(backdrop);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(run).not.toHaveBeenCalled();
  });

  it('keeps the dialog open with the server message when the action fails', async () => {
    const user = userEvent.setup();
    render(<Harness request={request(() => Promise.reject({ error: { message: "Can't delete: it has visit history." } }))} />);
    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    await user.click(screen.getByTestId('confirm-yes'));
    expect(await screen.findByTestId('confirm-error')).toHaveTextContent("Can't delete: it has visit history.");
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('falls back to the failure text when the error has no message', async () => {
    const user = userEvent.setup();
    render(<Harness request={request(() => Promise.reject(null))} />);
    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    await user.click(screen.getByTestId('confirm-yes'));
    expect(await screen.findByTestId('confirm-error')).toHaveTextContent('Failed to delete');
  });

  it('disables both buttons while the action runs', async () => {
    const user = userEvent.setup();
    let finish: () => void = () => {};
    const run = (): Promise<void> => new Promise(resolve => { finish = resolve; });
    render(<Harness request={request(run, 'primary')} />);
    await user.click(screen.getByRole('button', { name: 'Delete row' }));
    await user.click(screen.getByTestId('confirm-yes'));
    expect(screen.getByTestId('confirm-yes')).toBeDisabled();
    expect(screen.getByTestId('confirm-cancel')).toBeDisabled();
    expect(screen.getByTestId('confirm-yes')).not.toHaveClass('btn-danger');
    finish();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
