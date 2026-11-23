import { type Page, type Route, expect, test } from '@playwright/test';

type SseEvent = [name: string, data: Record<string, unknown>];

const SESSION_ID = 21;

const DOCTORS = {
  language: 'en',
  type: 'doctors',
  items: [
    { slot_id: 1, doctor_name: 'Dr. Sara Nabil', specialty: 'Dermatology', clinic: 'Cairo Clinic', location: 'Cairo', start_at: '2026-12-15T10:00:00Z' },
    { slot_id: 2, doctor_name: 'Dr. Omar Hassan', specialty: 'Dermatology', clinic: 'Nile Medical', location: 'Cairo', start_at: '2026-12-16T14:00:00Z' },
  ],
};

const VISIT = { visit_id: 7, start_at: '2026-11-12T10:00:00Z', doctor_name: 'Dr. Sara Nabil', specialty: 'Dermatology', clinic: 'Cairo Clinic' };

function sse(events: SseEvent[]): string {
  return events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join('');
}

function turn(text: string, cards?: Record<string, unknown>): string {
  const events: SseEvent[] = [['session', { session_id: SESSION_ID }]];
  for (const word of text.split(' ')) events.push(['token', { text: `${word} ` }]);
  if (cards) events.push(['cards', cards]);
  events.push(['done', {}]);
  return sse(events);
}

function staticMessages(user: string, assistant: string): Record<string, unknown>[] {
  return [
    { id: 101, session_id: SESSION_ID, role: 'user', content: user },
    { id: 104, session_id: SESSION_ID, role: 'assistant', content: assistant },
  ];
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockSignedInUser(page: Page, chatBodies: (string | 'hang')[]): Promise<{ chatRequests: Record<string, unknown>[] }> {
  const chatRequests: Record<string, unknown>[] = [];
  await page.route('**/api/auth/me', route => json(route, { username: 'user1', role: 'user', has_profile: true, mode: 'user' }));
  await page.route('**/api/me/sessions', route => json(route, []));
  await page.route('**/api/me/chat', async route => {
    chatRequests.push(route.request().postDataJSON() as Record<string, unknown>);
    const body = chatBodies.shift();
    if (body === 'hang' || body === undefined) return;
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body });
  });
  return { chatRequests };
}

async function send(page: Page, text: string): Promise<void> {
  await page.getByTestId('chat-input').fill(text);
  await page.getByTestId('send-btn').click();
}

test.describe('chat against stub scenarios', () => {
  test('book: Book marks the card booked and appends the static messages', async ({ page }) => {
    const { chatRequests } = await mockSignedInUser(page, [turn('Here are the earliest options.', DOCTORS)]);
    let bookBody: unknown = null;
    await page.route('**/api/me/visits', async route => {
      bookBody = route.request().postDataJSON();
      await json(route, { visit: { id: 30, status: 'scheduled' }, messages: staticMessages('Book Dr. Sara Nabil, Tue 15 Dec, 10:00 UTC.', 'Your visit is booked.') }, 201);
    });

    await page.goto('/chat');
    await page.getByTestId('starter-card').first().click();
    await expect(page).toHaveURL(new RegExp(`/chat/${SESSION_ID}$`));
    expect(chatRequests[0]).toEqual({ message: "I'd like to book a clinic visit." });
    await expect(page.getByTestId('doctor-card')).toHaveCount(2);
    await expect(page.getByText('Tue 15 Dec, 10:00 UTC')).toBeVisible();

    await page.getByTestId('book-btn').first().click();
    await expect(page.getByTestId('booked-badge')).toBeVisible();
    await expect(page.getByTestId('book-btn')).toBeDisabled();
    await expect(page.getByText('Your visit is booked.')).toBeVisible();
    expect(bookBody).toEqual({ session_id: SESSION_ID, slot_id: 1, language: 'en' });
  });

  test('F17: Arabic cards use Arabic labels, keep the database names and book in Arabic', async ({ page }) => {
    await mockSignedInUser(page, [turn('هذه أقرب المواعيد المتاحة.', { ...DOCTORS, language: 'ar' })]);
    let bookBody: unknown = null;
    await page.route('**/api/me/visits', async route => {
      bookBody = route.request().postDataJSON();
      await json(route, { visit: { id: 30, status: 'scheduled' }, messages: staticMessages('احجز موعدًا مع Dr. Sara Nabil يوم الثلاثاء 15 ديسمبر، 10:00 UTC.', 'تم حجز موعدك بنجاح.') }, 201);
    });

    await page.goto('/chat');
    await send(page, 'أريد حجز موعد');
    await expect(page.getByTestId('chat-cards')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('doctor-name').first()).toHaveText('Dr. Sara Nabil');
    await expect(page.getByText('Cairo Clinic, Cairo').first()).toBeVisible();
    await expect(page.getByText('الثلاثاء 15 ديسمبر، 10:00 UTC')).toBeVisible();
    await expect(page.getByTestId('book-btn').first()).toHaveText('احجز');

    await page.getByTestId('book-btn').first().click();
    await expect(page.getByTestId('booked-badge')).toHaveText('تم الحجز');
    await expect(page.getByText('تم حجز موعدك بنجاح.')).toBeVisible();
    expect(bookBody).toEqual({ session_id: SESSION_ID, slot_id: 1, language: 'ar' });
  });

  test('slot taken: the card says so and Show other options sends a new turn', async ({ page }) => {
    const { chatRequests } = await mockSignedInUser(page, [
      turn('Here are the earliest options.', DOCTORS),
      turn('Here are some other options.'),
    ]);
    await page.route('**/api/me/visits', route =>
      json(route, { detail: { error: { code: 'slot_taken', message: 'This slot was just taken.' } } }, 409),
    );

    await page.goto('/chat');
    await send(page, 'I want to book a dermatologist');
    await page.getByTestId('book-btn').first().click();
    await expect(page.getByText('This slot was just taken')).toBeVisible();
    await page.getByTestId('show-other-btn').click();
    await expect(page.getByText('Here are some other options.')).toBeVisible();
    expect(chatRequests[1]).toEqual({ message: 'Show me other options.', session_id: SESSION_ID });
  });

  test('complaint: select a visit, describe it, and the card shows Complaint filed', async ({ page }) => {
    await mockSignedInUser(page, [turn('Which visit is this about?', { type: 'visits_for_complaint', items: [VISIT] })]);
    let complaintBody: unknown = null;
    await page.route('**/api/me/complaints', async route => {
      complaintBody = route.request().postDataJSON();
      await json(route, {
        complaint: { id: 3, visit_id: 7, description: 'Long wait', status: 'open' },
        messages: staticMessages('Complaint about the visit on Thu 12 Nov, 10:00 UTC.', 'Your complaint was filed.'),
      }, 201);
    });

    await page.goto('/chat');
    await send(page, 'I want to file a complaint');
    await page.getByTestId('select-visit-btn').click();
    await expect(page.getByTestId('submit-complaint-btn')).toBeDisabled();
    await page.getByTestId('complaint-desc').fill('Long wait');
    await page.getByTestId('submit-complaint-btn').click();
    await expect(page.getByTestId('filed-badge')).toBeVisible();
    await expect(page.getByText('Your complaint was filed.')).toBeVisible();
    expect(complaintBody).toEqual({ session_id: SESSION_ID, visit_id: 7, description: 'Long wait', language: 'en' });
  });

  test('cancel: Yes, cancel visit marks the card cancelled', async ({ page }) => {
    await mockSignedInUser(page, [turn('Which visit do you want to cancel?', { type: 'cancel_confirm', items: [VISIT] })]);
    let cancelBody: unknown = null;
    await page.route('**/api/me/visits/7/cancel', async route => {
      cancelBody = route.request().postDataJSON();
      await json(route, { visit: { id: 7, status: 'cancelled' }, messages: staticMessages('Cancel my visit on Thu 12 Nov, 10:00 UTC.', 'Your visit is cancelled.') });
    });

    await page.goto('/chat');
    await send(page, 'I want to cancel a visit');
    await page.getByRole('button', { name: 'Yes, cancel visit' }).click();
    await expect(page.getByTestId('cancelled-badge')).toBeVisible();
    await expect(page.getByText('Your visit is cancelled.')).toBeVisible();
    expect(cancelBody).toEqual({ session_id: SESSION_ID, language: 'en' });
  });

  test('Stop: the input is locked while streaming and Stop gives the text back', async ({ page }) => {
    await mockSignedInUser(page, ['hang']);
    const aborted = page.waitForEvent('requestfailed', request => request.url().endsWith('/api/me/chat'));

    await page.goto('/chat');
    await send(page, 'a slow question');
    await expect(page.getByTestId('chat-input')).toBeDisabled();
    await expect(page.getByTestId('typing-indicator')).toBeVisible();
    await page.getByTestId('stop-btn').click();
    expect((await aborted).failure()?.errorText).toBeTruthy();
    await expect(page.getByTestId('chat-input')).toBeEnabled();
    await expect(page.getByTestId('chat-input')).toHaveValue('a slow question');
    await expect(page.getByTestId('msg-user')).toHaveCount(0);
    await expect(page.getByTestId('send-btn')).toBeVisible();
  });

  test('error: the turn shows Something went wrong and Retry resends it', async ({ page }) => {
    const { chatRequests } = await mockSignedInUser(page, [
      sse([['session', { session_id: SESSION_ID }], ['error', { code: 'turn_error', message: 'Something went wrong.' }]]),
      turn('All good now.'),
    ]);

    await page.goto('/chat');
    await send(page, 'trigger an error');
    await expect(page.getByText('Something went wrong.')).toBeVisible();
    await page.getByTestId('retry-btn').click();
    await expect(page.getByText('All good now.')).toBeVisible();
    await expect(page.getByTestId('chat-error')).toHaveCount(0);
    await expect(page.getByTestId('msg-user')).toHaveCount(1);
    expect(chatRequests[1]).toEqual({ message: 'trigger an error' });
  });
});
