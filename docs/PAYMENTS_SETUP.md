# Online payments setup (bKash tokenized checkout, SSLCommerz)

## Status: what is proven and what is not
| Part | Status |
|---|---|
| Built-in simulator (default, `*_MODE=off`) | tested end to end, no network |
| bKash adapter (`services/gateway_bkash.py`) | **verified against mocks only** (`httpx.MockTransport`, example payloads written from memory of the vendor docs) |
| SSLCommerz adapter (`services/gateway_sslcommerz.py`) | **verified against mocks only** |
| Our own guarantees (server-side verification, amount check, one payment per session, replay safety, reconciliation) | tested for both adapters |

**Every vendor URL, header, field name, status value and response code below is "to be verified" against the owner's merchant credentials and the vendor's current documentation in the vendor SANDBOX.** Do not set `*_MODE=live` before the certification checklist at the end passes.

## Public URLs (cPanel reality)
Both vendors call back to your site, so these must be **public HTTPS** URLs on the API host (`API_PUBLIC_URL`, e.g. `https://flat.example.com`; if the web app proxies `/api`, it is the same origin as `APP_URL`):

| Purpose | URL | Method | Who calls it |
|---|---|---|---|
| Customer returns (bKash) | `{API_PUBLIC_URL}/api/gateway/return/<session token>` | GET | bKash redirects the browser here (`paymentID`, `status`). It is passed as `callbackURL` when the payment is created |
| Customer returns (SSLCommerz) | `{API_PUBLIC_URL}/api/gateway/return/<token>?r=success\|fail\|cancel` | POST (form) | SSLCommerz posts the browser to `success_url`, `fail_url`, `cancel_url`; sent in the init call |
| IPN (SSLCommerz) | `{API_PUBLIC_URL}/api/gateway/ipn/sslcommerz` | POST (form) | SSLCommerz server to server. Also set it once in the SSLCommerz merchant panel (IPN settings) |
| Result pages the customer sees | `{APP_URL}/pay/return/success`, `/fail`, `/cancel`, `/error` | GET | our API redirects the browser here (HTTP 303) after it checked with the provider |

The IPN and return endpoints need no sign-in. localhost URLs do not work with the vendors: for sandbox testing use a tunnel or a staging host with HTTPS. Whitelist your server's outbound IP at the vendor if they ask.

## The rule: the redirect is never trusted
* **bKash**: the return only decides which branch to take. On `status=success` the server calls **execute payment** with the stored `paymentID` (not the one in the URL; a different one is refused), then **query payment** as an independent second confirmation: `transactionStatus=Completed`, same `trxID`, and `amount` equal to what we charged. Any other outcome leaves the invoice unpaid.
* **SSLCommerz**: the return carries `val_id`. The server calls the **validation API** (`val_id` + `store_id` + `store_passwd`) and requires `status` VALID/VALIDATED, `tran_id` equal to our session token, currency BDT, `risk_level` 0 and `amount` equal to what we charged. The IPN additionally requires a correct `verify_sign` hash (md5 over the fields in `verify_key` sorted by name plus md5 of the store password) before the validation call.
* Amounts are integer paisa internally, converted to `"123.45"` strings at the edge, and compared as integers.
* One payment per session (`gateway_sessions.idem_key`): replayed returns, double IPNs and the reconciliation job all end in the same single verified payment, and the same ledger entry as a cashier payment.
* If the provider confirms money taken but our session expired or failed locally, the payment is still recorded (`confirmed=True`); if the invoice can no longer accept it (void or already paid) a `payment_stuck` alert asks a person to refund.
* Provider outages: the customer sees the "still checking" page, the session stays open, and the nightly `gateway_reconcile` job re-queries yesterday's `created` and `failed` sessions.

## bKash
```
BKASH_MODE=sandbox            # off (simulator) | sandbox | live
BKASH_APP_KEY=...  BKASH_APP_SECRET=...  BKASH_USERNAME=...  BKASH_PASSWORD=...     # from the bKash merchant onboarding
BKASH_BASE_URL=               # optional override
API_PUBLIC_URL=https://flat.example.com
```
Base URLs used (to verify): sandbox `https://tokenized.sandbox.bka.sh/v1.2.0-beta`, live `https://tokenized.pay.bka.sh/v1.2.0-beta`. Calls (to verify): `POST /tokenized/checkout/token/grant` (headers `username`, `password`; body `app_key`, `app_secret`; answer `id_token`, `expires_in`; cached until near expiry), `POST /tokenized/checkout/create` (headers `Authorization: <id_token>`, `X-APP-Key`; body `mode 0011, payerReference, callbackURL, amount, currency BDT, intent sale, merchantInvoiceNumber`; answer `statusCode 0000, paymentID, bkashURL`), `POST /tokenized/checkout/execute` `{paymentID}` (answer `trxID, transactionStatus, amount`), `POST /tokenized/checkout/payment/status` `{paymentID}`. The method key `bkash` uses it.

## SSLCommerz
```
SSLCOMMERZ_MODE=sandbox       # off | sandbox | live
SSLCOMMERZ_STORE_ID=...  SSLCOMMERZ_STORE_PASSWORD=...
SSLCOMMERZ_KEYS=card          # which of our method keys go through SSLCommerz (card, or "card,nagad")
```
Hosts (to verify): sandbox `https://sandbox.sslcommerz.com`, live `https://securepay.sslcommerz.com`. Calls (to verify): `POST /gwprocess/v4/api.php` (form: `store_id, store_passwd, total_amount, currency, tran_id, success_url, fail_url, cancel_url, ipn_url, cus_*, shipping_method, product_*`; answer `status SUCCESS, GatewayPageURL, sessionkey`), `GET /validator/api/validationserverAPI.php?val_id&store_id&store_passwd&format=json`, `GET /validator/api/merchantTransIDvalidationAPI.php?tran_id&...` (reconciliation).

## Fees and plans
Per-building fee mode and basis points, the `gateway` plan feature and the enabled methods are unchanged (Payments settings). The building admin enables the methods; the platform operator owns the merchant credentials (env). Per-building merchant accounts would need the encrypted `credentials_enc` field wired in: not done.

## Certification checklist (vendor sandbox, before live)
- [ ] grant token works; token expiry value matches `expires_in`
- [ ] create returns `bkashURL`; the bKash sandbox wallet pays; browser lands on `/api/gateway/return/<token>`
- [ ] execute then query return `Completed` with matching `trxID` and `amount` (check the string format of `amount`)
- [ ] cancel and failure branches and the exact `status` values in the return URL (`success|failure|cancel`)
- [ ] replaying the return URL does not create a second payment
- [ ] SSLCommerz init returns `GatewayPageURL`; success/fail/cancel are POSTed to the URLs (check the `?r=` query survives)
- [ ] validation answer fields: `status`, `tran_id`, `val_id`, `amount`, `currency_type` vs `currency`, `bank_tran_id`, `risk_level`
- [ ] IPN hash: `verify_key` / `verify_sign` algorithm matches `verify_ipn_hash`
- [ ] IPN reaches the server over HTTPS and answers 200
- [ ] the query API format used by reconciliation (`element[]`)
- [ ] amounts with paisa (e.g. 1234.56) and the fee-on-payer case
- [ ] a payment made but the browser closed: appears after the IPN / the reconcile job
- [ ] refunds: not implemented (handled by hand at the vendor; the `payment_stuck` alert lists cases)

SMS/email credit purchases (M19) still use the built-in simulator or manual transfer; they do not go through these adapters yet.
