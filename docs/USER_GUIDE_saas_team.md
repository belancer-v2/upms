# User guide: FlatWise team (SaaS console)

For FlatWise staff. Engineering and set-up tasks are in `ADMIN_GUIDE.md`; this page is the screen-by-screen tour. Your menu shows only what your role needs.

| Screen | Super admin | SaaS admin | Finance | Sales | Support |
|---|---|---|---|---|---|
| Overview | yes | yes | yes | yes | yes |
| Buildings | yes | yes | yes | yes | yes |
| Leads | yes | yes | no | yes | no |
| SaaS invoices | yes | yes | yes | no | no |
| Credit sales | yes | yes | yes | yes | yes (read) |
| Email | yes | yes | yes | yes | no |
| Reports | yes | yes | yes | yes | no |
| Plans and prices | yes (edit) | yes (edit) | read | read | read |
| Invoice settings | yes | yes | no | no | no |
| Data retention | yes | yes | no | no | no |
| Jobs | yes | yes | no | no | no |
| Team | yes | yes | no | no | no |

## Overview and Buildings

The overview shows buildings, trials, paying customers and monthly revenue. **Buildings** lists every building with plan, status and flats. Open one to see invoices, features, credits and the trial end. From there you can change the plan, extend the trial, switch a feature on or off for that building only, grant SMS credits, or suspend and reactivate.

## Leads (Sales)

Every demo and contact form on the website becomes a lead. Open it, call, write a note, move it through New, Contacted, Demo, Trial, Won or Lost, and assign an owner. Call within a day.

## FlatWise invoices and reports (Finance)

**SaaS invoices**: choose the month, see each customer's invoice, open to print or send, record a payment, or issue a **credit note** for a correction. Numbers are sequential and never reused. **Reports**: revenue, subscriptions, collections, credit sales. **Invoice settings** (admins): legal name, address, BIN, TIN, VAT, bank and merchant numbers, prefixes, financial-year start. Fill them before the first invoice.

## Credit sales

**Packs and prices** (finance, admin): name, credits, price before VAT, on or off sale. **To check**: manual transfers: compare the amount sent with the invoice and press **Verify and add credits** or **Reject** with a reason. **Balances**: each building's SMS and email credits, filter to *Low balance only*. **Give bonus credits** with a reason. **VAT and payment details**: VAT % and the numbers buyers pay to.

## Email

**Audiences** (from leads or a CSV), **Templates** (English and Bangla, test send), **Campaigns** (send now or schedule, per-recipient result: sent, delivered, opened, clicked, bounced, suppressed). Everyone who unsubscribes or bounces is suppressed forever. Only email people who agreed.

## Plans and prices

Three plans by four size bands: monthly price, setup fee, included SMS and email, and the feature list. The website pricing page and the signup form read these live. Change carefully: it affects new invoices only.

## Jobs and alerts (admins)

**Jobs** shows each scheduled job, its last run and any alerts (integrity, stuck payment, dunning for a person, failed job, low credit, provider balance). **Run now** is safe: jobs guard against doing the same thing twice. Mark an alert resolved when handled.

## Data retention and deletion requests (admins)

Set how long visitor logs, sent email and SMS logs, and former residents' details are kept (`0` = forever, else 3 to 120 months). **Preview**, then **Run purge**. The activity log is never deleted. Process **account-deletion requests** here: **Erase now** (blocked for staff accounts and the last admin of a building) or **Refuse** with a reason.

## Team (admins)

Add a person with a SaaS role and a temporary password (shared privately); change roles; deactivate people who leave the same day. Keep two super admins.

## Support habits

- Reproduce as the customer's role: open the building from the building box and read what that role sees.
- Never ask a customer for their password. Reset by email.
- Quote the `request_id` from an error page when you look in the logs.
- Check credits first when "SMS did not arrive", then the provider balance and sender ID.
- Books cannot be edited: fix by reversing entry. Ask engineering before touching data.
