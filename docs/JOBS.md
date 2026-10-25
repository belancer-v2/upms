# Background jobs

Small DB-locked job runner in `backend/app/jobs/` (no Celery, no Redis). Three ways to run it, all safe together because every job takes a row in `job_locks` first and re-checks that it is still due after getting the lock.

| How | Command / setting | Use when |
|---|---|---|
| cPanel cron (primary) | `python -m app.jobs.cli run-due` every minute (or `*/5`) | shared hosting, no long-running worker. Exact cron line and `.env` notes: **docs/CPANEL_DEPLOY.md section 7** |
| One job by hand | `python -m app.jobs.cli run <name>` ; `python -m app.jobs.cli list` | testing, a missed run |
| In-process loop | `JOBS_ENABLED=1` (default **off**), `JOBS_TICK_SECONDS=30` | VPS where the API stays up |
| Console | SaaS console, Background jobs (`/app/saas/jobs`), SUPER_ADMIN and SAAS_ADMIN | see last runs, run now, failures, alerts |

CLI output: one JSON line per job (`ts, name, status, result, error`). Exit code 0 = everything that ran was ok or warn, 1 = a job failed, 2 = usage error.
Interval jobs run at the granularity of the cron (a 5-minute job on a 5-minute cron runs every 5 minutes; with a 1-minute cron it still waits its own interval). Daily jobs use **Dhaka time** and run on the first tick after their time; a failed daily job is retried after 30 minutes, up to 3 attempts.

## The jobs
| Name | Schedule | What it does | Idempotency |
|---|---|---|---|
| `campaigns_run_due` | every 5 min | start scheduled email campaigns, continue throttled ones | outbox rows per campaign |
| `gateway_sweep` | every 10 min | mark unfinished online-payment sessions and credit purchases `expired` | status-guarded UPDATE |
| `amenities_expire` | hourly | free slots of unpaid approvals and past requests | status change |
| `sms_provider_balance` | every 6 h | read the SMS provider's own balance (BulkSMSBD `getBalanceApi`), alert below `SMS_PROVIDER_LOW_BALANCE` (500) | one alert per day |
| `saas_invoices` | daily 00:30 | FlatWise subscription invoices for the current month, then `invoice_issued` email to building admins | one invoice per org and period; mail mark per invoice |
| `credit_grants` | daily 00:45 | plan-included monthly SMS and email credits | ledger reason `Monthly allowance YYYY-MM` is checked first |
| `gateway_reconcile` | daily 02:00 | yesterday's `created`/`failed` sessions: ask bKash/SSLCommerz, settle if paid (amount must match), expire abandoned ones, alert on mismatch or errors | `settle_paid` pays a session once |
| `cleanup` | daily 03:00 | expired locks, job history (90 d), job marks, OTP code hashes, expired sign-in tokens/sessions/rate limits, old outbox rows (`OUTBOX_RETENTION_DAYS` 180 for non-campaign and test mail, `OUTBOX_CAMPAIGN_RETENTION_DAYS` 730) | deletes by age |
| `integrity_check` | daily 03:30 | every journal entry balanced, ledger debit = credit per building, invoice `paid` = sum of verified payments, paid gateway sessions have a verified payment. Problems write a `system_alerts` row (kind `integrity`) and the run shows **warn** | one alert per day |
| `billing_auto` | daily 06:00 | monthly service-charge invoices for buildings that **opted in** (Billing automation: on, day of month, due day). Default **off** | job mark per building and month; invoices are skipped if they exist |
| `trial_ending` | daily 08:00 | emails at 7, 3 and 1 days (templates `trial_7`, `trial_3`, `trial_1`); a missed day sends the next smaller notice once | mark per subscription, bucket, end date |
| `reminders_run` | daily 09:00 | dues reminders (SMS) for every building whose plan has `reminders` | message idempotency key `inv<id>:<step>` |
| `low_credit_alerts` | daily 09:30 | SMS/email credits below the building's threshold: email its admins once a day and write an info alert | mark per org, kind, day |
| `saas_dunning` | daily 10:00 | overdue FlatWise invoices: day 1 sets the subscription `past_due` and emails; 7 and 14 remind; 30 raises an error alert for a person (it never suspends by itself) | mark per invoice and step |

Building opt-in for automatic billing: `GET/PUT /api/billing/automation` (`auto_billing`, `bill_day` 1-28, `due_day` 1-28), roles Property admin, Agency manager, Treasurer, plan feature `billing`.

Missing mail templates (`credits_low_email`, `invoice_overdue`, ...) are created automatically the first time they are needed.

## Alerts
`system_alerts` rows are shown on the jobs page with a "Mark resolved" button. Kinds: `integrity`, `payment_stuck`, `dunning`, `job_failed`, `low_credit`, `provider_balance`.

## Tests
`backend/tests/test_p3_jobs.py` calls each job function with `at` injected and checks it runs twice without doing the work twice; the runner tests cover locking, takeover of an expired lock, failure handling, retry timing and the CLI exit codes.
