import { type APIRequestContext, type Page, expect, test } from '@playwright/test';

async function signUpWithProfile(page: Page, username: string): Promise<void> {
  await page.goto('/signup');
  await page.fill('input[autocomplete="username"]', username);
  const passwords = page.locator('input[autocomplete="new-password"]');
  await passwords.nth(0).fill('e2epass123');
  await passwords.nth(1).fill('e2epass123');
  await page.click('button:has-text("Sign up")');
  await expect(page).toHaveURL(/\/onboarding/);
  await page.fill('input', 'E2E Member');
  await page.selectOption('select', { label: 'Cairo' });
  await page.click('button:has-text("Continue")');
  await expect(page).toHaveURL(/\/chat/);
}

async function addSpecialtyWithoutSlots(request: APIRequestContext, name: string): Promise<void> {
  const login = await request.post('/api/auth/login', { data: { username: 'admin1', password: 'adminpass1' } });
  expect(login.ok()).toBeTruthy();
  const created = await request.post('/api/admin/specialties', { data: { name } });
  expect([201, 409]).toContain(created.status());
}

test.describe('full scenario on the compose stack', () => {
  test('a specialty with free slots: recommend, book from the card, see it in my visits', async ({ page }) => {
    await signUpWithProfile(page, `e2e_book_${Date.now()}`);

    await page.getByTestId('chat-input').fill('I need a dermatologist');
    await page.getByTestId('send-btn').click();

    await expect(page.getByTestId('doctor-card').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('msg-assistant').last()).toContainText('Here are the earliest options');
    await expect(page.getByTestId('msg-assistant').last()).toContainText('UTC');
    const doctor = (await page.getByTestId('doctor-card').first().locator('.font-medium').textContent()) ?? '';
    expect(doctor).toMatch(/^Dr\. /);

    await page.getByTestId('book-btn').first().click();
    await expect(page.getByTestId('booked-badge')).toBeVisible();
    await expect(page.getByTestId('msg-assistant').last()).not.toContainText('Here are the earliest options');

    await page.getByTestId('visits-btn').click();
    await expect(page.getByText(doctor).first()).toBeVisible();
    await expect(page.getByText('Scheduled').first()).toBeVisible();
  });

  test('a specialty without free slots: the assistant says so and shows no cards', async ({ page, request }) => {
    await addSpecialtyWithoutSlots(request, 'Neurology');
    await signUpWithProfile(page, `e2e_none_${Date.now()}`);

    await page.getByTestId('chat-input').fill('I need a neurologist');
    await page.getByTestId('send-btn').click();

    await expect(page.getByTestId('msg-assistant').last()).toContainText('no doctor of that specialty has an available slot', { timeout: 30_000 });
    await expect(page.getByTestId('doctor-card')).toHaveCount(0);
    await expect(page.getByTestId('session-label').first()).toHaveText('Book a visit');
  });
});
