# FlatWise API

The API is a FastAPI application (`backend/app`). This page is generated from its OpenAPI schema by `scripts/gen_api_doc.py`; the same schema is
served at `/docs` (Swagger UI) and `/openapi.json` when `ENV` is not `production`. In production both are switched off on purpose; use this file or run
the script against a staging copy.

## Conventions

| Topic | Rule |
|---|---|
| Base path | Everything is under `/api`. The web app proxies `/api/*` to the API, so the browser sees one origin. |
| Sign in | `POST /api/auth/login` returns an access token. Send it as `Authorization: Bearer <token>`. Access tokens are short-lived; `POST /api/auth/refresh` rotates the refresh token (also kept as an HttpOnly cookie). A person with a temporary password must call `POST /api/auth/change-password` before anything else (403 with `X-Error-Code: password_change_required`). |
| Building scope | Calls about a building also need `X-Property-Id: <id>`. The caller's roles *in that building* decide what is allowed. An agency manager's role covers every building of the agency. Missing or unknown id: 400. No access: 403. |
| Roles | 5 FlatWise staff roles (`saas_role` on the user) and 12 customer roles (memberships). See `backend/app/permissions.py` for the groups used by every router. |
| Plan gate | A feature the building's plan does not include answers **402** `Your plan does not include '<feature>'`. The web app shows an upgrade message. |
| Money | Always **integer paisa** (100 paisa = 1 BDT) in JSON. CSV exports are decimal taka in columns ending `_bdt`. Never floats. |
| Dates | ISO 8601. Dates are `YYYY-MM-DD`, times are UTC. Billing periods are `YYYY-MM`. |
| Errors | `{"detail": "message"}`. 401 not signed in, 403 role cannot do this, 404 not found (also used to hide other buildings' records), 409 conflict (duplicate), 422 validation, 429 rate limited. Unexpected failures answer 500 with a `request_id`; quote it to support. |
| Request id | Every response carries `X-Request-ID`. A sane inbound value is kept. |
| Rate limits | Sign-in, password reset, public forms and the whole-building export are limited. 429 carries `Retry-After`. |
| Lists | Long lists take `q` (search) and `page` / `size` and return `total` where the screen has a pager. Some older lists return a plain array capped at a few hundred rows. |
| Idempotency | Generating invoices twice creates nothing new. A ledger entry is unique per source. Reminder SMS use a message key. A repeated payment transaction id is refused (409). |
| Audit | Every write that matters adds an `audit_log` row (append-only, hash-chained). `GET /api/audit` reads it; `GET /api/audit/verify` checks the chain (FlatWise admins). |
| Files | Uploads are multipart, limited in size and type; downloads go through the API so the sign-in applies. |
| Public endpoints | `/api/public/*`, `/api/auth/login`, password reset, e-mail verification, `/api/health`, `/healthz`, `/readyz`, and token links (`/api/notices/link/...`, tenant form, unsubscribe). Everything else needs sign-in. |

## Endpoints by area

Columns: method, path, summary and, where the code has one, the first sentence of its description. All except those in the public list above need `Authorization`; paths marked with `*` also need `X-Property-Id`.

421 operations in 37 areas.

### public

Website endpoints that need no sign-in: plans and prices, leads, trial signup, form token.

| Method | Path | Summary | Notes |
|---|---|---|---|
| POST | `/api/public/leads` | Create lead |  |
| GET | `/api/public/mail/click/{token}` | Mail click |  |
| GET | `/api/public/mail/open/{token}.gif` | Mail open |  |
| GET | `/api/public/plans` | Plans |  |
| POST | `/api/public/signup` | Signup |  |
| GET | `/api/public/unsubscribe/{token}` | Unsubscribe info | Shows who the link is for without changing anything (mail scanners open links). |
| POST | `/api/public/unsubscribe/{token}` | Unsubscribe do |  |

### auth

Sign in and who am I.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/auth/demo-accounts` | Demo accounts |  |
| POST | `/api/auth/login` | Login |  |
| GET | `/api/me` | Me |  |
| POST | `/api/me/lang` | Set lang |  |

### account

Sessions, refresh tokens, password change and reset, e-mail verification.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/audit/verify` | Audit verify | Re-computes the audit hash chain. |
| POST | `/api/auth/change-password` | Change password | Needs the current password. |
| POST | `/api/auth/forgot-password` | Forgot password | Always answers the same, whether or not the account exists. |
| POST | `/api/auth/logout` | Logout | Revokes this device's session (found by the access token, or by the refresh token when the access token has expired). |
| POST | `/api/auth/refresh` | Refresh |  |
| POST | `/api/auth/resend-verification` | Resend verification |  |
| POST | `/api/auth/reset-password` | Reset password |  |
| POST | `/api/auth/verify-email` | Verify email | Confirms the address and starts the free trial clock for the buildings this person signed up. |
| GET | `/api/me/sessions` | My sessions |  |
| POST | `/api/me/sessions/revoke-all` | Revoke all sessions | Sign out of all devices. |
| DELETE | `/api/me/sessions/{sid}` | Revoke session |  |
| GET | `/api/public/form-token` | Form token | A signed timestamp the public forms send back; a submission that arrives in under 3 seconds is treated as a bot. |

### core

Activity log and the current building.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/audit` * | Audit list | SaaS admins see everything. |
| GET | `/api/property` * | Property info | The building the caller is working in, with their roles and the features their plan includes. |

### saas

SaaS console: buildings, subscriptions, plans, leads and team. FlatWise staff only.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/cancellations` | Cancellations |  |
| POST | `/api/saas/cancellations/{rid}/decide` | Decide cancellation |  |
| GET | `/api/saas/invoices` | Invoices |  |
| POST | `/api/saas/invoices/run` | Run invoices | Monthly run. |
| POST | `/api/saas/invoices/{invoice_id}/pay` | Pay invoice |  |
| POST | `/api/saas/invoices/{invoice_id}/void` | Void invoice |  |
| GET | `/api/saas/leads` | Leads |  |
| PATCH | `/api/saas/leads/{lead_id}` | Patch lead |  |
| POST | `/api/saas/leads/{lead_id}/notes` | Add note |  |
| GET | `/api/saas/orgs` | Orgs |  |
| GET | `/api/saas/orgs/{org_id}` | Org detail |  |
| POST | `/api/saas/orgs/{org_id}/cancel` | Cancel subscription |  |
| PUT | `/api/saas/orgs/{org_id}/features` | Set feature |  |
| POST | `/api/saas/orgs/{org_id}/plan` | Change plan |  |
| POST | `/api/saas/orgs/{org_id}/sms` | Add sms |  |
| POST | `/api/saas/orgs/{org_id}/status` | Set status |  |
| POST | `/api/saas/orgs/{org_id}/trial` | Extend trial |  |
| GET | `/api/saas/overview` | Overview |  |
| GET | `/api/saas/plans` | Plans |  |
| PUT | `/api/saas/plans/{key}` | Update plan |  |
| GET | `/api/saas/staff` | Staff |  |
| POST | `/api/saas/staff` | Add staff |  |
| PATCH | `/api/saas/staff/{uid}` | Patch staff |  |

### saas-invoice-docs

FlatWise invoices, credit notes and company settings. FlatWise staff only.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/invoices-doc/credit-note/{cn_id}` | Credit note |  |
| POST | `/api/saas/invoices-doc/issue-pending` | Issue pending |  |
| GET | `/api/saas/invoices-doc/settings` | Get settings |  |
| PUT | `/api/saas/invoices-doc/settings` | Put settings |  |
| GET | `/api/saas/invoices-doc/statement/{org_id}` | Statement |  |
| GET | `/api/saas/invoices-doc/statement/{org_id}/csv` | Statement csv |  |
| GET | `/api/saas/invoices-doc/{invoice_id}` | Get doc |  |
| POST | `/api/saas/invoices-doc/{invoice_id}/email` | Email | Renders the invoice into the sandbox outbox (services/mailer.py, M20). |
| POST | `/api/saas/invoices-doc/{invoice_id}/issue` | Issue |  |
| PUT | `/api/saas/invoices-doc/{invoice_id}/lang` | Set lang |  |
| POST | `/api/saas/invoices-doc/{invoice_id}/refund` | Refund |  |
| POST | `/api/saas/invoices-doc/{invoice_id}/void` | Void |  |

### saas-reports

SaaS revenue and subscription reports. FlatWise staff only.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/reports/meta` | Meta |  |
| GET | `/api/saas/reports/{name}` | Report |  |
| GET | `/api/saas/reports/{name}/csv` | Report csv |  |

### credits

SMS and email credits for a building: balance, packs, purchases.

| Method | Path | Summary | Notes |
|---|---|---|---|
| POST | `/api/credits/callback/{token}` | Callback | Called by the provider (in the sandbox: by the hosted page). |
| POST | `/api/credits/checkout` * | Checkout |  |
| GET | `/api/credits/invoices/{invoice_id}` | Invoice | Printable invoice or receipt. |
| POST | `/api/credits/manual` * | Manual | Pay by transfer outside the app. |
| GET | `/api/credits/purchases` * | Purchases |  |
| GET | `/api/credits/sandbox/{token}` | Sandbox | The practice 'provider' page asks for its details and gets the signed payloads a real provider would post to the callback. |
| GET | `/api/credits/summary` * | Summary |  |
| PUT | `/api/credits/threshold` * | Set threshold |  |

### credits-console

Credit sales console for FlatWise staff.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/credits/balances` | Balances |  |
| POST | `/api/saas/credits/grant` | Grant | Bonus credits with a reason. |
| GET | `/api/saas/credits/packs` | Packs |  |
| POST | `/api/saas/credits/packs` | Add pack |  |
| PUT | `/api/saas/credits/packs/{pack_id}` | Edit pack |  |
| POST | `/api/saas/credits/purchases/{pid}/reject` | Reject |  |
| POST | `/api/saas/credits/purchases/{pid}/verify` | Verify |  |
| GET | `/api/saas/credits/queue` | Queue |  |
| GET | `/api/saas/credits/sales` | Sales |  |
| GET | `/api/saas/credits/settings` | Get settings |  |
| PUT | `/api/saas/credits/settings` | Put settings |  |

### mail

Email campaigns, templates, audiences and unsubscribe. FlatWise staff only, plus the public unsubscribe link.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/mail/audiences` | Audiences |  |
| POST | `/api/saas/mail/audiences` | Create audience |  |
| POST | `/api/saas/mail/audiences/csv` | Upload csv |  |
| DELETE | `/api/saas/mail/audiences/{aid}` | Delete audience |  |
| GET | `/api/saas/mail/audiences/{aid}/recipients` | Audience recipients |  |
| GET | `/api/saas/mail/campaigns` | Campaigns |  |
| POST | `/api/saas/mail/campaigns` | Create campaign |  |
| GET | `/api/saas/mail/campaigns/{cid}` | Campaign |  |
| POST | `/api/saas/mail/campaigns/{cid}/cancel` | Campaign cancel |  |
| GET | `/api/saas/mail/campaigns/{cid}/results` | Campaign results |  |
| POST | `/api/saas/mail/campaigns/{cid}/send` | Campaign send |  |
| GET | `/api/saas/mail/campaigns/{cid}/stats` | Campaign stats |  |
| POST | `/api/saas/mail/campaigns/{cid}/test` | Campaign test |  |
| PUT | `/api/saas/mail/leads/{lead_id}/consent` | Lead consent |  |
| GET | `/api/saas/mail/leads/{lead_id}/timeline` | Lead timeline |  |
| GET | `/api/saas/mail/outbox` | Outbox |  |
| GET | `/api/saas/mail/outbox/{oid}` | Outbox one |  |
| POST | `/api/saas/mail/run-due` | Run due | Starts scheduled campaigns that are due and continues throttled ones. |
| GET | `/api/saas/mail/settings` | Get settings |  |
| PUT | `/api/saas/mail/settings` | Put settings |  |
| GET | `/api/saas/mail/stats/compare` | Compare |  |
| GET | `/api/saas/mail/suppression` | Suppression |  |
| POST | `/api/saas/mail/suppression` | Add suppression |  |
| DELETE | `/api/saas/mail/suppression/{sid}` | Remove suppression |  |
| GET | `/api/saas/mail/templates` | Templates |  |
| POST | `/api/saas/mail/templates` | Create template |  |
| GET | `/api/saas/mail/templates/{tid}` | Template |  |
| PUT | `/api/saas/mail/templates/{tid}` | Update template |  |
| DELETE | `/api/saas/mail/templates/{tid}` | Delete template |  |
| POST | `/api/saas/mail/templates/{tid}/preview` | Preview | Renders the stored template, or the unsaved blocks the editor sends, with sample data. |
| POST | `/api/saas/mail/templates/{tid}/test` | Test template |  |

### plan

The current building's plan and feature switches.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/plan` * | My plan |  |
| POST | `/api/plan/cancel-request` * | Request cancel |  |
| DELETE | `/api/plan/cancel-request` * | Withdraw cancel |  |
| GET | `/api/plan/export` * | Export data | A zip of CSV files: flats, people, invoices, payments, expenses, vendors, assets, staff. |

### property

Flats, owners, tenants, building details and the agency portfolio.

| Method | Path | Summary | Notes |
|---|---|---|---|
| POST | `/api/occupants/{occ_id}/move-out` * | Move out |  |
| GET | `/api/people` * | People |  |
| GET | `/api/portfolio` | Portfolio | Every building the caller manages as an agency manager (or all buildings for FlatWise admins). |
| POST | `/api/portfolio/buildings` | Add building |  |
| PUT | `/api/property` * | Edit property |  |
| GET | `/api/units` * | List units |  |
| POST | `/api/units` * | Add unit |  |
| POST | `/api/units/generate` * | Generate | Creates A-101, A-102 ... |
| POST | `/api/units/import` * | Import units | The frontend parses the CSV or Excel paste and sends rows. |
| GET | `/api/units/summary` * | Summary |  |
| POST | `/api/units/{unit_id}/occupants` * | Add occupant |  |
| POST | `/api/units/{unit_id}/to-let/{step}` * | To let | request (admin) -> approve (the owner) -> to_let. |

### billing

Service charge: rules, invoices, payments, dues, receipts and reminders. Money is integer paisa.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/billing/automation` * | Get auto |  |
| PUT | `/api/billing/automation` * | Put auto | Opt in to automatic monthly invoices. |
| GET | `/api/billing/dues` * | Dues |  |
| GET | `/api/billing/invoices` * | Invoices |  |
| GET | `/api/billing/invoices/{iid}` * | Invoice |  |
| POST | `/api/billing/invoices/{iid}/payments` * | Add payment | Treasurer or admin records a payment: it counts at once. |
| POST | `/api/billing/invoices/{iid}/void` * | Void |  |
| GET | `/api/billing/map` * | Collection map | Status of every flat's invoice for a period: drives the colored building map. |
| GET | `/api/billing/messages` * | Messages |  |
| GET | `/api/billing/payments` * | Payments |  |
| POST | `/api/billing/payments/{pid}/{action}` * | Decide |  |
| GET | `/api/billing/receipts/{pid}` * | Receipt |  |
| POST | `/api/billing/reminders/run` * | Reminders | For each unpaid invoice, queues the latest reminder step that is due and not yet sent, then delivers it. |
| GET | `/api/billing/rules` * | Rules |  |
| POST | `/api/billing/rules` * | Add rule |  |
| PUT | `/api/billing/rules/{rid}` * | Edit rule |  |
| POST | `/api/billing/run` * | Run | Creates one invoice per flat for the period. |
| GET | `/api/billing/summary` * | Summary |  |

### cash

Cash desk: cash taken with payer confirmation, custody and hand-over to the treasurer.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/cash/custody` * | Custody |  |
| POST | `/api/cash/entries` * | Create |  |
| GET | `/api/cash/entries` * | Entries |  |
| POST | `/api/cash/entries/{eid}/cancel` * | Cancel |  |
| POST | `/api/cash/entries/{eid}/code` * | Enter code |  |
| POST | `/api/cash/entries/{eid}/confirm` * | Payer confirm | The payer taps Confirm in their own account. |
| POST | `/api/cash/entries/{eid}/resend` * | Resend |  |
| GET | `/api/cash/open-invoices` * | Open invoices | Unpaid invoices a caretaker can take cash against. |
| POST | `/api/cash/remittances` * | Hand over | The caretaker hands all confirmed cash to the treasurer. |
| GET | `/api/cash/remittances` * | Remittances |  |
| POST | `/api/cash/remittances/{rid}/{action}` * | Decide |  |

### finance

Expenses, vendors, assets, budget, ledger and trial balance.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/finance/assets` * | Assets |  |
| POST | `/api/finance/assets` * | Add asset | An item at or above the threshold becomes an asset and is depreciated. |
| POST | `/api/finance/assets/{aid}/dispose` * | Dispose |  |
| GET | `/api/finance/budget` * | Budget |  |
| PUT | `/api/finance/budget` * | Set budget |  |
| GET | `/api/finance/expenses` * | Expenses |  |
| POST | `/api/finance/expenses` * | Add expense |  |
| POST | `/api/finance/expenses/{eid}/approve` * | Approve |  |
| POST | `/api/finance/expenses/{eid}/pay` * | Pay |  |
| POST | `/api/finance/expenses/{eid}/reject` * | Reject |  |
| GET | `/api/finance/ledger` * | Journal |  |
| GET | `/api/finance/summary` * | Summary |  |
| GET | `/api/finance/trial-balance` * | Trial |  |
| GET | `/api/finance/vendors` * | Vendors |  |
| POST | `/api/finance/vendors` * | Add vendor |  |

### budget

Month-by-month budget and month locks.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/finance/budget/monthly` * | Monthly |  |
| PUT | `/api/finance/budget/monthly` * | Set monthly |  |
| POST | `/api/finance/budget/monthly/copy-forward` * | Copy forward | mode=month copies one month's lines to the following months; mode=even_split spreads the yearly total over 12 months. |
| POST | `/api/finance/budget/monthly/lock` * | Lock |  |
| GET | `/api/finance/budget/monthly/vs-actual` * | Vs actual |  |

### gateway

Online payment settings and sessions for a building.

| Method | Path | Summary | Notes |
|---|---|---|---|
| POST | `/api/gateway/callback/{token}` | Callback | Called by the provider (in the sandbox: by the hosted page). |
| POST | `/api/gateway/checkout` * | Checkout |  |
| GET | `/api/gateway/config` * | Get config |  |
| PUT | `/api/gateway/config` * | Put config |  |
| POST | `/api/gateway/ipn/sslcommerz` | Ipn sslcommerz | SSLCommerz server-to-server notification. |
| GET | `/api/gateway/options` * | Options | What a resident may pick on the pay screen. |
| POST | `/api/gateway/return/{token}` | Provider return | Where the customer's browser lands after a real provider (bKash GET, SSLCommerz POST). |
| GET | `/api/gateway/return/{token}` | Provider return | Where the customer's browser lands after a real provider (bKash GET, SSLCommerz POST). |
| GET | `/api/gateway/sandbox/{token}` | Sandbox | The sandbox 'provider' hosted page asks for its details. |
| GET | `/api/gateway/sessions` * | Sessions |  |

### staff

Staff register, the National ID vault and salary sheets.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/staff` * | Staff |  |
| POST | `/api/staff` * | Add |  |
| PUT | `/api/staff/payroll/lines/{lid}` * | Edit line |  |
| GET | `/api/staff/payroll/lines/{lid}/payslip` * | Payslip |  |
| GET | `/api/staff/payroll/sheets` * | Sheets |  |
| POST | `/api/staff/payroll/sheets` * | New sheet |  |
| GET | `/api/staff/payroll/sheets/{shid}` * | Sheet |  |
| POST | `/api/staff/payroll/sheets/{shid}/approve` * | Approve |  |
| POST | `/api/staff/payroll/sheets/{shid}/eid-bonus` * | Eid | Adds an Eid bonus of a percent of base pay to everyone on the sheet. |
| POST | `/api/staff/payroll/sheets/{shid}/pay` * | Pay | Marks the month paid, writes one ledger entry, and sends each person a payslip SMS. |
| PUT | `/api/staff/{sid}` * | Edit |  |
| POST | `/api/staff/{sid}/leave` * | Leave |  |
| GET | `/api/staff/{sid}/nid-views` * | Nid views |  |
| POST | `/api/staff/{sid}/reveal-nid` * | Reveal | Shows the full NID once and writes who looked, and when. |

### notices

Notices with read proof.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/notices` * | Notices |  |
| POST | `/api/notices` * | Publish |  |
| GET | `/api/notices/link/{token}` | By link | The page an SMS link opens. |
| POST | `/api/notices/{nid}/archive` * | Archive |  |
| POST | `/api/notices/{nid}/nudge` * | Nudge | Sends an SMS with the notice link to everyone who has not read it yet. |
| POST | `/api/notices/{nid}/pin` * | Pin |  |
| GET | `/api/notices/{nid}/reach` * | Reach |  |
| POST | `/api/notices/{nid}/read` * | Read |  |

### policies

Versioned policies and acceptance.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/policies` * | Policies |  |
| POST | `/api/policies` * | New policy |  |
| POST | `/api/policies/{pid}/accept` * | Accept |  |
| GET | `/api/policies/{pid}/history` * | History |  |
| POST | `/api/policies/{pid}/versions` * | New version | A new version never overwrites the old one. |

### onboarding

Tenant onboarding cases, documents and the DMP pack.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/onboarding/cases` * | Cases |  |
| POST | `/api/onboarding/cases` * | Create |  |
| GET | `/api/onboarding/cases/{cid}` * | Case |  |
| POST | `/api/onboarding/cases/{cid}/cancel` * | Cancel |  |
| GET | `/api/onboarding/cases/{cid}/docs/{did}/file` * | Doc file |  |
| POST | `/api/onboarding/cases/{cid}/docs/{did}/review` * | Review doc |  |
| POST | `/api/onboarding/cases/{cid}/done` * | Done |  |
| GET | `/api/onboarding/cases/{cid}/pack` * | Pack | Everything the DMP tenant form asks for, in one place, ready to print. |
| POST | `/api/onboarding/cases/{cid}/police` * | Police | Recorded by a person after they hand in the printed pack. |
| POST | `/api/onboarding/cases/{cid}/resend` * | Resend |  |
| POST | `/api/onboarding/cases/{cid}/verify` * | Verify | A person confirms the form and documents are complete. |
| GET | `/api/onboarding/link/{token}` | Link get |  |
| PUT | `/api/onboarding/link/{token}` | Link save |  |
| POST | `/api/onboarding/link/{token}/docs` | Link upload |  |
| POST | `/api/onboarding/link/{token}/submit` | Link submit |  |

### requests

Service requests with service levels.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/requests` * | Requests |  |
| POST | `/api/requests` * | Raise request |  |
| GET | `/api/requests/assignees` * | Assignees |  |
| GET | `/api/requests/sla` * | Sla |  |
| PUT | `/api/requests/sla/{category}` * | Set sla |  |
| GET | `/api/requests/summary` * | Summary |  |
| GET | `/api/requests/{rid}` * | Detail |  |
| POST | `/api/requests/{rid}/assign` * | Assign |  |
| POST | `/api/requests/{rid}/comments` * | Comment |  |
| POST | `/api/requests/{rid}/rate` * | Rate |  |
| POST | `/api/requests/{rid}/reopen` * | Reopen |  |
| POST | `/api/requests/{rid}/status` * | Set status |  |

### committee

Committee members, meetings and votes.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/committee/meetings` * | Meetings |  |
| POST | `/api/committee/meetings` * | Schedule |  |
| GET | `/api/committee/meetings/{mid}` * | Meeting |  |
| POST | `/api/committee/meetings/{mid}/cancel` * | Cancel |  |
| POST | `/api/committee/meetings/{mid}/minutes` * | Minutes | Records attendance, the minutes and the decisions, and marks the meeting as held. |
| GET | `/api/committee/members` * | Members | current = serving today. |
| POST | `/api/committee/members` * | Add member |  |
| PUT | `/api/committee/members/{mid}` * | Change tenure | Extend or end a tenure. |
| GET | `/api/committee/proposals` * | Proposals |  |
| POST | `/api/committee/proposals` * | Propose |  |
| POST | `/api/committee/proposals/{pid}/close` * | Close | Counts the votes, applies the majority rule and locks the result. |
| POST | `/api/committee/proposals/{pid}/vote` * | Vote |  |

### profiles

Profile photos and optional personal details.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/profiles/photos` * | Photo index | Which people in the current building have a photo, with a version for cache busting. |
| GET | `/api/profiles/{kind}/{rid}` * | Read |  |
| PUT | `/api/profiles/{kind}/{rid}` * | Update |  |
| POST | `/api/profiles/{kind}/{rid}/photo` * | Upload photo |  |
| DELETE | `/api/profiles/{kind}/{rid}/photo` * | Delete photo |  |
| GET | `/api/profiles/{kind}/{rid}/photo` * | Photo |  |

### rental

Private rental records between an owner and a tenant.

| Method | Path | Summary | Notes |
|---|---|---|---|
| DELETE | `/api/rental/agreements/{aid}` * | Del agreement |  |
| GET | `/api/rental/agreements/{aid}/file` * | Agreement file |  |
| GET | `/api/rental/flats` * | My flats | The flats where I am the owner side or the tenant. |
| PATCH | `/api/rental/followups/{fid}` * | Mark followup |  |
| DELETE | `/api/rental/followups/{fid}` * | Del followup |  |
| GET | `/api/rental/issues/{iid}` * | Get issue |  |
| PATCH | `/api/rental/issues/{iid}` * | Edit issue | Either side moves the status; only the owner marks the cost. |
| POST | `/api/rental/issues/{iid}/comments` * | Add comment |  |
| GET | `/api/rental/issues/{iid}/photo` * | Issue photo |  |
| DELETE | `/api/rental/payments/{pid}` * | Del payment | The owner removes a wrong entry. |
| POST | `/api/rental/payments/{pid}/confirm` * | Confirm payment |  |
| POST | `/api/rental/payments/{pid}/receipt` * | Make receipt | Gives a confirmed payment its money receipt number (1, 2, 3 ... |
| GET | `/api/rental/payments/{pid}/receipt` * | Get receipt |  |
| POST | `/api/rental/payments/{pid}/reject` * | Reject payment |  |
| GET | `/api/rental/switches` * | Switches | For the building admin: only whether the add-on is on, flat by flat. |
| GET | `/api/rental/units/{uid}` * | Overview |  |
| POST | `/api/rental/units/{uid}/agreements` * | Add agreement |  |
| POST | `/api/rental/units/{uid}/followups` * | Add followup |  |
| POST | `/api/rental/units/{uid}/issues` * | Add issue |  |
| POST | `/api/rental/units/{uid}/notes` * | Add note |  |
| POST | `/api/rental/units/{uid}/payments` * | Add payment | Owner: records rent received (confirmed at once). |
| POST | `/api/rental/units/{uid}/remind` * | Remind | Owner sends an SMS reminder to the tenant (costs one SMS credit). |
| PUT | `/api/rental/units/{uid}/switch` * | Set switch | The flat owner (or representative) turns the add-on on or off. |

### visitors

Visitor log, passes and regular visitors.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/visitors/board` * | Board | What the guard watches (the screen polls it every 10 seconds): waiting, approved and still inside. |
| GET | `/api/visitors/flats` * | Flats | Flat picker. |
| POST | `/api/visitors/frequent` * | Add frequent |  |
| GET | `/api/visitors/frequent` * | Frequent | Residents: their flat's list. |
| DELETE | `/api/visitors/frequent/{fid}` * | Remove frequent |  |
| POST | `/api/visitors/frequent/{fid}/enter` * | Enter frequent | The guard waves a known person through. |
| GET | `/api/visitors/mine` * | Mine |  |
| GET | `/api/visitors/mine/notifications` * | Notifications |  |
| POST | `/api/visitors/mine/notifications/read` * | Read all |  |
| GET | `/api/visitors/mine/pending` * | Pending | Visitors at the gate for my flat who wait for an answer, and my unread count. |
| POST | `/api/visitors/passes` * | Create pass | The code is returned here and nowhere else. |
| GET | `/api/visitors/passes` * | Passes |  |
| POST | `/api/visitors/passes/redeem` * | Redeem | The guard types the code at the gate. |
| POST | `/api/visitors/passes/{pid}/cancel` * | Cancel pass |  |
| GET | `/api/visitors/settings` * | Get settings |  |
| PUT | `/api/visitors/settings` * | Put settings |  |
| GET | `/api/visitors/summary` * | Summary |  |
| POST | `/api/visitors/visits` * | Arrive |  |
| GET | `/api/visitors/visits` * | Visits | The log. |
| POST | `/api/visitors/visits/delivery` * | Delivery | One tap: the flat is told, nobody has to approve, and the delivery person is logged as inside. |
| POST | `/api/visitors/visits/{vid}/cancel` * | Cancel |  |
| POST | `/api/visitors/visits/{vid}/decision` * | Decide |  |
| POST | `/api/visitors/visits/{vid}/in` * | Mark in |  |
| POST | `/api/visitors/visits/{vid}/out` * | Mark out |  |
| POST | `/api/visitors/visits/{vid}/override` * | Override | The gate lets a visitor in without the resident's answer (resident not reachable). |
| POST | `/api/visitors/visits/{vid}/photo` * | Upload photo |  |
| GET | `/api/visitors/visits/{vid}/photo` * | Photo |  |

### parking

Parking slots, vehicles and visitor bays.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/parking/handover` * | Handover | Free slots to hand out, or flats that are promised more slots than they hold. |
| GET | `/api/parking/lookup` * | Lookup | Gate check: plate in, flat, owner name and slot out. |
| GET | `/api/parking/mine` * | Mine |  |
| GET | `/api/parking/settings` * | Get settings |  |
| PUT | `/api/parking/settings` * | Put settings |  |
| GET | `/api/parking/slots` * | Slots |  |
| POST | `/api/parking/slots` * | Add slot |  |
| PUT | `/api/parking/slots/{sid}` * | Edit slot |  |
| POST | `/api/parking/slots/{sid}/allocate` * | Allocate | Gives a free slot to a flat, or moves a held slot to another flat (reassign). |
| POST | `/api/parking/slots/{sid}/unallocate` * | Unallocate |  |
| GET | `/api/parking/summary` * | Summary |  |
| POST | `/api/parking/swap` * | Swap | Two flats exchange their slots. |
| GET | `/api/parking/units/{uid}` * | Unit parking |  |
| PUT | `/api/parking/units/{uid}/entitlement` * | Put entitlement |  |
| POST | `/api/parking/vehicles` * | Add vehicle |  |
| GET | `/api/parking/vehicles` * | Vehicles |  |
| PUT | `/api/parking/vehicles/{vid}` * | Edit vehicle |  |
| DELETE | `/api/parking/vehicles/{vid}` * | Remove vehicle |  |
| POST | `/api/parking/vehicles/{vid}/keep` * | Keep vehicle | Confirms a vehicle that was marked 'to review' after a move-out. |
| POST | `/api/parking/vehicles/{vid}/photo` * | Upload photo |  |
| GET | `/api/parking/vehicles/{vid}/photo` * | Get photo |  |
| GET | `/api/parking/visits` * | Visits |  |
| POST | `/api/parking/visits` * | Visit in |  |
| POST | `/api/parking/visits/{xid}/out` * | Visit out |  |

### amenities

Community hall and amenity booking.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/amenities` * | Amenities |  |
| POST | `/api/amenities` * | Add amenity |  |
| GET | `/api/amenities/blackouts` * | Blackouts |  |
| POST | `/api/amenities/blackouts` * | Add blackout |  |
| DELETE | `/api/amenities/blackouts/{bid}` * | Del blackout |  |
| POST | `/api/amenities/bookings` * | Request booking |  |
| GET | `/api/amenities/bookings` * | Bookings |  |
| GET | `/api/amenities/bookings/{bid}` * | Booking |  |
| POST | `/api/amenities/bookings/{bid}/approve` * | Approve |  |
| POST | `/api/amenities/bookings/{bid}/cancel` * | Cancel |  |
| POST | `/api/amenities/bookings/{bid}/handover` * | Handover | After the event: note any damage and release the rest of the deposit. |
| GET | `/api/amenities/bookings/{bid}/permit` * | Permit | What the guard checks at the door. |
| POST | `/api/amenities/bookings/{bid}/refund` * | Refund | Records that a cancellation refund was paid back. |
| POST | `/api/amenities/bookings/{bid}/reject` * | Reject |  |
| POST | `/api/amenities/expire` * | Expire |  |
| GET | `/api/amenities/quote` * | Quote |  |
| GET | `/api/amenities/summary` * | Summary |  |
| PUT | `/api/amenities/{aid}` * | Edit amenity |  |
| GET | `/api/amenities/{aid}/calendar` * | Calendar | A month grid for one amenity. |

### agency

Security and cleaning agencies, duty roster, attendance and agency bills.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/agency/agencies` * | Agencies |  |
| POST | `/api/agency/agencies` * | Add agency |  |
| GET | `/api/agency/agencies/{aid}` * | Agency detail |  |
| PUT | `/api/agency/agencies/{aid}` * | Edit agency |  |
| POST | `/api/agency/agencies/{aid}/docs` * | Upload doc |  |
| GET | `/api/agency/agencies/{aid}/docs/{did}` * | Get doc |  |
| DELETE | `/api/agency/agencies/{aid}/docs/{did}` * | Delete doc |  |
| POST | `/api/agency/agencies/{aid}/staff` * | Add agency staff |  |
| GET | `/api/agency/attendance/summary` * | Attendance summary |  |
| GET | `/api/agency/bills` * | Bills |  |
| POST | `/api/agency/bills` * | Add bill | Records the agency's invoice next to what the system expects, and raises a normal expense so approval (two people above BDT 50,000) and the ledger work as usual. |
| GET | `/api/agency/bills/check` * | Bill check |  |
| GET | `/api/agency/duty` * | Duty | Read-only strip for every resident: names, posts and the agency name. |
| GET | `/api/agency/posts` * | Posts |  |
| POST | `/api/agency/posts` * | Add post |  |
| PUT | `/api/agency/posts/{pid}` * | Edit post |  |
| GET | `/api/agency/replacements` * | Replacements |  |
| POST | `/api/agency/replacements` * | Ask replacement | Records the request and sends an SMS to the agency's contact person. |
| POST | `/api/agency/replacements/{rid}/fulfil` * | Fulfil | The agency sent someone: pick an existing person or add a new substitute. |
| GET | `/api/agency/roster` * | Roster |  |
| POST | `/api/agency/roster/autofill` * | Autofill |  |
| POST | `/api/agency/roster/copy` * | Copy week | Copy last week: same people, same posts, same shifts. |
| POST | `/api/agency/roster/slots` * | Add slot |  |
| DELETE | `/api/agency/roster/slots/{slid}` * | Delete slot |  |
| POST | `/api/agency/roster/slots/{slid}/mark` * | Mark |  |
| GET | `/api/agency/settings` * | Get settings |  |
| PUT | `/api/agency/settings` * | Put settings |  |
| POST | `/api/agency/shifts` * | Add shift |  |
| PUT | `/api/agency/shifts/{sid}` * | Edit shift |  |
| PUT | `/api/agency/staff/{sid}/posting` * | Set posting | Moves a staff member between direct and an agency. |
| GET | `/api/agency/today` * | Today | Today's one-tap attendance list, and who is on duty right now. |

### contracts

Agency contracts and documents.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/contracts` * | Contracts |  |
| POST | `/api/contracts` * | Add contract |  |
| GET | `/api/contracts/summary` * | Summary |  |
| PUT | `/api/contracts/{cid}` * | Edit contract |  |
| GET | `/api/contracts/{cid}` * | Contract |  |
| POST | `/api/contracts/{cid}/docs` * | Add doc |  |
| GET | `/api/contracts/{cid}/docs/{did}` * | Get doc |  |
| DELETE | `/api/contracts/{cid}/docs/{did}` * | Del doc |  |
| POST | `/api/contracts/{cid}/visits` * | Add visit |  |
| DELETE | `/api/contracts/{cid}/visits/{vid}` * | Del visit |  |
| POST | `/api/contracts/{cid}/visits/{vid}/expense` * | Visit expense | 'Create expense for this visit': a pending finance Expense (services) that goes through the normal approval. |

### jobs

Scheduled jobs: status and manual runs.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/jobs` | Jobs |  |
| GET | `/api/saas/jobs/alerts` | Alerts |  |
| POST | `/api/saas/jobs/alerts/{aid}/resolve` | Resolve |  |
| GET | `/api/saas/jobs/runs` | Runs |  |
| POST | `/api/saas/jobs/{name}/run` | Run now |  |

### webhooks

Inbound provider callbacks (SMS delivery reports, payment gateway).

| Method | Path | Summary | Notes |
|---|---|---|---|
| POST | `/api/webhooks/ses` | Ses |  |
| POST | `/api/webhooks/sms/{provider}` | Sms dlr |  |

### setup

New-customer setup wizard progress.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/setup` * | Setup wizard progress for the current building | A building with no flats and no charge rules is treated as new and gets a progress row on first call. |
| POST | `/api/setup/committee` * | Create committee sign-ins with temporary passwords | For each person: a sign-in with a one-time temporary password (shown once), the committee role in this building, and a two-year committee tenure. |
| POST | `/api/setup/complete` * | Finish the setup wizard |  |
| PUT | `/api/setup/data` * | Save the due day and reminder choices | The due day is also saved as the building's automation due day, which the scheduled billing job uses; automatic billing itself stays off. |
| POST | `/api/setup/dismiss` * | Hide the dashboard setup card |  |
| PUT | `/api/setup/steps/{step}` * | Mark one setup step done, skipped or to do |  |

### export

CSV exports and the whole-building ZIP.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/export/building.zip` * | Download the whole building as a ZIP of CSV files | Property admin, agency manager and committee president only. |
| GET | `/api/export/csv/{name}` * | Download one list as a CSV file | `name` is one of invoices, payments, dues, ledger, expenses, people, visitors. |
| GET | `/api/export/status` * | How many whole-building exports are left today |  |

### privacy

Account-deletion requests.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/me/deletion` | My account-deletion request, if any |  |
| POST | `/api/me/deletion` | Ask FlatWise to erase my personal details | Needs your password. |
| DELETE | `/api/me/deletion` | Withdraw my deletion request |  |

### retention

SaaS console: data retention settings, purge, and deletion requests.

| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/saas/deletions` | Account-deletion requests |  |
| POST | `/api/saas/deletions/{rid}/process` | Erase the person's details now |  |
| POST | `/api/saas/deletions/{rid}/reject` | Refuse a deletion request with a reason |  |
| GET | `/api/saas/retention` | Retention settings, what is due for purging, and the last run |  |
| PUT | `/api/saas/retention` | Change retention periods |  |
| POST | `/api/saas/retention/run` | Run the purge now (not scheduled) | Deletes what is past its retention period. |

### other



| Method | Path | Summary | Notes |
|---|---|---|---|
| GET | `/api/health` | Health |  |
