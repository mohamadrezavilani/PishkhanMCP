# Ghabzino IPG: Paid completes payment, not proof of carrier settlement

Reviewed 2026-11-17 against the supplied `core-main.zip` and the current MCP
implementation. This corrects the earlier advice to keep polling this gateway
until `Settle` and the unconditional `Paid -> paid_waiting_settlement` mapping
for this particular successful bill-payment flow.

## Source observations

Paths below are relative to the supplied Core directory, not public URLs.

- `Main/Helper/HelperPayment.cs:15-16` selects `IPGGhabzino` for
  `OnlinePayment_AP_Ghabzino` and `OnlinePayment_Sadad_Ghabzino`.
- `Intermediate/Modules/Payment/IPG/External/Ghabzino/IPGGhabzino.cs:136-185`
  queries the downstream PaymentInfo. At least one successful bill sets the
  payment to `Paid` (lines 146-150); individual bills become `Paid` or `Unpaid`
  from their own success flags (lines 164-180).
- In that file, `Verify():88-99` accepts `Paid` or `Settle`, reports the
  transaction, and then reports `PaymentServiceStatus.Complete`. This source
  path does not require `Paid` to transition to `Settle` to finish verification.
  A payment-level `Paid` alone cannot establish success of all bills.
- `Intermediate/Modules/Payment/Commands/Info/PaymentInfoHandler.cs:10-55`
  reads stored payment info/details and retrieves the bills. It does not call
  IPGGhabzino.VerifyTransaction when the client polls PaymentInfo.
- `Intermediate/Persistence/Payment/Payment.cs:35-69` constructs ExtraInfo from
  database fields for DateTime, TraceNumber and CardPAN. It does not assign
  TransactionUniqueID in this method. `PaymentInfoHandler.cs:28-34` exposes the
  DTO properties, but their nullability is not a completion test.
- `Intermediate/Webhooks/Commands/BillPayment/v2/InformBillsPaymentStatusHandler.cs:14-68`
  maps incoming bill statuses to a database procedure. The ZIP has the C# wrapper,
  not the stored procedure implementation or live delivery logs. It cannot prove
  this transaction's webhook delivery, a future status transition, or a timeout.

## Interpretation and patch scope

Raw `payment_status`, `bill_statuses`, receipt fields and the existing `settled`
flag are unchanged. `settled` remains a payment-level observation of raw Settle;
false means Settle was not reported, not that a known settlement failed.

For the two reviewed Ghabzino **IPG** gateways, `Paid` plus a successful status
(Paid or Settle) for every expected bill completes the payment task:

```json
{
  "payment_status": "Paid",
  "payment_confirmed": true,
  "all_bills_payment_confirmed": true,
  "payment_complete": true,
  "financial_state": "paid",
  "pending": false,
  "requires_user_action": false,
  "settled": false,
  "all_bills_settlement_reported": false,
  "completion_basis": "ghabzino_ipg_all_bills_paid"
}
```

That is a normalized interpretation, not a rewritten Core response. It does not
claim that the carrier has cleared the debt, produce a settlement certificate,
or create a bank trace number. Missing expected bills, conflicting observations,
unknown status and partial success cannot complete the whole payment. A raw
payment-level Settle also does not hide an explicitly unpaid expected bill.

Other gateways do not inherit this source-specific Paid completion rule. Their
legacy paid_waiting_settlement label is retained for compatibility, not as a
promise of a future Settle event. Additional contracts should be reviewed before
expanding the supported completion rules.

The original payment operation becomes completed after this successful status
read. Its normalized requires_user_action/pending flags are updated and next_step
becomes none. The raw status is still Paid. Repeated reads only call PaymentInfo;
no payment is repeated, no record is deleted, and no financial state is forced.
The agent prompt stops asking for more polling merely to obtain Settle once
payment_complete=true. No new dependency or migration is required.

## Regression verification

A synthetic Ghabzino IPG response with one Paid bill reproduces the previous bug:
`assert result["pending"] is False` fails on the previous implementation. The
same test passes after the patch. There are 21 additional test cases, including
partial/missing bills, conflicting duplicates, unknown gateways, unconfirmed
payment states, repeat status reads, and explicit Settle reporting.

Local Python 3.13/SQLite: **192 tests passed**. Django check, migration drift,
Ruff lint/format and the demo smoke command also passed. Tests use synthetic
payloads and do not contact a model, bank, SMS service or Core production.
The Windows/Linux CI outcome must be checked for the published commit separately.

## Upgrade and check

Stop Uvicorn; run git pull --ff-only, manage.py check and pytest -q; restart
Uvicorn. Keep the existing database, session and PaymentKey. Call
p24_payment_status once with that existing PaymentKey to refresh its normalized
local status. Do not create another payment, replay a callback, invoke a webhook,
or edit the database to force Settle. The existing ten-message budget is unchanged.
