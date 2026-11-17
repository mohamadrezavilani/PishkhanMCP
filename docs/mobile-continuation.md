# Mobile bill continuation, gateway recovery and conversation persistence

Reviewed 2026-11-17. Basis: the supplied agent trace and Core C# source. No raw
phone number, session, bill identifier, payment key or account response is stored
in these fixtures. This is an integration fix, not a live payment verification.

## Reproduced defects

1. The shared CellPhoneBills endpoint lists several product IDs. Choosing the
   first ID made an Mci inquiry look like irancell and rejected an explicitly
   correct mci request with REQUEST_SERVICE_MISMATCH.
2. Literal IPG was not an actual returned Gateway. The failed INVALID_GATEWAY
   operation retained a stable bill-set reservation; changing to a valid gateway
   then failed with IDEMPOTENCY_CONFLICT. Raising AGENT_MAX_STEPS cannot fix that.
3. The console retained session_id but stored conversation_id only in memory.
   Refresh lost the active conversation pointer, not necessarily the DB history.
   The supplied trace does not prove that Refresh caused the user's earlier loss.
4. A broad Persian mobile search required all tokens but lacked the mobile alias.
   Extra discovery calls and errors consumed the step budget before a final reply.

The two primary regression tests fail against the preceding implementation with
exactly REQUEST_SERVICE_MISMATCH and IDEMPOTENCY_CONFLICT; both pass after this fix.

## Product and wire contracts

Core/Intermediate/Modules/Services/Telecom/Commands/Bills/CellPhone/ contains the
CellPhoneBills Model, Command and Handler. The operator is explicit; Mci,
Irancell and Rightel are normalized case-insensitively. We do not infer an
operator from a phone prefix. A shared endpoint must use its explicit Operator,
a compatible request service or another unambiguous contract; never list order.

New tool p24_mobile_bill(phone, operator) prepares the invoice and returns the
usual quote_id. p24_run_inquiry retrieves its result. The tool never pays.
The catalog's mobile search aliases cover the reported Persian wording.

## Saved results and continuation

p24_recent_bills(session_id, service_id?, phone?, offset?, limit?) reads stored
successful bill results without upstream or model calls. It returns the original
BillUniqueID, request/operation/quote IDs, Service, amount, term and observation
time. Query.UniqueID is never a bill. Results are labeled stored observations,
not current debt checks. Recovery is scoped to the session, independent of chat.

Older incorrect irancell labels are not rewritten. The recovery result exposes
recorded_service_id separately from service_id derived from Query.Operator.
The original request ID and actual invoice Service are preserved for payment.

The console persists a conversation pointer per session, restores its text after
refresh, and lists old conversations through the recovery button. Selecting an
old conversation is explicit. Switching sessions does not reuse another session's
conversation. Separate server endpoints enforce the session/conversation pairing.

## Browser-only payment links

p24_bill_payment_options discovers active gateways for stored bills.
p24_bill_payment_link creates a browser IPG link from selected stored bill IDs.
It chooses an actual active OnlinePayment_/IPG_ gateway, never literal IPG,
and never falls back to a wallet or CNPG. Missing online gateways stop the flow.
A positive unpaid saved bill is required; Core still validates current payment
eligibility. Selecting multiple bill terms is the caller's decision, not inferred.

For an existing bill reservation, the original request is retained. A successful
or uncertain attempt is not replaced by a new payment. An INVALID_GATEWAY failure
may change only Gateway when all recorded calls were successful
core_bills_payment_channels_v1 reads, with no PaymentAttempt or upstream reference.
A conditional UPDATE claims it once. CALLBACK_NOT_CONFIGURED recovery retains
its prior stricter identical-input/no-call guards. Changing Service/subject/request
is not a way around deduplication. No DB deletion or blanket retry is introduced.

After preparing a link, PaymentInfo supplies Amount, Fee and TotalAmount. Missing
fields remain null, not zero or an invented fee. These fields come from
Core/Intermediate/Modules/Payment/Commands/Info/PaymentInfoModel.cs.
A link is not payment; Paid is not final bill Settle. Core owns callbacks/webhooks.

## Configuration and retry

Keep P24_PAYMENT_CALLBACK empty to use Core's default return; keep the existing
AGENT_MAX_STEPS and AGENT_DAILY_MESSAGE_LIMIT. No new dependencies or migrations.
Stop Uvicorn, git pull --ff-only, manage.py check, pytest -q, then restart Uvicorn.
Do not overwrite .env or delete db.sqlite3, operations, conversations or quotes.

First test without a model: p24_recent_bills for the existing session and phone,
then p24_bill_payment_link with the returned bill_ids and original request_id.
The link-only tool may create a real payment intent but does not submit payment.
For chat, recover the old conversation or ask the agent to recover the stored bill
before preparing its link. Paper BillID/PaymentID need not be requested when Core's
stored bill UniqueID exists.

Step-budget errors now include progress (request/operation/quote IDs and the last
unresolved tool error) rather than obscuring the underlying error behind the cap.

## Verification boundaries

Local Python 3.13/SQLite: 171 tests pass; Django checks, migration drift, Ruff
lint/format and the demo smoke run pass. The synthetic model-driven continuation
uses two tools and three model steps, with no new inquiry and one message-budget
unit. This is a controlled regression, not a claim about every live Claude run.

Console state behavior is tested with a Node DOM stub: pointer persistence,
reload initialization, session switching, history selection and explicit new chat.
A real Chromium navigation was attempted but the environment blocked localhost
with ERR_BLOCKED_BY_ADMINISTRATOR; no full browser-rendering claim is made.
No live model, SMS, bank request, wallet debit or card payment is used in tests.
GitHub CI outcomes must be read for the published revision separately.
