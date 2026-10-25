# Environment variables added in P3 (jobs, providers, storage)

Secrets are marked S: put them in the cPanel Python App screen or `.env` (chmod 600), never in git. Other variables (SECRET_KEY, DATABASE_URL, NID_KEY, ...) are in `backend/.env.example` and docs/CPANEL_DEPLOY.md.

| Variable | Default | Needed when | Meaning |
|---|---|---|---|
| `JOBS_ENABLED` | 0 | VPS only | 1 = run the scheduler loop inside the API. On cPanel leave 0 and use cron |
| `JOBS_TICK_SECONDS` | 30 | in-process loop | how often it looks for due jobs |
| `JOBS_RUN_RETENTION_DAYS` | 90 | | job history kept |
| `OUTBOX_RETENTION_DAYS` / `OUTBOX_CAMPAIGN_RETENTION_DAYS` | 180 / 730 | | outbox cleanup |
| `APP_URL` | http://localhost:3000 | always in production | public web address, used in emails and the payment result redirects |
| `API_PUBLIC_URL` | APP_URL | online payments | public HTTPS origin of the API for vendor callbacks |
| `SMS_PROVIDER` | sandbox | | sandbox, bulksmsbd, http, sslwireless, greenweb, alphasms, mimsms |
| `BULKSMSBD_API_KEY` S | | bulksmsbd | |
| `BULKSMSBD_SENDER_ID` | | bulksmsbd | approved sender id |
| `BULKSMSBD_BASE_URL` | http://bulksmsbd.net/api | | |
| `SMS_PROVIDER_LOW_BALANCE` | 500 | | provider balance alert level |
| `SMS_BILL_BY_SEGMENT`, `SMS_CREDITS_PER_SEGMENT`, `SMS_GSM_SINGLE/MULTI`, `SMS_UNICODE_SINGLE/MULTI` | 1, 1, 160/153, 70/67 | | credit maths |
| `SMS_TIMEOUT`, `SMS_RETRIES`, `SMS_MSISDN_FORMAT` | 10, 2, intl | | |
| `SMS_API_KEY` S, `SMS_SENDER_ID`, `SMS_HTTP_*` | | generic/preset gateway | see docs/SMS_SETUP.md |
| `SMS_DLR_SECRET` S or `SMS_DLR_TOKEN` S | | delivery reports | webhook auth |
| `SMS_DLR_REF_FIELD`, `SMS_DLR_STATUS_FIELD`, `SMS_DLR_DETAIL_FIELD`, `SMS_DLR_DELIVERED`, `SMS_DLR_FAILED`, `SMS_REFUND_UNDELIVERED` | ref, status, reason, lists, 1 | delivery reports | |
| `MAIL_PROVIDER` | sandbox | | sandbox, smtp, ses |
| `MAIL_SMTP_HOST`, `MAIL_SMTP_PORT`, `MAIL_SMTP_SECURITY`, `MAIL_SMTP_USER`, `MAIL_SMTP_PASSWORD` S | , 587, starttls | smtp / ses | |
| `MAIL_FROM`, `MAIL_REPLY_TO`, `MAIL_SMTP_TIMEOUT`, `MAIL_SMTP_RETRIES` | , , 15, 2 | smtp / ses | |
| `SES_REGION`, `SES_CONFIGURATION_SET`, `SES_SNS_TOPIC_ARN`, `SES_WEBHOOK_VERIFY` | , , , 1 | ses | |
| `BKASH_MODE` | off | | off, sandbox, live |
| `BKASH_APP_KEY` S, `BKASH_APP_SECRET` S, `BKASH_USERNAME` S, `BKASH_PASSWORD` S, `BKASH_BASE_URL`, `BKASH_TIMEOUT` | | bkash | |
| `SSLCOMMERZ_MODE` | off | | off, sandbox, live |
| `SSLCOMMERZ_STORE_ID` S, `SSLCOMMERZ_STORE_PASSWORD` S, `SSLCOMMERZ_KEYS`, `SSLCOMMERZ_TIMEOUT` | , , card, 20 | sslcommerz | |
| `STORAGE_BACKEND` | local | | local or s3 |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID` S, `S3_SECRET_ACCESS_KEY` S, `S3_PREFIX`, `S3_SSE`, `S3_SSE_KMS_KEY_ID`, `S3_ADDRESSING`, `STORAGE_DOWNLOAD`, `S3_URL_TTL` | | s3 | see docs/STORAGE.md |

## What the owner must supply
BulkSMSBD API key, approved sender id and the vendor documentation; bKash merchant app key/secret/username/password (sandbox first); SSLCommerz store id and password (sandbox first); an SMTP mailbox or SES account with a verified domain and DNS access; an S3/R2 bucket and keys (optional); a public HTTPS domain for callbacks.

## Security settings (P2, see SECURITY.md)
| Variable | Default | Needed when | What it does |
|---|---|---|---|
| `ACCESS_TOKEN_MINUTES` | 30 | | life of the bearer token; the web app refreshes it silently |
| `REFRESH_TOKEN_DAYS` | 30 | | life of the rotating refresh token (idle sessions end after this) |
| `REFRESH_COOKIE` | 1 | | 0 = do not set the HttpOnly `fw_refresh` cookie (API clients then keep the refresh token themselves) |
| `RESET_TOKEN_MINUTES` / `VERIFY_TOKEN_HOURS` | 30 / 48 | | life of password-reset and e-mail confirmation links |
| `TRUSTED_PROXIES` | empty | behind any proxy | comma separated IPs/CIDRs whose `X-Forwarded-For` is believed. **Set it in production**, or all visitors share one rate-limit bucket |
| `MAX_BODY_BYTES` | 2097152 | | largest JSON/form body; uploads allow `MAX_UPLOAD_BYTES` + 1 MB |
| `REQUIRE_EMAIL_VERIFICATION` | 1 in production, else 0 | | sign-ups must confirm their email before signing in; the 30 day trial starts then |
| `ANTISPAM_STRICT` | 1 in production, else 0 | | public forms need the signed form token (3 s minimum fill time) |
| `SANDBOX_PAYMENTS` | 1 only when `DEMO=1`, always 0 in production | | the practice payment provider (a payer can sign their own "success") |
| `RATE_LIMITS` | 1 | | 0 switches every rate limit and lockout off (tests only) |
| `ALLOWED_HOSTS` | empty | optional | comma separated Host header allow-list |
| `CORS_ORIGINS` | empty | web on another origin | exact origins; never `*` (production refuses it) |
| `CSP_REPORT_ONLY` (web) | 0 | first CSP rollout | 1 = the web app's Content-Security-Policy only reports |
