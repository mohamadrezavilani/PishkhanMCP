# Payment callback: Core default return and local-error recovery

## Observed problem

The MCP layer raised `CALLBACK_NOT_CONFIGURED` when `P24_PAYMENT_CALLBACK`
was empty. In `prepare_bill_payment`, it did so after reserving a stable local
operation but before **any** upstream call. Subsequent requests for the same bill
replayed that saved failure even with a new client idempotency key.

This was our integration guard, not a refusal from a bank or from Core. The
reported mobile bill amount came from an agent reply; this patch does not verify
that bill, its amount, or a real transaction.

## Source evidence (user-supplied core-main.zip)

- `Core/Main/Helper/Helper.cs`, `ValidateCallBack`, lines 352-407: a null,
  empty or whitespace callback is accepted. For nonempty values, scheme, host,
  port, path prefix and allowed query parameters are checked.
- `Core/Main/ProjectValues.cs`, `AllowedDomains`: the supplied list includes
  the Pishkhan domains and selected development origins. It does **not** include
  `http://127.0.0.1:8000`. A reachable URL is not automatically an approved URL.
- `Core/Intermediate/Modules/Payment/Commands/Bills/BillsPaymentCommand.cs`
  and `Core/Intermediate/Modules/Sales/Commands/Payment/InvoicePaymentCommand.cs`
  invoke that validator.
- `Core/Intermediate/Modules/Payment/Commands/Callback/PaymentCallbackHandler.cs`:
  an absent/invalid absolute CallbackPage falls back to
  `https://pishkhan24.com/corecallback/#/payment/{PaymentKey}`. The same handler
  performs the applicable payment verification before redirecting.
- `Core/Pages/PaymentCallback.aspx.cs` receives the upstream payment callback and
  redirects the browser according to the handler result. This is not the MCP
  `/payments/return/` page and not a provider's bill-settlement webhook.

These are source observations, not proof of every deployed database procedure
or gateway's live behavior. No production bank call was made to verify this fix.

## Configuration

For the current local test, leave the local **.env** setting empty:

```dotenv
P24_PAYMENT_CALLBACK=
```

The MCP integration sends `Callback: ""` for BillsPayment and InvoicePayment.
This uses Core's supported default path rather than inventing a localhost URL.
The user may end up on the Pishkhan return page; return to the local agent and
check the **same** PaymentKey with `p24_payment_status`.

A custom return address remains supported, but it must be configured and allowed
by Core. No local allowlist bypass or change to Core is introduced here. The
local `/payments/return/` route remains informational and never marks a payment
as successful based on browser parameters.

The payment result reports `callback_mode: core_default` or `custom`. A redirect
or HTTP 200 is not settlement evidence; payment/bill state still comes from Core.

## Existing local failure

Retry the same `p24_prepare_bill_payment` tool with the same session, bill IDs,
Service, gateway and (when supplied) request_id. The original operation/request
IDs are retained. A different model-generated client key does not create a
second payment for the same bill set.

Recovery is limited to `FAILED` + `CALLBACK_NOT_CONFIGURED` with the identical
input fingerprint, no ProviderCall, no associated PaymentAttempt and no upstream
reference. A conditional database update claims the existing reservation once.
Another caller sees the claimed state and does not contact Core again. Any other
failure, timeout, unknown result, already-created payment, or cross-request
attempt is not automatically retried. Do not delete the database or operations.

## Test outcome

On Python 3.13/SQLite, all **145 tests** passed, including 18 added callback and
recovery cases. Django checks, migration drift check, Ruff lint and formatting
passed. The empty-callback regression also fails against the previous code.
Tests use synthetic upstream responses and do not consume model credit, send an
OTP or pay a real bill. GitHub CI is a separate result for the published commit.

## User-facing flow

For browser IPG, the agent uses the original Result.UniqueID bill identifier,
its Service, and an active gateway from BillsPaymentChannels to obtain the
actual RedirectLink and PaymentKey. Card details are entered on the bank page,
not in the agent chat. The final amount and any fee must come from tool results.
After user action, reconcile with PaymentInfo through `p24_payment_status`;
`Paid` remains different from `Settle`, including the individual bill states.
