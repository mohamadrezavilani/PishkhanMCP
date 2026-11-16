# Verification - source/log alignment update

Review date: 2026-11-16. Runtime used: Python 3.13.5, locked dependencies,
SQLite. Source was obtained through the GitHub offline-bundle artifact because
this container could not clone from GitHub directly.

| Check | Observed result |
|---|---|
| Initial suite before these fixes | 92 passed, 1 failed (taxi expectation) |
| Updated regression suite | 117 passed |
| Django system check | No issues |
| Migration drift check | No changes detected |
| Migration application including 0002 | Successful |
| Ruff lint and format | Passed |
| In-process demo smoke | Passed |
| Actual Uvicorn GET /, /health/, /api/tools/, /api/services/ | All HTTP 200 |
| HTTP demo smoke + MCP initialize/list/call | Passed |
| Fresh live smoke (DeviceRegister only before failure) | UPSTREAM_CONNECTION; exit 1 |
| Fresh live OTP, paid inquiry, payment and webhook | Not performed |
| Docker/PostgreSQL execution | Not performed in this container |
| Real LLM conversation | Not performed; controlled agent-loop tests only |

Successful HTTP smoke check names:
product_scope, demo_login, distinct_requests_same_session, idempotent_replay,
demo_payment_receipt, request_trace, http_mcp_initialize_list_call.
It reported real_otp_sent=false and real_payment_attempted=false.

Regressions cover scope exclusion, separate electricity/water requests, continuity
across invoice steps, explicit relations without Query.UniqueID confusion,
active gateway selection, all eight PaymentInfo enum states, Paid vs Settle,
CNPG payload redaction, unknown payment deduplication, service/session mismatches
and a forged browser return that cannot change payment state.

Captured browser success in the supplied HAR is evidence of that capture, not a
fresh successful MCP production test. All fixture identities and money examples
used in tests are synthetic. No private source archive, HAR or log window is
part of the repository or release ZIP.
