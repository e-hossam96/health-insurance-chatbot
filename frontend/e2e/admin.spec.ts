import { type Page, type Route, expect, test } from '@playwright/test';

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function signInAsAdmin(page: Page): Promise<void> {
  await page.route('**/api/auth/me', route => json(route, { username: 'admin1', role: 'admin', has_profile: true, mode: 'admin' }));
  await page.route('**/api/admin/kb-documents?limit=*', route => json(route, { items: [], total: 0, max_upload_bytes: 10 * 1024 * 1024 }));
}

const LIGHT_BG = 'rgb(242, 245, 247)';
const DARK_BG = 'rgb(37, 32, 34)';

function bodyBackground(page: Page): Promise<string> {
  return page.evaluate(() => getComputedStyle(document.body).backgroundColor);
}

test.describe('theme', () => {
  test('a pinned dark theme is applied before the app script runs, and System clears it', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await signInAsAdmin(page);
    await page.goto('/admin/kb');
    await expect.poll(() => bodyBackground(page)).toBe(LIGHT_BG);

    await page.getByRole('button', { name: 'Dark theme' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect.poll(() => bodyBackground(page)).toBe(DARK_BG);

    await page.route('**/src/main.tsx', route => route.abort());
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.unroute('**/src/main.tsx');

    await page.reload();
    await expect.poll(() => bodyBackground(page)).toBe(DARK_BG);
    await page.getByRole('button', { name: 'Match system theme' }).click();
    await expect(page.locator('html')).not.toHaveAttribute('data-theme');
    await expect.poll(() => bodyBackground(page)).toBe(LIGHT_BG);
  });

  test('the theme follows the system when nothing is pinned', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await signInAsAdmin(page);
    await page.goto('/admin/kb');
    await expect(page.getByRole('button', { name: 'Match system theme' })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => bodyBackground(page)).toBe(DARK_BG);
    await page.emulateMedia({ colorScheme: 'light' });
    await expect.poll(() => bodyBackground(page)).toBe(LIGHT_BG);
  });
});

test.describe('admin row actions', () => {
  test('A5: catalog delete confirms in an in-app dialog, cancels on Escape, and shows a refusal', async ({ page }) => {
    const deleted: number[] = [];
    let nativeDialogs = 0;
    page.on('dialog', dialog => {
      nativeDialogs += 1;
      void dialog.dismiss();
    });
    await signInAsAdmin(page);
    await page.route('**/api/admin/locations', route => json(route, [{ id: 1, name: 'Cairo', clinic_count: 1 }, { id: 2, name: 'Giza', clinic_count: 0 }]));
    await page.route('**/api/admin/locations/*/cascade', route => json(route, { cascade: { clinics: 1, doctors: 2, slots: 16 }, blocked: null }));
    await page.route('**/api/admin/locations/*', async route => {
      if (route.request().method() !== 'DELETE') {
        await route.fallback();
        return;
      }
      const id = Number(route.request().url().split('/').pop());
      deleted.push(id);
      if (id === 2) {
        await json(route, { detail: { error: { code: 'has_visit_history', message: "Can't delete: it has visit history." } } }, 409);
        return;
      }
      await json(route, { deleted: true, cascade: { clinics: 0 } });
    });

    await page.goto('/admin/catalog');
    const deleteButtons = page.getByRole('button', { name: 'Delete' });
    await expect(deleteButtons).toHaveCount(2);

    await deleteButtons.first().click();
    const dialog = page.getByRole('dialog', { name: 'Delete Cairo?' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('Also deletes 1 clinic, 2 doctors, 16 slots.');
    await expect(page.getByTestId('confirm-cancel')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    expect(deleted).toEqual([]);

    await deleteButtons.first().click();
    await page.getByTestId('confirm-yes').click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(deleted).toEqual([1]);

    await deleteButtons.nth(1).click();
    await page.getByTestId('confirm-yes').click();
    await expect(page.getByTestId('confirm-error')).toHaveText("Can't delete: it has visit history.");
    await expect(page.getByRole('dialog', { name: 'Delete Giza?' })).toBeVisible();
    expect(nativeDialogs).toBe(0);
  });

  test('D3 E4: completing a visit and closing a complaint go through the confirm dialog', async ({ page }) => {
    const calls: string[] = [];
    let nativeDialogs = 0;
    page.on('dialog', dialog => {
      nativeDialogs += 1;
      void dialog.dismiss();
    });
    await signInAsAdmin(page);
    await page.route('**/api/admin/visits?*', route => json(route, {
      items: [{
        id: 5, profile_id: 1, slot_id: 9, status: 'scheduled', patient_name: 'Sara N.', location: 'Cairo',
        clinic: 'Cairo Clinic', specialty: 'Dermatology', doctor_name: 'Dr. Sara Nabil', start_at: '2026-11-15T10:00:00Z',
      }],
      total: 1,
    }));
    await page.route('**/api/admin/visits/*/complete', async route => {
      calls.push(new URL(route.request().url()).pathname);
      await json(route, { id: 5, status: 'completed' });
    });
    await page.route('**/api/admin/complaints?*', route => json(route, {
      items: [{ id: 7, visit_id: 5, description: 'Long wait', status: 'open', created_at: '2026-11-16T08:00:00Z', patient_name: 'Sara N.', reply_count: 0 }],
      total: 1,
    }));
    await page.route('**/api/admin/complaints/7', route => json(route, {
      id: 7, description: 'Long wait', status: 'open', created_at: '2026-11-16T08:00:00Z', patient_name: 'Sara N.',
      visit: { id: 5, start_at: '2026-11-15T10:00:00Z', doctor_name: 'Dr. Sara Nabil', specialty: 'Dermatology', clinic: 'Cairo Clinic', location: 'Cairo' },
      replies: [],
    }));
    await page.route('**/api/admin/complaints/*/close', async route => {
      calls.push(new URL(route.request().url()).pathname);
      await json(route, { id: 7, status: 'closed' });
    });

    await page.goto('/admin/visits');
    await page.getByRole('button', { name: 'Mark completed' }).click();
    await expect(page.getByRole('dialog', { name: "Mark Sara N.'s visit as completed?" })).toBeVisible();
    expect(calls).toEqual([]);
    await page.getByTestId('confirm-yes').click();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    await page.getByTestId('admin-nav-complaints').click();
    await page.getByTestId('complaint-item').click();
    await page.getByRole('button', { name: 'Close complaint' }).click();
    await expect(page.getByRole('dialog', { name: 'Close complaint #7?' })).toBeVisible();
    await page.getByTestId('confirm-yes').click();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    expect(calls).toEqual(['/api/admin/visits/5/complete', '/api/admin/complaints/7/close']);
    expect(nativeDialogs).toBe(0);
  });
});
