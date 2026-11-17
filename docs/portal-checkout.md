# LAN portal checkout and account-state refinement

Reviewed 17 November 2026. Based on the reported status-button and malformed
Markdown-link experience and the exact LAN pilot tree at 55dd769. The report
contains no failed HTTP response for the button, so it does not establish one
specific production transport error. Source inspection confirmed that the old
renderer handled bold/code but not Markdown links, and a successful status read
cleared the alert without acknowledging an unchanged result.

## User-facing changes

- The service badge now says "services of Pishkhan", separate from authentication.
  A signed-out page has a prominent number-login CTA and no active chat input.
  A signed-in header shows the account number and signed-in state. OTP steps and
  loading labels are explicit. This remains a browser-isolated LAN pilot.
- Structured payment cards sit immediately under the conversation. They show the
  bill, amount/fee/total from stored PaymentInfo observations, actual HTTPS bank
  action and a separate status button. Model Markdown/HTML cannot create a bank
  action. The reported escaped/nested Markdown pattern is rendered as its label.
- Status clicks POST only to the browser-owned payment action. Loading, unchanged
  Unpaid, confirmed Paid and lookup error each have visible feedback. The last
  status-read time is shown. A confirmed complete payment no longer offers a bank
  button; checking it does not create another payment or call the model.
- History restoration rehydrates cards from the current account's observations,
  not from obsolete link text. Unknown fees stay unknown; zero fees display zero.

## Automatic link preparation

The portal post-processes successful inquiry tool results within the reserved
chat turn. It verifies the stored Operation and account, extracts the actual
BillUniqueID, and prepares a browser IPG link for a single positive unpaid bill.
This adds no model round trip or user message. It calls existing core tools and
retains their stable deduplication, request identity and gateway restrictions.
It never debits a wallet, submits CNPG/card details or performs the bank payment.

Preparation runs only for an inquiry executed in the turn, never for state,
history or operation-status reads. Existing attempts are retained, including
uncertain ones. Paid/zero/unknown-amount bills are excluded. Multiple positive
terms require an explicit choice rather than preparing potentially overlapping
payments. At most five unambiguous inquiry groups are processed per turn.

An enabled-by-default checkbox can disable automatic link creation for a turn.
The server also conservatively honors listed literal inquiry-only phrases (for
example `inquiry only`, `no payment link` and the corresponding Persian phrases).
This guard is not claimed as general intent understanding. A preparation error
leaves the successful inquiry available and reports that the link is not ready;
unknown payment outcomes are not blindly retried.

Configuration: `P24_AUTO_BILL_LINKS=true` (default). All payment completion rules,
including the reviewed Ghabzino Paid rule, are unchanged.

## Quota and upgrade

Default `AGENT_DAILY_MESSAGE_LIMIT=50` is global for the installation per Tehran
calendar day, not 50 for every person and not 50 calls/tokens. Message 51 is
blocked before a model call. Existing consumption is preserved. AGENT_MAX_STEPS
and the output-token cap are unchanged. Manual status buttons do not use model
quota. An existing `.env` with a limit of 10 will still override the new default.

Stop the server, run `git pull --ff-only`, `manage.py check` and `pytest -q`.
No dependency or migration is added. Keep the database and `.env`. Run:

```powershell
.\.venv\Scripts\python.exe scripts/run_lan.py --ip 192.168.3.45 --port 8000 --message-limit 50
```

The CLI option explicitly overrides an old limit for this server process and
prints the effective cap. For other launch methods, set the same value in `.env`.
Reload with Ctrl+F5 to fetch `pilot.js?v=lan2` and `pilot.css?v=lan2`.

## Verification

- 257 Python tests passed (233 prior, 24 new) on local Python 3.13 / SQLite.
- Full Django model/tool loop with synthetic model and Core responses: one user
  turn, three model steps, one inquiry and one payment-intent creation; no extra
  model call for automatic link preparation. Paid/zero/ambiguous/foreign/failed
  cases, replay, unknown outcomes, 50th/51st messages and history were checked.
- Node DOM tests execute the actual button handler and POST payload, unchanged
  status feedback, Paid link removal, error recovery, authentication states and
  malformed Markdown. Existing console-state tests also passed.
- Five independent HTTP cookie clients and ten synthetic concurrent chat turns
  passed the existing Uvicorn regression with an explicit ten-turn fixture cap.
  That fixture cap is intentional and separate from the new deployment default.
- Chromium rendered guest/member desktop and 390px mobile layouts; actual DOM
  login, chat and status clicks used injected synthetic fetch responses. Both
  status clicks used no extra chat/model turn. There was no horizontal overflow
  and no page JavaScript error. Direct browser navigation is blocked here by
  ERR_BLOCKED_BY_ADMINISTRATOR, so this is not claimed as a browser-to-live-Core
  end-to-end run. Python HTTP and backend tests are separate evidence.
- No production model call, SMS, bank call or charge was made by these tests.
  Published Windows/Linux CI must be read for the final revision separately.

For LAN acceptance, one inquiry should show an unpaid positive bill card with a
bank action without a follow-up message. The status button must acknowledge even
an unchanged result. No real payment is required just to check these UI changes.
