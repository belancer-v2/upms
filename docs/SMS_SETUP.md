# SMS setup

`backend/app/services/sms.py`. Choose with `SMS_PROVIDER`:

| Value | What |
|---|---|
| `sandbox` (default) | nothing is sent; messages count as sent. Demo and tests |
| `bulksmsbd` | **BulkSMSBD**, the first-class adapter |
| `http` | generic HTTP gateway described only by env vars |
| `sslwireless`, `greenweb`, `alphasms`, `mimsms` | presets of the generic adapter. **Written from memory, never run against the vendor.** They need your credentials and a check against the vendor documentation |

## BulkSMSBD
```
SMS_PROVIDER=bulksmsbd
BULKSMSBD_API_KEY=...            # from your BulkSMSBD dashboard (secret)
BULKSMSBD_SENDER_ID=...          # an approved sender id / mask
BULKSMSBD_BASE_URL=http://bulksmsbd.net/api     # default, change only if the vendor tells you
SMS_PROVIDER_LOW_BALANCE=500     # alert threshold for the provider balance job
```
Calls the adapter makes (all **to be verified against the vendor docs the owner will share**):
* single: `POST {base}/smsapi` form `api_key, type (text|unicode), number (8801XXXXXXXXX), senderid, message`
* bulk: `POST {base}/smsapimany` JSON `{api_key, senderid, messages:[{to, message}]}`, sent in chunks of 100
* balance: `GET {base}/getBalanceApi?api_key=`
* `type=unicode` is chosen automatically when the text has any non-GSM character (all Bangla text).
* Numbers are normalised to `8801XXXXXXXXX` (`017...`, `+88017...`, `88017...` all accepted; anything else is refused before calling the provider).
* Response codes the adapter understands (best recollection, **verify**): 202 success; 1001 invalid number; 1002 sender id not correct; 1003 required fields missing; 1005 internal error (the only one treated as retryable); 1006 balance validity not available; 1007 balance insufficient; 1011 user id not found; 1012 masking SMS must be sent in Bengali; 1013 sender id not found; 1014 sender type name not found; 1015 no valid sender id; 1016 sender type name active; 1017 sender type name not active; 1018 account disabled; 1019 sender type price disabled; 1020 parent account not found; 1021 parent active price; 1031 account not verified; 1032 IP not whitelisted. An unknown code is reported as `Provider answered <code>`.
* The adapter returns no per-message id, so our idempotency key (`Message.idem_key`) is stored as `provider_ref`.

**cPanel note (code 1032):** if BulkSMSBD requires IP whitelisting, give them the server's outbound IP. On shared hosting that IP can change; ask the host for a dedicated IP.

### Verify with vendor docs (checklist before go-live)
- [ ] base URL and whether HTTPS is available (the default is plain http: use https if offered)
- [ ] `smsapi` parameter names and that `type=unicode` is the right value for Bangla
- [ ] `smsapimany` JSON shape (`messages[].to` / `message`) and maximum batch size
- [ ] balance endpoint name and answer shape
- [ ] every response code in the table above, and any code not listed
- [ ] sender id rules (masking must be Bengali, 1012) and approval status
- [ ] IP whitelisting, rate limits, whether a delivery report is offered (if yes, see below)
- [ ] send one real SMS to the owner's phone in English and one in Bangla, and check the count of credits used at BulkSMSBD against `segments` below
- [ ] cost per segment, to price the FlatWise packs

## Segments and credits
A message is split into segments: GSM-7 text 160 characters (153 per part when joined), Bangla/Unicode 70 (67 per part). One FlatWise SMS credit is charged **per segment**, after the provider accepted the message (a refused message costs nothing). Each sent SMS stores `segments`, `encoding`, `credits` in `sms_dispatch`. Tunables:

| Env | Default | Meaning |
|---|---|---|
| `SMS_BILL_BY_SEGMENT` | 1 | 0 = one credit per message whatever its length |
| `SMS_CREDITS_PER_SEGMENT` | 1 | multiplier |
| `SMS_GSM_SINGLE` / `SMS_GSM_MULTI` | 160 / 153 | |
| `SMS_UNICODE_SINGLE` / `SMS_UNICODE_MULTI` | 70 / 67 | |
| `SMS_TIMEOUT`, `SMS_RETRIES` | 10 s, 2 | exponential backoff on connection errors and 5xx. A read timeout is **not** retried (the message may already be sent) |
| `SMS_MSISDN_FORMAT` | intl | generic adapter only: `intl` 8801..., `local` 01..., `plus` +8801... |

## Delivery reports (optional)
`POST /api/webhooks/sms/<provider>` (public HTTPS URL, e.g. `https://flat.example.com/api/webhooks/sms/bulksmsbd`). Authenticate with **either** header `X-Signature: <hex HMAC-SHA256 of the raw body with SMS_DLR_SECRET>` **or** `?token=<SMS_DLR_TOKEN>`; with neither configured the endpoint answers 503. Body JSON or form with `ref` (our `provider_ref` or idempotency key) and `status`; field names via `SMS_DLR_REF_FIELD`, `SMS_DLR_STATUS_FIELD`, `SMS_DLR_DETAIL_FIELD`, values via `SMS_DLR_DELIVERED` / `SMS_DLR_FAILED` (comma lists). Undelivered: `Message.status` becomes `failed` and the credits are refunded once (`SMS_REFUND_UNDELIVERED=0` to disable). To my recollection BulkSMSBD does not push reports: confirm with the vendor.

## Generic gateway (`SMS_PROVIDER=http`)
`SMS_HTTP_URL` (placeholders `{to} {text} {ref} {sender} {api_key}`), `SMS_HTTP_METHOD`, `SMS_HTTP_FORMAT=query|form|json`, `SMS_HTTP_PARAMS` (JSON with the same placeholders), `SMS_HTTP_AUTH_HEADER` (`Authorization: Bearer {api_key}`), `SMS_API_KEY`, `SMS_SENDER_ID`, success test `SMS_HTTP_SUCCESS_JSON` (`status=SUCCESS`) or `SMS_HTTP_SUCCESS_REGEX`, id `SMS_HTTP_ID_PATH` (dotted path). Secrets are never logged.
