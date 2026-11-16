# Run and test PishkhanMCP

## 1. Update and install (PowerShell)

For an existing checkout:

```powershell
cd PishkhanMCP
git pull --ff-only
```

For a new checkout:

```powershell
git clone https://github.com/mohamadrezavilani/PishkhanMCP.git
cd PishkhanMCP
```

Create the environment only if it does not already exist:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Python 3.13 is also supported. In Bash use `python3 -m venv .venv` and then
`.venv/bin/python` wherever the examples use `.\.venv\Scripts\python.exe`.

Edit `.env` for the initial test:

```dotenv
P24_MODE=demo
DB_HOST=
P24_ACCESS_KEY=
```

An empty DB_HOST selects SQLite. Preserve other local credentials/settings.
A shell environment variable overrides `.env`; remove an old P24_MODE override
or set it consistently. Never copy the example over an existing `.env` blindly.

## 2. Migrate and validate

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe manage.py smoke_test
```

Expected: no Django issues, all tests pass, and smoke output has `ok: true`,
`mode: demo`, `real_otp_sent: false`, `real_payment_attempted: false`.
The migration adds request/call/correlation/payment state tables; old operation
rows are retained. No database reset is needed.

## 3. Start the actual HTTP and MCP server

```powershell
.\.venv\Scripts\python.exe -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. In a second terminal in the project directory:

```powershell
.\.venv\Scripts\python.exe manage.py smoke_test --base-url http://127.0.0.1:8000
```

The checks list must include `http_mcp_initialize_list_call`. This confirms
actual HTTP transport and MCP execution, not only Django's test client.
The endpoint is `/mcp` (no trailing slash). Use Uvicorn for this test; Django
runserver alone does not host the MCP ASGI router.

The smoke run checks no taxi discovery, demo OTP login, two distinct requests
for electricity and water under one session, repeat-call deduplication, demo
payment/receipt and request tracing. Its identifiers are synthetic.

## 4. Use the Persian console without an LLM

Create a session, select a tool, review/edit its JSON arguments and execute it.
The session ID is filled automatically. Select `p24_request_otp` with any demo
phone, then `p24_verify_otp` with `123456`, using different idempotency keys.

Example electricity tool arguments in demo:

```json
{"session_id":"<local-session-id>","bill_id":"000100","idempotency_key":"electricity-1"}
```

Use `p24_water_bill` with `bill_id: "000200"` and `idempotency_key: "water-1"`.
Check that the results' request_id values differ. The same tool/input/key must
return the same operation_id with replayed=true, not repeat execution.

The request-ID field and trace button show the current behavior's steps.
For explicit inspection use:

```json
{"session_id":"<local-session-id>","request_id":"<returned-request-id>"}
```

with `p24_request_trace`. To group several manual steps, first call
`p24_begin_request`, then supply its request_id on those steps. Quote/payment
continuations infer their request automatically. Never group water and electricity
only because they share the same session.

## 5. First live check (no OTP or payment)

Stop the server. Set in `.env`:

```dotenv
P24_MODE=live
P24_API_BASE_URL=https://core.pishkhan24.ayantech.ir/webservices
P24_APPLICATION=pishkhan24
P24_ORIGIN=web
P24_PLATFORM=web
P24_VERSION=1.0.0
P24_DEVICE_PARAMETERS={}
```

Restart Uvicorn, then:

```powershell
.\.venv\Scripts\python.exe manage.py smoke_test --base-url http://127.0.0.1:8000 --live
```

Expected checks: live_device_register, live_config_basic,
http_mcp_initialize_list_call. This does not send OTP or attempt payment.
UPSTREAM_CONNECTION is a network/DNS/connectivity failure, not evidence that
credentials or extra device fields are missing. UPSTREAM_REJECTED requires
reading the actual upstream code. Never substitute demo output for live failure.

## 6. Login and one real inquiry

Create a fresh live session in the console (do not reuse a demo session).
Call p24_request_otp for your authorized test phone, then p24_verify_otp with
the **fresh** code. Do not reuse the HAR's OTP or assume this environment can
read SMS. Use a new idempotency key for each distinct request/verify action.

Call p24_electricity_bill with a valid real identifier. In live mode it returns
an invoice/quote workflow, not necessarily the final bill. Read the returned
stage/next_step. Use p24_resume_inquiry for required acknowledgement or service
OTP, p24_pay_quote only when a charge is explicitly accepted, and
p24_run_inquiry after prerequisites/payment. Supply the returned quote_id.
Repeat for water with a distinct behavior. Inspect request traces.

Check the tool schemas at `/api/tools/` rather than guessing argument names.
The site may charge for an inquiry. Do not treat demo fee values as real prices.

## 7. Payment and webhook acceptance

Configure P24_PAYMENT_CALLBACK to the legitimate URL accepted by Core for this
installation. Select a gateway returned by current PaymentChannels. For bill
payment, supply the original Service (or the matching request_id for electricity
or water). Do not use Query.UniqueID as a BillUniqueID.

For IPG complete RedirectLink, then call p24_payment_status with the returned
PaymentKey. `Paid` does not mean `Settle`; inspect individual bill statuses.
For CNPG the tools need the existing client's encrypted EncryptData tied to this
session's public key; a card input/encryption UI is not delivered here. Never
submit card data or repeat an unknown payment just to make a smoke test pass.

Core owns verification and provider webhooks. The MCP browser return page does
not mark payment success; it only directs you to authoritative status checking.

## 8. Optional conversational agent

Direct tools and the smoke command work without a model. The console chat needs:

```dotenv
AGENT_BASE_URL=https://your-model-provider.example/v1
AGENT_MODEL=your-tool-capable-model
AGENT_API_KEY=
```

Use your actual compatible model endpoint and restart the app. A missing model
produces agent_not_configured; it does not mean MCP transport failed. No real
model endpoint was used in this review; the agent loop has controlled tests.

For an external MCP client use `http://127.0.0.1:8000/mcp` locally, or your own
deployed HTTPS address for a cloud client. This review has not deployed a public
server. Do not interpret a developer container's loopback URL as remotely hosted.
