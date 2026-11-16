# PishkhanMCP

Django + MCP integration for Pishkhan24, with a Persian local console, a shared
tool registry, invoice workflows, request tracing and an optional conversational
agent. Python 3.12 or 3.13 is required.

**Start with [Run and test](docs/run-and-test.md).**

## Current scope and evidence

- Taxi is **not** a Pishkhan product in this integration. It is excluded from
  discovery, direct execution and generic invoice registration. Shared Core code
  is not proof of product availability. `apps/product_scope.py` is authoritative.
- The runtime catalog exposes 55 entries and the runtime registry 156 observed
  endpoint contracts, after applying scope and the source-backed contract overlay.
  These counts are **not** a count of working live services.
- 37 MCP tools share their implementation with the HTTP API and the agent.
- Demo covers electricity, water, freeway summary and parcel tracking. It never
  sends SMS, purchases an inquiry or transfers money.
- 117 automated tests, Django checks, migration checks and an actual local
  Uvicorn HTTP/MCP smoke run passed. See [verification](docs/verification.md).
- Fresh live bootstrap from the development container failed with
  `UPSTREAM_CONNECTION`; no live login or financial transaction was performed.
- CNPG tools accept the existing client's session-key-encrypted `EncryptData`.
  This version does not supply a card-entry/encryption UI and has not completed
  a live CNPG payment.

## Quick start (PowerShell)

```powershell
git clone https://github.com/mohamadrezavilani/PishkhanMCP.git
cd PishkhanMCP
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py smoke_test
.\.venv\Scripts\python.exe -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

Existing checkout: run `git pull --ff-only`, install the locked dependencies and
run `migrate` again. Do not overwrite an existing `.env`. Ensure `P24_MODE=demo`
for the first smoke test. In Bash, use `python3 -m venv .venv` and
`.venv/bin/python` instead of the Windows Python path.

The Persian console is at `http://127.0.0.1:8000/`; MCP is at
`http://127.0.0.1:8000/mcp`. Run this in a second terminal:

```powershell
.\.venv\Scripts\python.exe manage.py smoke_test --base-url http://127.0.0.1:8000
```

This checks the API **and** MCP initialize, tools/list and tools/call, rather
than merely checking that the HTTP port is open. The result must contain
`"ok": true` and `"http_mcp_initialize_list_call"`.

## Request identity and trace

| Identifier | Meaning |
|---|---|
| Core Session / token | The upstream account/device session; not a business operation ID |
| `session_id` | Local reference to that connection; it does not expose the token |
| `request_id` | One user behavior in MCP, explicitly labeled `request_id_origin=mcp` |
| `operation_id` | An executable step, with an idempotency key |
| `call_id` | One provider transport attempt, including outcome and duration |
| `upstream_request_id` | Core RequestID **only when actually returned**, otherwise null |
| PurchaseKey / BillUniqueID / PaymentKey | Explicit invoice, bill and payment relationships |

Electricity and water under the same session get different request IDs. A quote,
its OTP/preview/payment steps and result retrieval continue the same request.
Use `p24_begin_request` for explicit grouping and `p24_request_trace` to inspect
steps, calls, correlations and payment states. Do not reuse a request ID for a
different service. The supplied HAR exposes no Core RequestID; the app does not
fabricate one or inject an undocumented header.

## Payments

`PaymentInfo` is the authoritative read used for reconciliation. HTTP success,
a successful verification call, invoice finalization and bill settlement are
not interchangeable. `Paid` is kept separate from `Settle`; individual bill
statuses are returned separately. Unknown payment outcomes are not automatically
retried. Gateways are selected only from the current active payment channels.

IPG browser return and Core provider webhook are different paths. Core performs
verification and processes `InformBillsPaymentStatus`; MCP does not expose that
webhook as an agent tool. `/payments/return/` is informational and cannot mark a
payment successful. See [source/log review](docs/log-contract-review.md).

## Live bootstrap, without spending

Set these values in `.env`, restart Uvicorn and create a **new** session:

```dotenv
P24_MODE=live
P24_API_BASE_URL=https://core.pishkhan24.ayantech.ir/webservices
P24_APPLICATION=pishkhan24
P24_ORIGIN=web
P24_PLATFORM=web
P24_VERSION=1.0.0
P24_DEVICE_PARAMETERS={}
```

```powershell
.\.venv\Scripts\python.exe manage.py smoke_test --base-url http://127.0.0.1:8000 --live
```

This only creates a device session, reads ConfigBasic and checks MCP. It does
**not** request an OTP, debit a wallet or pay a bill. Complete fresh login and a
real inquiry manually using the guide. Never reuse a captured HAR OTP.

For a real payment, configure `P24_PAYMENT_CALLBACK` with a valid callback owned
by your installation and accepted by Core. A localhost placeholder cannot
establish payment validity or reachability from an external provider.

## Agent and MCP clients

External MCP clients provide their own model. The built-in chat additionally
requires a model endpoint supporting Chat Completions tool calling:

```dotenv
AGENT_BASE_URL=https://your-model-provider.example/v1
AGENT_API_KEY=
AGENT_MODEL=your-tool-capable-model
```

The example URL is not a deployed service. The app appends `/chat/completions`.
No model credentials are needed for `smoke_test` or direct tool use.

Local stdio: `python manage.py mcp_stdio`. Cloud MCP clients need your deployed,
reachable HTTPS server, not the developer container's loopback address. This
version is not a multi-tenant production deployment; OAuth is not implemented.
An optional `P24_ACCESS_KEY` protects a shared instance with a bearer header.

## Tests and Docker

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

The existing Compose stack uses PostgreSQL. Migrations are explicit:

```bash
docker compose build app
docker compose up -d db
docker compose run --rm app python manage.py migrate --noinput
docker compose up -d app
docker compose exec app python manage.py smoke_test --base-url http://127.0.0.1:8000
```

Docker/PostgreSQL were not run in the development container in this review;
local acceptance used SQLite and Python 3.13. Test concurrency on PostgreSQL
before allowing concurrent live payments.

## Documents and retained snapshots

- [Run and test](docs/run-and-test.md)
- [Source/log contract review](docs/log-contract-review.md)
- [Verification results](docs/verification.md)
- [Runtime action coverage](docs/action-coverage.md)
- [Live acceptance checklist](docs/live-validation.md)
- [Source/HAR correction note](docs/source-and-har-review.md)
- [MCP client examples](docs/mcp-clients.md)

The large JSON files under `catalog/data` and `providers/data` are retained
extraction snapshots, not the runtime product allowlist. The registry applies
`contract_overrides.json` and product scope before any discovery or execution.
Older architecture/service documents describe the initial extraction and must
not override the current scope or acceptance results. Raw company source, HAR,
log windows, credentials and local databases are not included in commits.
