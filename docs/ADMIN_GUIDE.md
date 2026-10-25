# Admin guide (FlatWise staff)

For the FlatWise team: how to bring a new building on, manage plans and credits, set up providers, watch the jobs and handle personal-data requests. Day-to-day screens for customers are in the `USER_GUIDE_*.md` files; engineering is in `ARCHITECTURE.md` and `RUNBOOK.md`.

## 1. Who can do what

| Role | Sees in the SaaS console |
|---|---|
| Super admin | everything, including the team, invoice settings, retention, jobs |
| SaaS admin | everything except creating other super admins |
| SaaS finance | invoices, credit sales, reports, buildings (read) |
| SaaS sales | leads, email campaigns, reports, buildings (read) |
| SaaS user (support) | overview, buildings, credit balances, plans (read) |

Keep at least two super admins. Add and remove people under **Team**. Every change is in the activity log.

## 2. Onboarding a new building

**Self-service (normal path).** The customer signs up on `/signup`, which creates the organization, the building, the first PROPERTY_ADMIN sign-in and a 30-day trial on the chosen plan. On first sign in they land on the **setup wizard**:

1. Building details (name in English and Bangla, address, city, floors).
2. Floors and flats: floors, blocks, flats per floor, usual area and bedrooms, and car and bike slots per flat (if the plan has parking). FlatWise names flats `A-101`, `A-102`.
3. Charges: a suggested list for a Bangladeshi building (service charge per sq ft, security, cleaning, lift, generator fuel, water and common electricity, sinking fund) with English and Bangla names. The admin ticks and edits amounts.
4. Due day (1 to 28) and which SMS reminders to send (before, on the day, 7, 15, 30 days late). The due day is also saved as the building's automation due day; automatic billing stays **off** until the admin switches it on.
5. Committee: name, email and role per person. FlatWise creates a sign-in with a temporary password, shown once; the admin passes it on. Each person must choose a new password at first sign in.
6. Review and finish.

Progress is saved per building on the server (`setup_progress`); every step can be skipped; a step whose answer FlatWise already has is shown as "Already set". Until the wizard is finished or hidden, the dashboard shows a checklist card. Buildings created before the wizard existed, and agency buildings that already have flats, never see it.

**What you do as staff**

1. Watch **Leads** and **Buildings**: a new trial appears in Buildings with its plan, flats and trial end.
2. Call the admin on day 1: confirm the setup is finished, that owners and tenants are being added (Flats > Add flats / Import), and that the first month's invoices are generated.
3. Check **SMS and email credits** (Buildings > the building > balances). Plans include a monthly allowance; reminders and OTP codes spend it. Offer a pack if they will send more.
4. Day 20: the `trial_ending` job emails the admin at 7, 3 and 1 days before the end. Offer a call.
5. When they pay, mark the FlatWise invoice paid (SaaS invoices) or let the gateway/transfer flow do it. The subscription becomes active.

**Assisted setup for an agency or a large complex.** Add people from the customer's side only through their own sign-ins. As staff you can open any building (building box at the top) but you should not create residents for them; ask the admin to import a spreadsheet (Flats > Import: number, floor, block, area, bedrooms, owner name, owner phone).

## 3. Plans, prices and features

- **Plans and prices**: three plans (Basic, Standard, Pro) by four size bands (up to 30, 31 to 80, 81 to 200 flats, and 200+ by quote). Each has a monthly price, a one-time setup fee, SMS and email credits included per month, and a feature list. The public pricing page and the signup form read these numbers live from `GET /api/public/plans`. Only super admin and SaaS admin can edit.
- **Per-building changes** (Buildings > the building): change plan, extend the trial, switch one feature on or off (an override survives plan changes), grant SMS credits, suspend or reactivate. Suspending blocks everyone except staff; use it for non-payment or abuse, after notice.
- **Cancellation**: a building admin can ask to cancel from their Plan page; the request appears under cancellations for staff to approve or reject. Whatever the outcome, the customer can export their data.
- **Dunning**: the `saas_dunning` job marks an overdue FlatWise invoice `past_due` and emails at day 1, 7 and 14, and raises an alert at day 30 for a person to decide. It never suspends by itself.
- Prices are in BDT. Yearly billing charges 10 months for 12.

## 4. SMS and email credits

Every SMS (reminder, notice SMS, OTP, payslip, tenant form link) costs one credit per segment; every email costs one email credit. Credits are per building.

- **Packs and prices**: Credit sales > Packs and prices. Price is before VAT; VAT % and the payment details shown to buyers (bKash, Nagad, bank account) are under **VAT and payment details**.
- **Buying**: the building admin buys on SMS and email credits: online (gateway) or by transfer. A transfer arrives under **To check**: compare the amount sent and the transaction id with the invoice, then **Verify and add credits** or **Reject** with a reason.
- **Bonus credits**: Credit sales > Balances > give bonus credits (reason is kept in the audit log).
- **Low balance**: each building has alert levels (SMS and email). The `low_credit_alerts` job emails the admins once a day and the dashboard shows a banner. At zero, messages fail visibly instead of being lost.
- Provider side: your own balance with the SMS aggregator is checked every 6 hours (`sms_provider_balance`), alert below `SMS_PROVIDER_LOW_BALANCE`.

## 5. Online payment gateway

Two different things use gateways:

1. **Building collections** (residents paying service charge): the building admin switches on **Online payment** in Collections > Charges, picks methods (bKash, Nagad, card), who pays the fee and the fee percent. Money goes to the **building's own** merchant account.
2. **FlatWise credit sales** (buildings buying credits): FlatWise's merchant account.

Provider settings (keys, mode off/sandbox/live) are environment variables: `BKASH_*`, `SSLCOMMERZ_*`, see `docs/PAYMENTS_SETUP.md` for sandbox, certification and go-live. Never enable `SANDBOX_PAYMENTS` in production. The `gateway_sweep` job expires abandoned sessions; `gateway_reconcile` asks the provider about yesterday's unfinished ones and settles genuine payments (amount must match).

## 6. Email

- Configure the provider with `MAIL_PROVIDER` (`smtp` or `ses`), `MAIL_FROM`, credentials. SPF, DKIM and DMARC records are in `docs/EMAIL_SETUP.md`.
- **Templates** (SaaS console > Email > Templates): system emails (invoice issued, trial ending, credits low, password reset) and promotional ones, in English and Bangla. Missing system templates are created automatically the first time they are needed.
- **Campaigns**: audiences come from leads or an uploaded CSV (email, name, company, city, language, with the source of consent). Send a test to yourself, then send or schedule. The `campaigns_run_due` job continues throttled sends.
- **Suppression**: unsubscribes and bounces are added to the suppression list automatically and never emailed again. Promotional mail always carries an unsubscribe link.

## 7. Jobs

SaaS console > **Jobs** lists every scheduled job, last run, status and alerts. You can run one now (for example `reminders_run` after fixing a provider issue). Jobs are safe to run twice: each guards itself with a mark or an idempotency key. The list and what each does is in `docs/JOBS.md`.

Scheduling: on cPanel a cron entry every minute runs `python -m app.jobs.cli run-due`; on a VPS set `JOBS_ENABLED=1`.

**Data retention is not a job yet.** Add one that calls `app.services.retention.run_purge(db)` and commits, daily (see section 8). Until then use **Run purge** by hand.

Alerts (`system_alerts`): integrity problems, stuck payments, dunning for a person, failed jobs, low credits, provider balance. Read them daily; press **Mark resolved** when handled.

## 8. Data retention and deletion requests

SaaS console > **Data retention** (super admin and SaaS admin).

| Setting | Default | Covers |
|---|---|---|
| Visitor log | 24 months | visits, visitor photos, resident notifications about visits, visitor-bay parking logs, finished passes |
| Sent email and SMS | 12 months | email copies in the outbox (not queued ones) and the SMS log rows |
| Former residents | 36 months | phone and email on the occupancy record of people who moved out; their tenant-onboarding file: documents, National ID, family and address details |
| Activity (audit) log | never | never deleted: it is append-only and hash-chained |

`0` months keeps that kind forever; otherwise 3 to 120. The page shows how many records are past their time. **Preview** counts without deleting; **Run purge** deletes and writes one audit row (`retention.purge`). The name of a former resident stays on the flat's history, and invoices, payments and ledger are never purged here.

The same function is available to jobs: `from app.services.retention import run_purge`.

**Account-deletion requests**: a person asks from Profile > Delete my account (password required). Under *Account-deletion requests* you see who, when and why. **Erase now** anonymises the account: name, email, phone, photo and profile details are blanked, sign-in and sessions closed, memberships removed, their name on notice receipts, committee records and occupancy records removed. Invoices, payments, journal lines and the audit log stay (they hold flat and numeric ids, not names), so the books balance exactly as before. A request is **blocked** if the person is FlatWise staff or the only property admin of a building (hand the role over first). **Refuse** needs a reason that the person sees. Target a response time (the checklist suggests 30 days).

**Tenant move-out**: the admin or owner presses Move out. The sign-in for that building stops at once, vehicles go to "to review", the flat keeps a history line. After the former-resident period the contact details and onboarding file are erased by the purge.

## 9. Exports for customers

Property admin, agency manager and president can download the whole building from **Data export**: one ZIP, one CSV per topic (flats, people, invoices, invoice lines, payments, ledger journal lines, expenses, staff without National ID, notices, requests, visitors, bookings, vehicles). Limit: 3 per building per 24 hours (`EXPORT_BUILDING_PER_DAY`). Each export is in the activity log (`export.building`). Single lists have an **Export CSV** button. The Plan page also offers a raw export for customers who leave.

## 10. Everyday support

| Request | What to do |
|---|---|
| "I forgot my password" | The sign-in page has a reset by email. If email is not working, check the mail provider and the outbox. |
| "I cannot see menu X" | Role or plan. Check the person's role in Roles, then the building's plan features. |
| "SMS did not arrive" | Messages screen (customer) shows sent or failed and why; check credits first, then the provider balance and sender ID. |
| "A payment is missing" | Collections > Payments (pending ones wait for the treasurer); for online payments Online payments list and the gateway reconcile job. |
| "Our books do not balance" | They cannot be edited. Run the `integrity_check` job and read the alert; fix by a reversing entry, never by deleting. |
| "Delete our data" | Export first, then handle as a cancellation and a retention purge; personal deletion requests go through section 8. |
| "A guard used override" | Audit log shows who, when and why. |

## 11. Audit log

Menu > Activity log. FlatWise admins see everything; building admins and presidents see their building; everyone else sees their own actions. `GET /api/audit/verify` (super admin, SaaS admin) re-computes the hash chain and names the first changed row.
