# Launch checklist

Everything the **owner** must decide, sign or register before real customers use FlatWise. The software cannot do these for you. Tick each line and write the date and who did it.

Legend: **[blocker]** do not launch without it. **[soon]** within the first month. Where a vendor's rules matter, this page says "confirm with the vendor": rules and fees change, so ask in writing and keep the reply.

## 1. Company and legal

- [ ] **[blocker]** Company registered (legal name, registered address). Fill `frontend/src/lib/company.ts`: legal name, address, jurisdiction, support email, support phone, support hours, privacy contact email, website. Every `[SQUARE BRACKET]` there shows highlighted on the Terms, Privacy, Refund, Contact and Help pages until replaced.
- [ ] **[blocker]** Trade licence number and BIN/TIN in `company.ts`, and the same details in **SaaS console > Invoice settings** (legal name, address, BIN, TIN, VAT %, bank, bKash and Nagad merchant numbers, invoice prefix, financial year start). These print on every FlatWise invoice.
- [ ] **[blocker]** A Bangladeshi lawyer reviews `frontend/src/lib/legal.ts` (Terms of Service, Privacy Policy, Refund and Cancellation Policy, English and Bangla). Decide every `[BRACKET]` decision in them: refund window, refund days, credit expiry, retention after a customer leaves, hosting country, provider names, liability cap. Then set `LEGAL_REVIEWED = true` in `company.ts` to remove the "draft" notice.
- [ ] **[blocker]** Make sure the Privacy Policy is **true**: it states default retention periods (visitor logs 24 months, sent mail and SMS logs 12, former residents 36), "no advertising or tracking cookies", NID encryption, regular backups and private file storage. Change the text or the setting, not just one of them.
- [ ] **[blocker]** Check data-protection obligations for personal data in Bangladesh (the law is changing; ask your lawyer which rules apply on the launch date): lawful basis, notice to residents, where data may be stored, breach reporting, a named contact. Record the answer here: ____________
- [ ] **[soon]** Customer contract or order form for agencies with many buildings (custom quote above 200 flats).
- [ ] **[soon]** Bank account in the company's name for subscription payments; decide VAT registration and the VAT % default (SaaS console > Credit sales > VAT and payment details, and Invoice settings).
- [ ] **[soon]** Terms for resident-facing text: who tells residents that the building uses FlatWise and what is recorded (a notice template for committees).

## 2. Payments

- [ ] **[blocker for online payment]** bKash merchant account for the committee-side gateway and for FlatWise's own credit sales. Apply with the documents the vendor asks for (usually trade licence, TIN, bank account, owner's NID; confirm with the vendor). Keep sandbox until `docs/PAYMENTS_SETUP.md` certification checklist passes, then switch `BKASH_MODE=live`.
- [ ] **[soon]** SSLCommerz merchant account (card and other wallets), same steps (`SSLCOMMERZ_MODE`).
- [ ] **[blocker]** Public HTTPS address for vendor callbacks (`API_PUBLIC_URL`) and result redirects (`APP_URL`). The redirect is never trusted; the server-to-server callback settles payments.
- [ ] **[blocker]** Manual payment details shown to customers who buy credits by transfer: bKash/Nagad numbers and bank account (Credit sales > VAT and payment details).
- [ ] **[soon]** Decide who pays the gateway fee by default and check the fee percentage against the vendor contract.
- Reminder: `SANDBOX_PAYMENTS` must be off in production; start-up checks enforce this.

## 3. SMS

- [ ] **[blocker]** Contract with a BTRC-licensed SMS aggregator (the repo ships a BulkSMSBD adapter and a generic HTTP gateway; see `docs/SMS_SETUP.md`).
- [ ] **[blocker]** **Sender ID (mask) registration** through the aggregator: submit the company name, trade licence and the sender text you want; approval by the aggregator and the operators can take days. Until approved, messages may go out on a generic number. Confirm with the vendor whether Bangla (Unicode) messages are billed per 70-character segment (FlatWise counts segments; set `SMS_UNICODE_*` to match).
- [ ] **[blocker]** Set `SMS_PROVIDER`, key and `SMS_SENDER_ID` as secrets, send a real test to three operators (Grameenphone, Robi, Banglalink, Teletalk if you can) and check delivery reports (`SMS_DLR_*`, optional).
- [ ] **[soon]** Top up the aggregator balance; set `SMS_PROVIDER_LOW_BALANCE`; a job alerts below that level.
- [ ] **[soon]** Opt-out wording and quiet hours policy for reminders (FlatWise sends polite reminders at the steps set in the wizard; decide what you promise customers).

## 4. Email

- [ ] **[blocker]** Sending domain (for example `mail.yourdomain`) and a mailbox for replies. Choose SMTP (cPanel, Zoho, Brevo, Mailgun) or Amazon SES (`docs/EMAIL_SETUP.md`).
- [ ] **[blocker]** DNS: **SPF** record including your sender, **DKIM** keys published and verified, **DMARC** starting at `p=none` then tightened. Test with a mail checker and send to Gmail and Outlook.
- [ ] **[blocker]** `MAIL_PROVIDER`, `MAIL_FROM`, `MAIL_REPLY_TO`, credentials as secrets.
- [ ] **[soon]** Bounce and complaint handling (SES notifications, webhook secret) so bad addresses are suppressed automatically.
- [ ] **[soon]** Physical address and unsubscribe wording in the promotional templates (SaaS console > Email > Templates).

## 5. Domain, DNS, TLS

- [ ] **[blocker]** Domain registered in the company's name, with registrar login held by two people. Set `NEXT_PUBLIC_SITE_URL` (used by sitemap, robots, social previews) and `APP_URL`.
- [ ] **[blocker]** DNS: `@` and `www` to the site, `api` (or same-origin proxy) to the API, mail records from section 4. Lower the TTL a day before launch.
- [ ] **[blocker]** HTTPS everywhere, redirect HTTP to HTTPS, certificate auto-renewal checked.
- [ ] **[soon]** Check the social preview (Open Graph image `src/app/opengraph-image.png`) and favicon in a messaging app. Replace the images with final artwork if the brand guideline differs.
- [ ] **[soon]** Submit `/sitemap.xml` to search consoles. `robots.txt` already hides `/app`, `/api` and token links.

## 6. Hosting, secrets, backups

- [ ] **[blocker]** Choose cPanel (`docs/CPANEL_DEPLOY.md`) or VPS (`docs/VPS_DEPLOY.md`). Production database (PostgreSQL or MySQL), not SQLite.
- [ ] **[blocker]** All secrets generated and stored outside git: `SECRET_KEY`, `NID_KEY` (losing it makes saved National IDs unreadable: keep two copies), database password, provider keys. `ENV=production` and `DEMO=0`. The API refuses to start with unsafe values.
- [ ] **[blocker]** `alembic upgrade head` on the production database; create the first super admin (`docs/CPANEL_DEPLOY.md` step 4). No demo data in production.
- [ ] **[blocker]** **Backups**: nightly database dump and file copy, off the server, 30 days; **do a restore drill before launch and monthly** (`docs/RUNBOOK.md` section 4, `scripts/backup.sh`, `scripts/restore.sh`).
- [ ] **[blocker]** Scheduler running: cron entry `python -m app.jobs.cli run-due` every minute (or `JOBS_ENABLED=1` on a VPS). Check SaaS console > Jobs shows recent runs.
- [ ] **[blocker]** Schedule the data-retention purge (section 9).
- [ ] **[soon]** Storage choice for uploads (local private folder or S3) and its backup (`docs/STORAGE.md`).

## 7. Monitoring and support

- [ ] **[blocker]** Uptime monitor on `/readyz` (database) and the home page, alerting two people by SMS or phone call.
- [ ] **[blocker]** Error logs reachable (JSON logs carry a `request_id`; customers quote it from the error page).
- [ ] **[soon]** Alert destinations for the jobs system (failed job, low provider balance, integrity problems) read daily.
- [ ] **[blocker]** **Support rota**: who answers `support@`, the phone line and the contact form each day, backup person, response targets (for example first reply within one working day), escalation for payment and data problems. Publish the hours in `company.ts` (`supportHours`).
- [ ] **[soon]** Status and incident message template; who may speak to customers during an incident.
- [ ] **[soon]** Train support on the Help center articles and on SaaS console tasks (`docs/USER_GUIDE_saas_team.md`).

## 8. Pricing check

- [ ] **[blocker]** Plans and prices in SaaS console > Plans and prices are the numbers you want to charge, for all four size bands, setup fee, SMS and email included, yearly (10 months for 12). The public pricing page reads them live.
- [ ] Review copy that is **not** read live: agency discount lines, "yearly: 2 months free" label and the FAQ wording (`frontend/src/lib/i18n/site.ts`). Update if prices or terms change.
- [ ] Credit packs (price before VAT, credits) and VAT % in Credit sales.
- [ ] Check what the free trial includes, the trial length (30 days, `TRIAL_DAYS`) and what happens at the end (`trial_ending` and `saas_dunning` jobs email on schedule; dunning never suspends by itself).
- [ ] Margin check: SMS cost from your aggregator (per segment) against what a plan includes.

## 9. Data protection operations

- [ ] Set retention periods in **SaaS console > Data retention** to what the Privacy Policy says. Press Preview, then Run purge once to see it work.
- [ ] Add a nightly job that calls `app.services.retention.run_purge(db)` (and commits). The retention page does **not** schedule itself. The existing `cleanup` job only removes technical leftovers (job history, expired tokens, old outbox rows by `OUTBOX_RETENTION_DAYS`); it is not the personal-data policy.
- [ ] Decide who processes **account-deletion requests** (Data retention page) and the target time (for example 30 days). Tell residents.
- [ ] Decide how a lost device or leaked temporary password is handled (revoke sessions from the profile, `must_change_password`).
- [ ] Keep a short **breach response** plan: who decides, who tells customers and authorities, what to preserve.
- [ ] Confirm that exports are done only by property admin, agency manager or president, and that each is in the activity log.

## 10. Day-0 smoke test (on production, with a real phone)

1. Sign up a test building from the website (English and Bangla). Check the welcome email arrives and is not in spam.
2. Walk the setup wizard: building, flats, charges, due day, committee (sign in as a committee member with the temporary password and change it).
3. Generate invoices, record a payment, see the receipt, open the ledger and check Books balance.
4. Send one reminder SMS to your own phone, in Bangla. Check sender ID and the credit deduction.
5. Pay a small amount through the online gateway in live mode, then refund it by hand.
6. Download a CSV and the whole-building ZIP; open both in Excel (Bangla text readable).
7. Request deletion of a test account and process it from the Data retention page.
8. Kill the API once and watch the uptime alert fire. Restore last night's backup on a spare server.
9. Delete the test building (SaaS console) and confirm no test data remains in reports.

## 11. Where the placeholders are

| File | What to fill |
|---|---|
| `frontend/src/lib/company.ts` | company details, support contacts, `LEGAL_REVIEWED` |
| `frontend/src/lib/legal.ts` | the `[BRACKET]` decisions inside the three legal texts |
| SaaS console > Invoice settings | legal name, BIN, TIN, VAT, bank, merchant numbers |
| `backend/.env` / host secrets | every item in `docs/ENV_VARS.md` marked S |
| `frontend/.env` | `NEXT_PUBLIC_SITE_URL` |
