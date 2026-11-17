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

    const cards = page.getByTestId('doctor-card');
    await expect(cards.first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('msg-assistant').last()).toContainText('Here are the earliest options');
    expect(await cards.count()).toBeGreaterThan(1);
    const card = cards.first();
    await expect(card).toContainText('Dermatology');
    const doctor = (await card.getByTestId('doctor-name').textContent()) ?? '';
    expect(doctor).toMatch(/^Dr\. /);
    const cardTime = (await card.getByText(/UTC$/).textContent()) ?? '';

    await card.getByTestId('book-btn').click();
    await expect(card.getByTestId('booked-badge')).toBeVisible();
    for (const sibling of await page.getByTestId('book-btn').all()) {
      await expect(sibling).toBeDisabled();
    }

    // C8: the card shows the stored slot time in UTC although the browser runs in New York
    const visits = (await (await page.request.get('/api/me/visits')).json()) as { doctor_name: string; start_at: string; status: string }[];
    expect(visits).toHaveLength(1);
    const start = new Date(visits[0].start_at);
    const utcClock = `${String(start.getUTCHours()).padStart(2, '0')}:${String(start.getUTCMinutes()).padStart(2, '0')} UTC`;
    expect(cardTime).toContain(` ${start.getUTCDate()} `);
    expect(cardTime.endsWith(utcClock)).toBeTruthy();
    expect(visits[0].doctor_name).toBe(doctor);

    // D6: the four static messages are stored; the user and confirmation texts are shown
    const booking = `Book ${doctor} on ${cardTime}.`;
    await expect(page.getByTestId('msg-user').last()).toHaveText(booking);
    await expect(page.getByTestId('msg-assistant').last()).toHaveText('Your visit has been booked successfully.');

    // F12: reopening the session replays the transcript without cards
    await page.getByRole('button', { name: /New chat/ }).click();
    await page.getByTestId('session-label').first().click();
    await expect(page.getByTestId('msg-user').last()).toHaveText(booking);
    await expect(page.getByTestId('msg-assistant').last()).toHaveText('Your visit has been booked successfully.');
    await expect(page.getByTestId('doctor-card')).toHaveCount(0);

    await page.getByTestId('visits-btn').click();
    const row = page.getByTestId('visits-list').locator('div.border').filter({ hasText: doctor });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(cardTime);
    await expect(row.getByTestId('status-badge')).toHaveText(/Scheduled/i);
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
