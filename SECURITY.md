# FlatWise security

Last reviewed: 2026-10-25 (hardening pass P2). Owner of this document: the FlatWise security contact below.

## Reporting a vulnerability (responsible disclosure)

Email **security@REPLACE-WITH-YOUR-DOMAIN** (placeholder: the owner must create this mailbox before launch and publish it at `/.well-known/security.txt`).
Please include what you found, how to reproduce it, and the building or account it affected. Do not read or change other people's data beyond what is needed to show the problem.
We acknowledge within 2 working days, give a first assessment within 7 days, and tell you when it is fixed. Good-faith reports are not pursued legally.

## What we protect and from whom (threat model summary)

FlatWise holds the money records, identity documents and contact details of people who live in or run residential buildings in Bangladesh. Many unrelated buildings share one installation.

| Threat | Example | Main defences |
|---|---|---|
| Another customer reads or changes my building | a resident of building B guesses `/api/billing/invoices/581` | every building route resolves the building from `X-Property-Id` and the caller's own memberships (`deps.property_ctx`); every object is re-checked against that building; `tests/test_authz.py` sweeps all routes |
| A resident sees what only managers should | tenant opens the staff vault or payroll | role sets in `app/permissions.py` and per router; `docs/PERMISSIONS.md` is generated from the running API |
| Account takeover by guessing | password spraying, credential stuffing | per account, per account+address and per address lockouts with doubling delay; one neutral error; bcrypt on every attempt, including unknown accounts; password policy and common-password list |
| Account takeover by theft | stolen laptop, copied token | 30 minute access tokens, rotating refresh tokens with theft detection, "Signed-in devices" list, revoke on password change and role removal |
| Phishing and link abuse | forged unsubscribe or payment links | signed (HMAC) links; payment results confirmed server to server; single-use hashed reset tokens that expire in 30 minutes |
| Free money / free credits | calling the practice payment provider as a payer | practice provider endpoints and signatures are disabled unless `SANDBOX_PAYMENTS=1` (never in production) |
| Bots and abuse of public forms | fake sign-ups, lead spam, link scanning | rate limits stored in the database, honeypot field, signed form token with a minimum fill time, optional e-mail confirmation before the trial starts |
| Upload attacks | a script saved as `photo.png`, `../../` file names | magic-byte check of every upload, size caps, random storage names, display names sanitised, downloads sent as attachments with `nosniff` and a `sandbox` CSP |
| Tampering by an insider or intruder | editing the audit log to hide a refund | audit log is append-only in the application and hash-chained; `GET /api/audit/verify` and `python -m app.auditchain verify` find the first changed row |
| Browser attacks (XSS, clickjacking, CSRF) | injected script, hidden frame | nonce-based CSP on pages, strict CSP on the API, `frame-ancestors 'none'`, bearer tokens (no ambient cookie authority); the one cookie is HttpOnly, SameSite=Lax and needs a custom header |

Out of scope for this release: a malicious host administrator with root on the server, compromise of the mail or SMS provider, denial of service at network level (use the hosting provider's protection).

## Authentication and sessions

- Login: `POST /api/auth/login` returns `token` (access token, 30 minutes, `ACCESS_TOKEN_MINUTES`), `refresh_token`, `expires_in`, `must_change_password` and the usual profile payload. Wrong email and wrong password give the same 401; a locked key gives the same 429 for real and invented accounts.
- Lockouts (table `rate_limits`, shared by all workers): 10 failures per account, 5 per account+address, 20 per address inside 15 minutes lock that key for 30 s, then 1 min, 2 min ... up to 30 min. Lockouts and failures are written to the audit log (`auth.lockout`, `auth.login_failed`). A successful login clears the account and account+address counters.
- Refresh: `POST /api/auth/refresh`. The refresh token is random (256 bit), stored only as a SHA-256 hash, and replaced on every use. Showing an already-replaced token outside a 20 second grace window (two tabs racing) revokes the whole session (`auth.refresh_reuse`).
- Access tokens carry `sid` (session) and `tv` (user token version). They stop working when the session is revoked, the user is deactivated, or `token_version` changes (password change/reset, role removal, SaaS role change).
- Sessions: `GET /api/me/sessions`, `DELETE /api/me/sessions/{id}`, `POST /api/me/sessions/revoke-all` (shown in My profile).
- Passwords: 8 to 72 bytes, not on the common list, not equal to the email, name or phone, not a plain run or repeated character. Enforced on signup, change, reset and SaaS staff creation. `POST /api/auth/change-password` needs the current password and signs other devices out.
- Reset: `POST /api/auth/forgot-password` (email or phone, same answer always; 3 per hour per account, 8 per hour per address) sends a single-use link valid 30 minutes through the mail provider or SMS credit. The token is stored hashed; the copy recorded in `mail_outbox` / `messages` has it replaced by `[removed]`. The token sits in the URL fragment (`#token=`) so it is not sent to servers or in Referer headers.
- Temporary passwords (created for residents, committee members and SaaS staff) set `must_change_password`. Until it is changed every endpoint except `/api/me`, change-password, sessions and logout answers 403 with `X-Error-Code: password_change_required`, and the web app sends the person to `/change-password`.
- E-mail confirmation: with `REQUIRE_EMAIL_VERIFICATION=1` (default in production) a sign-up cannot sign in, and its 30 day trial does not start, until the emailed link is used. A repeated sign-up with a registered address looks identical to a new one (no account enumeration).

## CSRF

The API authenticates with an `Authorization: Bearer` header that scripts add explicitly; browsers never attach it on their own, so classic CSRF does not apply to those endpoints. The only cookie is `fw_refresh` (HttpOnly, SameSite=Lax, `Secure` in production, path `/api/auth`). It is honoured only on `POST /api/auth/refresh` and `/api/auth/logout`, and `refresh` additionally requires the header `X-Requested-With: fetch`, which a cross-site page cannot send without a CORS pre-flight that the allow-list refuses. CORS uses an explicit origin list (`CORS_ORIGINS`) and never allows credentials.

## Browser and HTTP hardening

- API responses: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (camera, microphone, geolocation, payment off), `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; sandbox`, `Cross-Origin-Resource-Policy: same-origin`, `Cache-Control: no-store`, HSTS when `ENV=production`, no `Server` header (`secure.py`).
- Web pages (Next.js): headers in `next.config.mjs`; the CSP is built per request in `src/middleware.ts` with a nonce and `strict-dynamic` (no inline scripts allowed; the theme boot script carries the nonce). Styles allow `'unsafe-inline'` because React renders `style=""` attributes. `CSP_REPORT_ONLY=1` switches to report-only for a first rollout. Pages with secrets in the address (`/n`, `/t`, `/unsubscribe`, `/pay`, `/reset-password`, `/verify-email`) send `Referrer-Policy: no-referrer`.
- Request size: `MAX_BODY_BYTES` (2 MB) for JSON/forms; multipart uploads may be `MAX_UPLOAD_BYTES` (3 MB) + 1 MB. Larger bodies get 413 before they are read.
- Client address behind a proxy: set `TRUSTED_PROXIES` (IPs or CIDRs). Only then is `X-Forwarded-For` believed, read from the right, so a forged left-most entry is ignored. If it is empty in production every visitor shares one rate-limit bucket (the API logs a warning at start-up).
- Validation errors never echo the rejected value (a rejected password would otherwise be sent back).
- Logs: access logs print paths with link tokens replaced by `[redacted]`; SQL bound values are hidden from error text (`hide_parameters`); audit entries hold ids and counts, never tokens, NIDs, OTP codes or passwords (`tests/test_security.py::test_audit_log_never_records_secrets`).

## Uploads and downloads

Accepted: JPG, PNG, PDF. Every upload goes through the magic-byte check (`services/uploads.py`), the size cap, a random storage name and a sanitised display name. Files are served only after the route's own permission check, as `Content-Disposition: attachment` (documents) or as an image (photos) with `nosniff` and the API's `sandbox` CSP, so an uploaded file cannot execute in a browser. Storage keys are validated by `services/storage.py`.

## Data classification, encryption and retention

| Class | Examples | At rest | Who sees it |
|---|---|---|---|
| Restricted | National ID numbers, ID/NID photos, tenancy agreements, gateway credentials, passwords | NID numbers and gateway credentials Fernet-encrypted (`NID_KEY`); passwords bcrypt; reset/refresh/verify tokens SHA-256 only; documents in private storage, never public URLs | named roles only; every NID reveal is logged (`nid_views`) |
| Confidential | phone numbers, emails, addresses, invoices, payments, ledger, payroll, rent records | database (encrypt the disk/volume at the host) | building roles by `permissions.py`; residents see their own flat |
| Internal | audit log, rate-limit counters, job history | database; audit log hash-chained | SaaS admins; building managers see their building's entries |
| Public | plans and prices, website text | n/a | everyone |

Link tokens (tenant form, SMS notice read-link, payment session ids) are random 96 to 192 bit values kept in clear in the database because staff can re-send the same link; they are not credentials for anything but their one record. Rotate by cancelling and re-inviting.

Retention (`services/retention.py`, SaaS console): visitor log 24 months, outbox 12 months, former-resident records 36 months by default; audit log is never purged. Expired `rate_limits` rows are removed opportunistically after 2 days. Account erasure (`services/privacy.py`) blanks the person and revokes sessions while keeping the books balanced.

## Secrets

`SECRET_KEY` (32+ random characters) signs JWTs (through a derived key), mail links and payment callbacks. `NID_KEY` encrypts NIDs and gateway credentials. `ENV=production` refuses to start with defaults (`app/prodcheck.py`). Rotating `SECRET_KEY` signs everyone out and invalidates unsubscribe/tracking links already sent; rotating `NID_KEY` needs `python -m app.rekey_nid`. Secrets live in environment variables, never in the repository or logs.

## Audit log integrity

Rows are written only through `audit()`; the application raises on any UPDATE or DELETE of an audit row and no endpoint modifies it. Each row stores `prev_hash` and `row_hash` (SHA-256 over the previous hash and the row). The `audit_head` row is locked while a row is added, so concurrent workers cannot fork the chain. Check it: `GET /api/audit/verify` (SaaS admins) or `python -m app.auditchain verify` (exit code 1 if broken). Record the printed `head` somewhere outside the database after each check (for example in the ops log): that also catches removal of the newest rows by someone who can edit the database. Run the check daily.

## Incident response

1. **Contain.** Suspected stolen account: in My profile "Sign out of all devices", or as a SaaS admin deactivate the user (`PATCH /api/saas/staff/{id}` for staff). Suspected key leak: rotate `SECRET_KEY` (signs everyone out) and the provider keys (SMS, mail, bKash, SSLCommerz, S3). Suspected database leak: rotate `NID_KEY` with `rekey_nid` and force password resets.
2. **Preserve.** Export the audit log and the access logs (JSON, request ids) before anything is cleaned; run `python -m app.auditchain verify` and keep the output. Take a database snapshot.
3. **Assess.** Use the audit log (`auth.*`, `export.*`, `staff.nid.view`) to list which buildings and people were affected, and for how long.
4. **Fix.** Patch, deploy through the normal pipeline, run the full test suite (it includes the authorization sweep).
5. **Notify.** Tell affected building admins and, where personal data was exposed, the people concerned without undue delay, saying what happened, which data, and what to do (change password, watch for phishing). Inform the regulator if the law that applies requires it. Keep a written record.
6. **Learn.** Add a regression test, update this file, and note the change in the release notes.

## Known limits and open decisions

See "What remains risky" in the P2 report: shared per-address limits behind a proxy, SaaS admins who can act in every building, link tokens stored in clear, the practice payment provider switched off in production, CSP `style-src 'unsafe-inline'`, the Next.js build tooling advisory (PostCSS), and the need for disk encryption and off-site backups at the host.

## Dependency audit

See `docs/DEPENDENCY_AUDIT.md`. Python packages are pinned in `backend/requirements.txt` and audited with `pip-audit`; the web app with `npm audit --omit=dev`.
