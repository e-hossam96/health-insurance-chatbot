import { expect, test } from '@playwright/test';

test.describe('auth flows', () => {
  test('signup, onboarding, and empty chat', async ({ page }) => {
    await page.goto('/signup');
    await expect(page.getByText('Create your account')).toBeVisible();

    await page.fill('input[autocomplete="username"]', `e2e_user_${Date.now()}`);
    await page.fill('input[autocomplete="new-password"]', 'testpass123');
    const confirmInputs = page.locator('input[autocomplete="new-password"]');
    await confirmInputs.nth(1).fill('testpass123');
    await page.click('button:has-text("Sign up")');

    await expect(page).toHaveURL(/\/onboarding/, { timeout: 5000 });
    await expect(page.getByText('Complete your profile')).toBeVisible();

    await page.fill('input', 'E2E Test User');
    await page.selectOption('select', { index: 1 });
    await page.click('button:has-text("Continue")');

    await expect(page).toHaveURL(/\/chat/, { timeout: 5000 });
    await expect(page.getByTestId('chat-greeting')).toHaveText('Hi E2E Test User, how can I help today?');
  });

  test('admin login to /admin/kb', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[autocomplete="username"]', 'admin1');
    await page.fill('input[autocomplete="current-password"]', 'adminpass1');
    await page.click('button:has-text("Log in")');

    await expect(page).toHaveURL(/\/admin\/kb/, { timeout: 5000 });
    await expect(page.getByRole('heading', { name: 'Knowledge base' })).toBeVisible();
  });

  test('mode toggle', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[autocomplete="username"]', 'admin1');
    await page.fill('input[autocomplete="current-password"]', 'adminpass1');
    await page.click('button:has-text("Log in")');

    await expect(page).toHaveURL(/\/admin\/kb/, { timeout: 5000 });

    await page.click('[data-testid="mode-toggle"]');
    await expect(page).toHaveURL(/\/chat/, { timeout: 5000 });

    await page.click('[data-testid="mode-toggle"]');
    await expect(page).toHaveURL(/\/admin\/kb/, { timeout: 5000 });
  });
});
