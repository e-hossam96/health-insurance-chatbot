# Demo script (about 10 minutes)

Setup: the stack is running with real models, the demo data is seeded, and `policy_handbook.pdf` and `member_guide.docx` from `packages/chatbot_ai/src/chatbot_ai/evals/kb_fixtures/` are uploaded and **Ready** in the admin panel. Grafana is open through the SSH tunnel on the **Demo overview** and **Chat and LLM** dashboards.

## 1. A new member (2 min)

1. Sign up as a new user. Onboarding asks for a name and location (Cairo) and warns that they can't be changed later.
2. The chat opens with six starter cards. Point out "All times are UTC" under the input.

## 2. Booking from a card (3 min)

1. Type "I need a dermatologist". The sidebar item becomes **Book a visit**.
2. The answer streams in and names up to three doctors with their dates and times in UTC; doctor cards appear after the last word.
3. Click **Book** on the first card. The card shows **Booked**, the other cards lock, and a confirmation appears in the chat. The model never booked anything; the click did.
4. Open **My visits & complaints** in the header: the visit is listed as Scheduled.
5. Optional: open a second browser as another member and book the same slot first, then click Book in the first browser: "This slot was just taken" with **Show other options**.

## 3. Policy questions from the knowledge base (2 min)

1. Start a new chat and click **Ask about my coverage**, or ask "How much is the co-pay for an outpatient visit?" (50 EGP) and "Does an MRI need approval, and how far ahead?" (3 working days, from a table in the member guide).
2. Ask something the documents don't cover, such as "Does the plan cover IVF?": the assistant answers "I couldn't find that in the documents." without guessing.

## 4. Cancel and complain (2 min)

1. "I want to cancel my appointment" offers the scheduled visit as a card; **Yes, cancel visit** cancels it and frees the slot.
2. In the admin panel, mark a visit as completed. Back in user view, "I want to complain about my last visit" offers that visit; describe the problem and submit. The admin sees it under **Complaints** and can reply; the member sees the reply in the drawer.

## 5. Behind the scenes (1 min)

1. Grafana **Chat and LLM**: turns by outcome and agent, time to first token, per-stage durations, tokens.
2. **Demo overview**: sign-ups, bookings, cancellations and complaints from the last day.
3. With Langfuse keys set, show the trace of a turn (`chat-<session id>`): classify, the tool calls, generate.

## Things to say

- Every change is a button click on a card; the model only reads data and proposes.
- Answers about policy come only from uploaded documents, with a fixed reply when nothing relevant is found.
- Each turn is routed to one specialist agent by a small classifier; the conversation history stays the same for all of them.
