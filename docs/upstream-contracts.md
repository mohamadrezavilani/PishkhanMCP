# قراردادهای مشاهده‌شدهٔ پیشخوان۲۴

Reviewed: **2026-11-16**. See [company source and HAR review](source-and-har-review.md) for source-backed bootstrap, login, electricity and taxi contracts. The registry in `apps/providers/data/pishkhan_actions.json`
contains **153 distinct endpoint actions** found in public frontend JavaScript.
These are source-observed contracts, not an internal OpenAPI specification and
not a claim that 153 authenticated journeys have passed live tests.

## Evidence and current limitation

The public site is a Nuxt application. Its main bundle was
[`CpQMm8z7.js`](https://pishkhan24.com/_nuxt/CpQMm8z7.js). The review followed its
referenced modules and inspected 224 JavaScript files including the main bundle.
No account login, OTP delivery, paid inquiry, wallet debit or payment was executed.

Two small API observations were made:

| Request | Observed result | Interpretation |
| --- | --- | --- |
| `core/v1/ConfigBasic` without a token | `G00002`, expired session | Confirms the response envelope and unauthenticated error handling |
| `core/v2/DeviceRegister` with the four public runtime fields | `GR0002`, input validation | Bootstrap is **not live validated**; the missing requirement is unknown |

The bootstrap request used `Application=pishkhan24`, `Origin=web`, `Platform=web`,
`Version=1.0.0`, exactly as published in the HTML runtime configuration. Both the
global initializer and the login-page reinitializer send these four fields.
The application interceptor sets `Identity.Token` to the token or the empty
string; it does not send `null` and does not inject another application body
field. The source does not explain the backend rejection. Obtain a successful,
redacted internal request or a company-approved API contract before claiming that
new live sessions work. Do not guess additional device fields or repeatedly send
production registration requests. `P24_DEVICE_PARAMETERS` is reserved for fields
confirmed by the company, not speculative substitutions.

A user-owned existing session can be connected by the project's session-import
facility; this does not establish that all services or financial flows work.

## Transport

Base URL:

```text
https://core.pishkhan24.ayanco.com/webservices/
```

There are three endpoint groups, all using POST JSON:

- `core.svc/`: account, configuration, invoice information and payment helpers.
- `services.svc/`: service actions and invoice registration.
- `public.svc/`: public-data actions such as cryptocurrency prices.

Request envelope:

```json
{
  "Identity": {"Token": "<device-or-account-session>"},
  "Parameters": {"<action-specific-field>": "<value>"}
}
```

Response envelope:

```json
{
  "Status": {
    "Code": "<upstream-code>",
    "Type": "<upstream-type>",
    "Description": "<upstream-description>"
  },
  "Parameters": {}
}
```

The frontend compares `Status.Code` case-insensitively. `G00000` is success and
`G00002` means the session needs authentication or has expired. Actual status
objects can additionally include `IsFromCache` and `Retryable`. Preserve the
upstream code and description. HTTP 200 alone does not mean business success.
The client must not automatically retry POST requests with uncertain effects.

## Registry semantics

Each action records its exact group, endpoint, source URL, source hash, review
date, request properties, relevant public routes and frontend service names.
Action IDs are stable identifiers such as `services_electric_bills_v1`; they are
not upstream URLs. A caller cannot supply an arbitrary URL through this registry.

- `status=source_verified` means the action literal and its request factory were
  found in the public application.
- `schema_completeness=complete` means the complete object used by the reviewed
  frontend call is represented. It is not a server-side validation guarantee.
- `schema_completeness=partial` deliberately allows additional properties. Many
  pages spread a service-specific object into a request; the source wrapper alone
  cannot establish all required fields. Missing fields must not be invented.
- `frontend_service_names` are the exact `Service` values used for invoice
  registration. They are different from public route slugs and endpoint names.
- Outside the three initial journeys and freeway details, some service-name lists
  reflect candidates in a shared module. The caller must choose the appropriate
  observed name; an arbitrary first item is not a verified mapping.
- `service_ids` use public route slugs. Shared endpoint modules are linked to
  route components through observed imports. A service may use several actions.
- `effect=unknown` is intentional when the source does not establish the complete
  side effect. A result-oriented inquiry can still depend on a paid invoice.

There are currently 28 complete source request schemas and 125 partial ones.
This number should be re-evaluated when contracts are updated.

## Account login

Sources:
[`DA2yXIGZ.js`](https://pishkhan24.com/_nuxt/DA2yXIGZ.js),
[`Br7W_My-.js`](https://pishkhan24.com/_nuxt/Br7W_My-.js), and
[`CblpC8Gx.js`](https://pishkhan24.com/_nuxt/CblpC8Gx.js).

### Request and verify OTP

Both steps use `core.svc/v1/LoginByOTP` in the same device session:

```json
{"Username": "<phone-number>", "OTPCode": null}
```

The request response exposes `Parameters.OTP.Message`, `.Length` and `.Timer`.
Do not hardcode a production OTP length or timer. Verification sends:

```json
{"Username": "<phone-number>", "OTPCode": "<entered-otp>"}
```

After success, the frontend marks its existing device session as authenticated;
it does not replace the token in the observed login code. A response containing a
new session should still be handled by a future contract update.

### Password login

`core.svc/v1/LoginByUserCredential` accepts `Username` and `Password`. The website
transforms the entered password to a **lowercase SHA-1 hex digest** before sending
it. Its exact text handling replaces CRLF with LF and encodes UTF-16 code units
through its legacy UTF-8 routine. The provider's `password_digest` matches this
wire transformation, including non-BMP characters. This is an upstream protocol
requirement, not a recommended password-storage algorithm.

A raw action call must follow the action's wire schema. The friendly password
login tool performs the transform. Other downstream services can have their own
password fields; they must not all receive this transform automatically.

The reviewed logout helper clears local account state and cookies. No dedicated
`Logout` endpoint was found. Account session-list and termination endpoints do
exist; their exact request fields must follow the observed or internal contract.

## Common inquiry and invoice workflow

Sources:
[`CdW2m7yj.js`](https://pishkhan24.com/_nuxt/CdW2m7yj.js),
[`B6kB3dDH.js`](https://pishkhan24.com/_nuxt/B6kB3dDH.js), and
[`BjhR_IcI.js`](https://pishkhan24.com/_nuxt/BjhR_IcI.js).

1. Ensure the user's account session is available.
2. Call `core.svc/v1/ConfigService` with `{"Service":"<frontend-service-name>"}`.
   A returned `Message` may require a user-visible acknowledgement.
3. Register the inquiry through `services.svc/v1/InvoiceRegister`:

   ```json
   {
     "Service": "<frontend-service-name>",
     "Parameters": "<JSON-encoded service input object>"
   }
   ```

   The inner `Parameters` is a **JSON string**. The outer transport envelope's
   `Parameters` remains an object.
4. Inspect the returned state. The frontend evaluates an additional service step,
   an OTP prerequisite, a summary/terms preview and payment channels in that order
   before fetching the result. Important fields include `Invoice.PurchaseKey`,
   `Invoice.Amount`, `Invoice.Service.Summary`, `Prerequisites`,
   `TermsAndConditions`, `PaymentChannels` and `Credit`.
5. If `Prerequisites.Type` is `otp`, its `Value` is JSON containing OTP information.
   Preserve this response even if a purchase key is not yet available. Re-register
   the invoice with the original input plus `OTPCode`, or the endpoint-specific
   OTP field. Do not replace a required upstream OTP with a local boolean.
6. When a cost must be paid, complete the selected payment-channel flow.
7. Call the service result endpoint using the purchased inquiry's key and its
   exact endpoint request fields.
8. Reload `core.svc/v1/InvoiceInfo` with `{"PurchaseKey":"..."}` when resuming an
   existing invoice or inspecting status.

The frontend may store service input in `Query.Parameters` as `Key`/`Value` pairs.
The `InvoiceRegister` input and final result-endpoint input are **not always the
same schema**. Some endpoints need only a purchase key; others need subject fields,
service OTP, tracking IDs or another step. The generic registry exposes partial
contracts so an unsupported combination is visible rather than silently guessed.

### Verified initial mappings

| Journey | Invoice `Service` | Invoice input | Result endpoint and input |
| --- | --- | --- | --- |
| Electricity | `v1_InquiryElectricBills` | `Identifier` | `services/v1/ElectricBills`: `Identifier`, `PurchaseKey` |
| Parcel tracking | `v1_InquiryPostPackagesStatus` | `TrackingCode` | `services/v1/PostPackagesStatus`: `TrackingCode`, `PurchaseKey` |
| Freeway summary | `v1_InquiryFreewayTollBills` | `PlateNumber`, optional `OTPCode` | `services/v1/FreewayTollBills`: same fields plus `PurchaseKey` |
| Freeway detail | `v1_InquiryFreewayTollBillsDetailed` | `PlateNumber`, `NationalCode`, `MobileNumber`, `OTPCode` when requested | `services/v1/FreewayTollBillsDetailed`: same fields plus `PurchaseKey` |

Sources:
[`BjfIHXfS.js`](https://pishkhan24.com/_nuxt/BjfIHXfS.js),
[`CuOALLyJ.js`](https://pishkhan24.com/_nuxt/CuOALLyJ.js),
[`CJFYnG-v.js`](https://pishkhan24.com/_nuxt/CJFYnG-v.js).

The website requires login and invoice registration even for its freeway summary
flow. Do not skip these because the marketing page describes the inquiry as free.

## Payment and wallet

Sources:
[`H6vUcZy-.js`](https://pishkhan24.com/_nuxt/H6vUcZy-.js),
[`C_bn9mgn.js`](https://pishkhan24.com/_nuxt/C_bn9mgn.js),
[`DRvY4pBc.js`](https://pishkhan24.com/_nuxt/DRvY4pBc.js).

- `core/v1/InvoicePayment`: `Callback`, `Gateway`, `PurchaseKey`, `UseCredit`.
- `core/v1/BillsPayment`: `Callback`, `Gateway`, `Bills` (the bill unique IDs).
- Responses can provide `PaymentKey` and `RedirectLink`.
- For a selected gateway whose name starts with `wallet`, the frontend next calls
  `core/v1/WalletPayment` with `PaymentKey`.
- `core/v1/InvoiceDiscounts` receives `PurchaseKey`, `Final` and `VoucherCode`.
- `core/v1/UserWallets` discovers wallets. The selected wallet name must come from
  the response, rather than a guessed constant.
- `core/v1/UserWalletBalance` receives `Wallet`, `CreditBalance`.
- `core/v1/UserWalletChargeChannels` receives `Wallet`.
- `core/v1/UserWalletCharge` receives `Wallet`, `Gateway`, `Amount`, `Callback`.

A callback URL in the website includes the purchase key and a `#status#` template
placeholder. Configure an application-owned callback compatible with the internal
contract. A browser query such as `status=paid` is not independent payment proof.
The project must inspect the authoritative upstream result and retain unknown
states after transport failures. No backend idempotency contract was found in the
public source; local deduplication cannot guarantee that the upstream system did
not already execute an uncertain request.

The invoice amount formatter defaults to **ریال (IRR)** and adds digit separators
without dividing by ten. Source:
[`Du_ngInV.js`](https://pishkhan24.com/_nuxt/Du_ngInV.js).
Actual fees, wallet choices and gateway choices must come from current responses.

## Completing live acceptance

Before marking a journey `live_verified`, record a successful test using a
company-approved account or sandbox, including bootstrap/session handling,
service configuration, OTP branch if present, cost quote, selected payment path,
result and recovery after interruption. Keep account values and credentials out
of fixtures. Until then, the repository's demo mode is an executable simulation
and the live connector is a source-derived integration awaiting acceptance.
