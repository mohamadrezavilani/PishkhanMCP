# Live acceptance

First pass the demo and local HTTP/MCP checks in [run-and-test.md](run-and-test.md).
Changing `.env` does not change existing AccountSession.mode; restart the server
and create a new session.

1. Set the observed API host and P24_MODE=live. Run `smoke_test --live` (with
   `--base-url` for a running server). It performs only DeviceRegister/ConfigBasic.
2. Request a fresh login OTP for your own test account and verify it in the same
   session. A captured HAR OTP is not reusable.
3. Run one electricity inquiry with a valid identifier. Follow the actual
   quote stage: acknowledgement, service OTP, preview, active payment channel
   if required, then result. Record Request/Operation/Call IDs and the returned
   invoice/bill identifiers locally. Do not assume an inquiry is free.
4. Run a water inquiry in the same session. Its request_id must differ from
   electricity; each continuation must retain its own request_id.
5. Test a specifically approved payment in the company's test environment:
   select the returned active gateway, complete the provider flow, then query
   p24_payment_status with its PaymentKey. Inspect Paid vs Settle and individual
   bill states. A successful return URL is not sufficient.
6. For CNPG, use the existing client's valid session-encrypted EncryptData;
   test OTP and payment separately. This repository does not yet provide the
   card-entry/encryption UI. Do not retry an unknown payment outcome.
7. Confirm the Core webhook/reconciliation path using the company's controlled
   provider test setup, not by letting the agent forge a webhook.
8. Test concurrency on PostgreSQL, provider failures and recovery before use by
   multiple live users. The local regression run used SQLite.

This review did not complete a fresh live login, paid inquiry, bank payment or
provider webhook transaction. Local fresh bootstrap failed with UPSTREAM_CONNECTION.
No additional uploaded source is required to run the local/demo tests.
