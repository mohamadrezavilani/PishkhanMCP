# Correction to the initial source/HAR review

The authoritative updated review is [log-contract-review.md](log-contract-review.md).

The previous review incorrectly promoted taxi endpoints in a shared Core backend
to the Pishkhan product. The product owner explicitly says taxi is not offered.
It is now excluded from active discovery and execution, including generic invoice
registration. The existence of backend classes is not evidence of product scope.

The supplied HAR does record successful device registration, OTP login and an
electricity inquiry on core.pishkhan24.ayantech.ir. It does not record a bank
payment, expose Core RequestID to the client or prove that a fresh MCP live run
will succeed. The host mismatch was a real configuration discrepancy; calling
it the proven sole cause of GR0002 was too strong.

Private source/HAR/log values are not included in this repository. Captured
success, mock contract tests, a local HTTP run and a new production run remain
four distinct kinds of evidence.
