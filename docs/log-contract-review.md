# Source and log contract review

Review date: 2026-11-16. Basis: the supplied Core source, HAR, log-window package
and the product owner's explicit clarification. This supersedes the earlier
claim that shared taxi code establishes a Pishkhan taxi product.

## Product availability

Taxi is excluded from active catalog entries, endpoint discovery, direct calls
and the generic InvoiceRegister Service argument. Source code availability is
not product activation. ConfigService.Active=false also blocks a new inquiry.

## What was actually present in the logs

The archive contains **four** five-minute windows, not three, covering
2026-10-23 11:20 through 11:40 UTC. Counts: 63,534; 68,887; 67,727; 62,524;
total **262,672 records**. Fields include RequestID, Session, CallPath, Counter,
ProcessID, ThreadID, level, message and ExecutionTime. Multiple internal call
paths occur within one RequestID. Session must not be used to collapse separate
user behaviors or to infer financial relationships.

No literal `correlation:` messages were found in these supplied windows.
The supplied source does contain those log calls. That difference is retained:
the capture does not establish the exact deployed source version or completeness
of every payment chain. The package manifest also does not establish traffic
representativeness or source finality. No raw payloads/identifiers are published.

## Identity and request boundaries

The user's Session identifies their Core connection; RequestID groups a behavior
and its internal calls. In source, Helper.GetRequestIdentifier reads
RequestContext.CurrentLocal.RequestID. Request scope infrastructure comes from
a dependency, and callbacks/jobs can create their own scopes.

The supplied HAR contains no Core RequestID in response bodies or headers.
MCP therefore has a **local** UserRequest ID, labeled `request_id_origin=mcp`,
separate from Core RequestID. A ProviderCall's upstream_request_id remains null
unless actual response metadata supplies it. No speculative request header is
sent. Existing records migrated from the old version keep a null request rather
than receiving fabricated history.

A new electricity behavior and a new water behavior get different UserRequests.
Invoice configuration, registration, OTP, payment and result retrieval can be
steps/calls of that behavior. Quote/payment continuation inherits its original
request, with session and cross-service checks.

## Explicit relations in the source

| Source file (under Core) | Relation |
|---|---|
| Intermediate/Persistence/Infrastructure/CommandHandlerBase.cs | InvoiceID-BillUniqueIDs |
| Intermediate/Modules/Sales/Commands/Payment/InvoicePaymentHandler.cs | InvoiceID-PaymentKey |
| Intermediate/Modules/Payment/Commands/Bills/BillsPaymentHandler.cs | BillUniqueIDs-PaymentKey |
| PaymentCallbackHandler, CnpgPaymentHandler, WalletPaymentHandler and review jobs | PaymentKey-Status verification outcome |

The last relation logs `Success`/`Failed` of the verification result. It is **not**
the PaymentStatus enum and must not be converted directly to `Settle`.
MCP retains links supported by actual wire input/output and their evidence.
For example, Query.UniqueID is not a BillUniqueID; a bill's Result.UniqueID and
its Payment/PaymentStatus structure identify the bill node. Shared Session or
nearby timestamps are not correlation evidence.

## Payment contracts and finality

Sources: WebServices/Contracts/ICore.cs;
Intermediate/Modules/Payment/Commands/Info/PaymentInfoModel.cs;
Intermediate/Persistence/Enums/PaymentStatus.cs;
Intermediate/Modules/Payment/CNPG/CnpgPayment/;
Intermediate/Modules/Payment/CNPG/CnpgRequestOtp/.

PaymentInfo receives PaymentKey and returns gateway/type, amounts, Status,
ExtraInfo, RedirectLink, Invoice and Bills. The source states are:
Unknown, Undefined, Unpaid, Paid, InProcess, Settle, Return and Unpayable.
Invoice lifecycle states are a different enum. `Paid` is payment received, not
proof of final bill settlement. MCP reports individual bill states separately.

IPG supplies a redirect for user action. CNPG uses CnpgRequestOtp and CnpgPayment
with PaymentKey and session-public-key-encrypted EncryptData. Payment OTP is not
login OTP. Native InApp_CNPG and external wallets retain their distinct flow.
The tools accept the existing client's encrypted payload; this change does not
add a new card entry/encryption UI. A transport timeout after payment leaves an
unknown result and does not authorize a second charge.

## Callback versus webhook

Source: Intermediate/Modules/Payment/Commands/Callback/PaymentCallbackHandler.cs.
Core loads the payment, verifies an unpaid payment through its payment service,
logs the verification outcome, then redirects to the configured callback.
A browser URL parameter is not independent proof of success.

Source: Intermediate/Webhooks/Commands/BillPayment/v2/InformBillsPaymentStatusHandler.cs.
Core receives provider bill-status notifications and persists bill payment
status/trace information. This is not the MCP `/payments/return/` page.
MCP does not create an agent-callable webhook or duplicate Core's settlement
logic. It reconciles a known session-owned PaymentKey through PaymentInfo.

## HAR and bootstrap

The HAR contains 409 network entries, including 14 successful API POSTs on
core.pishkhan24.ayantech.ir. DeviceRegister, OTP login and an electricity invoice
and result are observed. No bank payment was captured. HostOriginsMap contains
the observed host/origin pairing. That supports the corrected default host,
but does not prove the sole cause of the earlier GR0002 response. A fresh live
MCP bootstrap still requires a successful current network call.

See verification.md for what was executed locally and what remains unverified.
