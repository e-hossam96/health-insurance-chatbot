import { type Route, expect, test } from '@playwright/test';

type Doc = {
  id: number;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  error_message: string | null;
  uploaded_by: string;
  created_at: string;
};

const LIMIT = 10 * 1024 * 1024;

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test.describe('AP1 KB documents', () => {
  test('upload, watch it become ready, reject a duplicate, and delete with confirmation', async ({ page }) => {
    const docs: Doc[] = [];
    const uploads: { filename: string; bytes: number }[] = [];
    let listCalls = 0;

    await page.route('**/api/auth/me', route => json(route, { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' }));
    await page.route('**/api/admin/kb-documents?limit=*', async route => {
      listCalls += 1;
      for (const doc of docs) {
        if (doc.status === 'processing') doc.status = 'ready';
        else if (doc.status === 'uploaded') doc.status = 'processing';
      }
      await json(route, { items: docs, total: docs.length, max_upload_bytes: LIMIT });
    });
    await page.route('**/api/admin/kb-documents?filename=*', async route => {
      const filename = new URL(route.request().url()).searchParams.get('filename') ?? '';
      const bytes = route.request().postDataBuffer()?.length ?? 0;
      uploads.push({ filename, bytes });
      if (docs.some(d => d.filename === filename)) {
        await json(route, { detail: { error: { code: 'duplicate_document', message: 'This file was already uploaded.' } } }, 409);
        return;
      }
      const doc: Doc = {
        id: docs.length + 1,
        filename,
        file_type: filename.split('.').pop() ?? '',
        file_size_bytes: bytes,
        status: 'uploaded',
        error_message: null,
        uploaded_by: 'admin1',
        created_at: '2026-11-14T10:00:00Z',
      };
      docs.push(doc);
      await json(route, doc, 201);
    });
    let deleted: number | null = null;
    await page.route('**/api/admin/kb-documents/*', async route => {
      if (route.request().method() !== 'DELETE') return route.fallback();
      deleted = Number(route.request().url().split('/').pop());
      docs.splice(docs.findIndex(d => d.id === deleted), 1);
      await route.fulfill({ status: 204 });
    });

    await page.goto('/admin/kb');
    await expect(page.getByTestId('kb-limit')).toHaveText('pdf, txt, docx · max 10 MB');

    await page.getByTestId('kb-file-input').setInputFiles({ name: 'handbook.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 demo') });
    await expect(page.getByTestId('kb-row')).toHaveCount(1);
    await expect(page.getByTestId('kb-status')).toHaveText('Ready', { timeout: 15_000 });
    expect(uploads).toEqual([{ filename: 'handbook.pdf', bytes: 13 }]);
    expect(listCalls).toBeGreaterThanOrEqual(3);

    await page.getByTestId('kb-file-input').setInputFiles({ name: 'handbook.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 demo') });
    await expect(page.getByTestId('kb-errors')).toHaveText('handbook.pdf: already uploaded.');
    await expect(page.getByTestId('kb-row')).toHaveCount(1);

    await page.getByTestId('kb-delete').click();
    await expect(page.getByRole('dialog', { name: 'Delete handbook.pdf?' })).toBeVisible();
    expect(deleted).toBeNull();
    await page.getByTestId('confirm-yes').click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText('No documents yet.')).toBeVisible();
    expect(deleted).toBe(1);
  });

  test('B5: the admin header tabs reach every section without typing a path', async ({ page }) => {
    await page.route('**/api/auth/me', route => json(route, { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' }));
    await page.route('**/api/admin/kb-documents?limit=*', route => json(route, { items: [], total: 0, max_upload_bytes: LIMIT }));
    await page.route('**/api/admin/locations', route => json(route, [{ id: 1, name: 'Cairo' }]));

    await page.goto('/admin/kb');
    const tabs = page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link');
    await expect(tabs).toHaveText(['Knowledge base', 'Catalog', 'Slots', 'Visits', 'Complaints']);
    await expect(page.getByTestId('admin-nav-kb')).toHaveAttribute('aria-current', 'page');

    await page.getByTestId('admin-nav-catalog').click();
    await expect(page).toHaveURL(/\/admin\/catalog$/);
    await expect(page.getByRole('heading', { name: 'Catalog' })).toBeVisible();
    await expect(page.getByTestId('admin-nav-catalog')).toHaveAttribute('aria-current', 'page');
  });
});
