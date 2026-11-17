# Invited LAN pilot (17 November 2026)

This is a small, trusted-office pilot, not an Internet/public deployment. No
OAuth, ChatGPT plugin publication or account subscription is needed on client
machines. Only the host runs Django and holds the configured model credentials.

## What changed

- `/` is a responsive Persian RTL chat workspace. `/console/` preserves the old
  technical console, and existing Core sessions/operations are not deleted.
- OTP login is a form, outside the model conversation. The server binds the Core
  session to a database-backed Django browser session. Clients never choose an
  account by typing a session UUID. Each new browser connects its own account.
- Chat, history, saved bill cards, payment links, explicit status checks and
  feedback are presented without raw JSON. The model sees a small high-level
  bill toolset; no raw endpoint executor, token import, wallet debit or CNPG.
- LAN mode rejects non-loopback access to the developer API, console, admin and
  raw MCP. It uses the peer address, not client-supplied forwarding headers. The
  launcher disables Uvicorn proxy-header trust. Do not place this mode behind a
  reverse proxy that makes every remote user appear to be localhost.
- CSRF applies to browser POSTs. Payment URLs are structured Core output, not
  model-generated HTML. Only HTTPS links without embedded credentials render.
- Global model quota defaults to **50 user turns per Tehran calendar day for the
  whole installation**, not ten per person. Login, saved-history reads and
  payment-status buttons do not call the model. Multiple model requests may be
  used within one turn. `AGENT_MAX_OUTPUT_TOKENS=1200` caps each model response;
  it is not an exact monetary budget and does not cap input tokens.
- Chat turn keys are reserved server-side, retried responses are replayed, and
  simultaneous turns in one browser workspace are rejected. A network failure
  never auto-resubmits a model/payment request. Reload can recover a turn's
  recorded result. A crashed in-flight turn is not silently replayed.

## Windows host setup

Stop the old Uvicorn process. Keep `.env` and `db.sqlite3`. Back up your existing
SQLite database **while the server is stopped**. PostgreSQL users should use
their existing DB backup procedure instead.

```powershell
cd C:\Users\Administrator\PycharmProjects\PishkhanMCP
if (Test-Path db.sqlite3) {
    $backup = Join-Path $env:LOCALAPPDATA ("PishkhanMCP-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".sqlite3")
    Copy-Item db.sqlite3 $backup
    Write-Host "Database backup: $backup"
}
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "Pull failed; stop and preserve local changes." }
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw "Install failed." }
.\.venv\Scripts\python.exe manage.py migrate
if ($LASTEXITCODE -ne 0) { throw "Migration failed." }
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
ipconfig
```

The new migration is `portal.0001_initial`, adding browser workspaces, turn
reservations, payment observations and feedback. No Core records are rewritten.
If `git pull` says `Aborting`, do not continue on the previous revision. Keep
credentials in `.env`, not in the tracked `.env.example`.

Keep existing working `AGENT_BASE_URL`, model, API key, model-only proxy, and
`P24_MODE=live`. Keep `P24_PAYMENT_CALLBACK=` empty for the tested Core return.
Do not distribute `.env`, keys, database copies or proxy passwords to colleagues.

Find the IPv4 address of the network adapter connected to the office LAN, **not**
0.0.0.0, 127.0.0.1 or the default gateway/router. Example only: `192.168.1.20`.

```powershell
.\.venv\Scripts\python.exe scripts/run_lan.py --ip 192.168.1.20 --port 8000 --message-limit 50
```

The launcher checks/migrates the DB and starts one Uvicorn worker bound to
`0.0.0.0`. It sets DEBUG=false, exact ALLOWED_HOSTS and CSRF origins, LAN mode,
and --no-proxy-headers for that process without overwriting `.env`. If the
Django secret is still the sample, it creates a persistent ignored `.lan-secret`.
Preserve that file across restarts to keep browser cookies valid. It never
changes the configured message budget or silently switches live to demo.
`--demo` explicitly selects synthetic Core behavior; the chat model still needs
configuration. `--check-only` prints the addresses and checks/migrates without
opening the listening port. Multiple detected IPs require an explicit --ip.

**Address to share:** `http://192.168.1.20:8000/` (replace the IP). 0.0.0.0 is a
listen address, not a browser destination. The host, terminal, network link and
model connectivity must remain available; disable sleep for the pilot session.
No `--reload`, router port forwarding or public exposure is needed.

## Windows Firewall (only when needed)

From an elevated PowerShell, allow only the local subnet on Private/Domain
profiles, not all public networks:

```powershell
New-NetFirewallRule -DisplayName "PishkhanMCP LAN Pilot" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Private,Domain
```

If your corporate firewall policy is managed centrally, request this limited
rule from IT instead of disabling the firewall. Devices on a guest Wi-Fi, an
isolated VLAN or a different routed subnet may still be blocked. Check the
actual route with IT; do not broadly open every network.

From another Windows computer:

```powershell
Test-NetConnection 192.168.1.20 -Port 8000
```

The pilot is plain HTTP on a trusted internal network. It does not provide
transport encryption; use HTTPS before untrusted Wi-Fi or wider exposure.

## First acceptance run

In a second host terminal, with the server running:

```powershell
.\.venv\Scripts\python.exe manage.py pilot_smoke --base-url http://127.0.0.1:8000
.\.venv\Scripts\python.exe manage.py pilot_smoke --base-url http://192.168.1.20:8000
```

These checks are read-only: consumer HTML, local CSS/JS, health, CSRF bootstrap
and no inherited login in a fresh browser. They make no Core/model/OTP/payment
call. They are not a substitute for testing the actual second device.

Invite two or three colleagues first. Each opens the shareable address and logs
in with their own number and fresh OTP. No UUID, API key, JSON or software setup
is required. Accounts, history and bills must remain separate when switching
between devices. Old developer records remain in the host-only console; they
are not automatically attached to the new portal's browser session.

Acceptance checklist:

1. Page loads from a second device and narrow mobile viewport without a CDN.
2. Own-number OTP login works; the other browser cannot see these conversations.
3. One requested bill inquiry completes or clearly presents a required input.
4. Refresh restores the correct conversation. A double-click does not send two
   model turns. A transport interruption does not cause an automatic retry.
5. A requested payment link shows Core's actual amount and fee. Opening the bank
   is a human action; testing page accessibility does not require moving money.
6. After an authorized payment, use the **status** button for the same PaymentKey.
   A confirmed complete Ghabzino IPG payment stops polling, retains raw Paid,
   and does not invent Settle, a receipt or carrier debt reconciliation.
7. Feedback is recorded. Logout clears this browser connection. Re-login creates
   a new connection; account-wide, cross-device history merging is not included.

Do not make another real payment solely to exercise the interface. A screenshot,
model prose, or link creation alone is not proof of a completed payment.

## Feedback and recovery

```powershell
.\.venv\Scripts\python.exe manage.py pilot_report --feedback
```

This local command reports counts, recorded feedback, active turn IDs and the
shared model budget without consuming model credit. It does not export API keys.
If a process crashed during a turn, first STOP the server and inspect saved Core
operations via the local console. Do not blindly repeat an uncertain payment.
After inspection, a host operator can release only that crashed turn:

```powershell
.\.venv\Scripts\python.exe manage.py pilot_report --release-turn TURN_UUID --server-stopped
```

This marks the local turn unknown and releases its chat lease; it does not retry
any tool or modify a financial outcome. Never use it while the worker is running.

## Verification performed for this change

- Existing 192 tests passed before modification; the expanded test suite includes
  cookie ownership, CSRF, cross-account isolation, replay, budget, payment cards
  and LAN/loopback boundaries. 233 local pytest cases passed; read the published CI for its separate outcome.
- A real Uvicorn HTTP run tested two independent cookie clients, OTP demo login,
  a controlled model-to-demo-tool loop, history isolation and duplicate replay.
- A five-browser concurrent HTTP regression initially exposed SQLite deferred
  transaction lock-upgrade errors during login. Short transactions now use
  IMMEDIATE mode (30-second timeout). Five logins and ten chat turns passed in
  three consecutive runs; the eleventh model turn is blocked. The reproducible
  `python scripts/test_lan_http.py` uses a temporary DB and fake model, never
  your account or production database. This is a small-pilot check, not a
  throughput guarantee; use PostgreSQL before scaling beyond this pilot.
- Chromium rendered desktop (1440px) and mobile (390px) layouts. Form interaction,
  safe Markdown tables and zero horizontal overflow were checked with synthetic
  fetch responses. Direct Chromium navigation to localhost was blocked by the
  environment (ERR_BLOCKED_BY_ADMINISTRATOR), so this is not claimed as a full
  browser-to-live-server end-to-end test.
- Node tests exercise LAN HTTP UUID fallback, Markdown safety and null versus
  zero amounts. Tests do not spend Claude credit or contact Core production.
- The host's Windows firewall, office routing, real colleagues' OTP login and
  real model behavior still require the acceptance run on your own network.

References: Uvicorn settings, Django 5.2 sessions/CSRF and Microsoft's
New-NetFirewallRule documentation were checked. This pilot is not a claim of
production readiness or support for every catalog service.

## Checkout interface update

See [payment cards and automatic link preparation](portal-checkout.md). Existing
`.env` values still win over defaults; the explicit `--message-limit 50` launcher
option sets the effective shared daily cap without rewriting local secrets.
