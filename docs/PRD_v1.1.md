# Unified Property Management System — Product Requirements Document v1.1

**Document:** 02_PRD_v1.1.md
**Status:** DRAFT for owner approval (supersedes v1.0 once approved)
**Product:** Multi-tenant Property & Facility Management SaaS
**Initial market:** Bangladesh (Dhaka residential buildings first)
**Commercial model:** SaaS, priced per building (see section 8)

---

## 1. Product vision

UPMS gives flat-owner committees, property-management agencies, caretakers and residents one system for service charges, cash control, expenses, assets, staff, tenant registration, notices and policies.

It replaces spreadsheets, paper receipts, cash disputes, missed reminders and "nobody told us" arguments. It must work for volunteer committee members and for caretakers on inexpensive Android phones with weak networks. It is reusable SaaS, not a single-building application.

## 2. What changed from v1.0

| # | Change |
|---|---|
| 1 | Added MOD-15 Communication Center (SMS, email, in-app). |
| 2 | Added MOD-16 Staff & Payroll (building staff, NID vault, salary, Eid bonus). |
| 3 | Added MOD-17 Notices & Policies (notice delivery proof, versioned policies, acceptance). |
| 4 | MOD-05 widened to **Finance, Expenses & Assets** (expenses, fixed assets, current assets). |
| 5 | MOD-02 tenant onboarding is **owner-led**, with a DMP pack and policy acceptance. |
| 6 | MOD-03 gains a **reminder engine**; manual bKash/Nagad TrxID flow first, API later. |
| 7 | MOD-04 cash control is **configurable**: payer confirmation link (default) or OTP (option). |
| 8 | New MOD-18 Visitor Pass, MOD-19 Resident App/Portal, MOD-20 Agency Dashboard. |
| 9 | Delivery is phased (P0–P5). Hardware (parking, edge) is deferred to P4. |
| 10 | Per-building SaaS plans, size bands and SMS credits are part of the product (section 8). |
| 11 | Resident experience starts as **Bangla mobile web + SMS**; native app later. |

## 3. Product outcomes (measurable)

- one authoritative building / unit / occupancy registry;
- transparent service-charge billing, reminders and collection;
- verifiable cash handling with proof for the payer;
- auditable expenses, assets and double-entry financial records;
- owner-led tenant registration and DMP pack preparation with evidence tracking;
- provable delivery of notices and acceptance of policies;
- secure storage of staff, owner and tenant NID and documents;
- reliable SMS and email delivery with cost control;
- offline-capable caretaker operations;
- SaaS onboarding, plans and subscription billing per building.

## 4. Organizational model

```text
Platform
└─ Organization (committee or agency)
   ├─ Portfolio(s)
   │  └─ Building (property)
   │     ├─ Floor → Unit
   │     ├─ Parking bay
   │     ├─ Assets (fixed, current)
   │     ├─ Staff
   │     └─ Occupancy / ownership records
   └─ Users, roles, plan, subscription, policies, integrations
```

One organization may manage many buildings. A user may hold different roles in different buildings. Billing for the SaaS subscription is per building.

## 5. Personas and roles

Stable role keys; do not invent role names in UI code.

Platform: `PLATFORM_SUPER_ADMIN`, `PLATFORM_SUPPORT` (restricted, audited, optional).

Organization / building: `AGENCY_DIRECTOR`, `PROPERTY_ADMIN`, `COMMITTEE_PRESIDENT`, `COMMITTEE_SECRETARY`, `COMMITTEE_TREASURER`, `CARETAKER`, `OWNER`, `RESIDENT_OCCUPANT`, `CORPORATE_TENANT_ADMIN`, `GUARD`.

**P1 starts with four effective roles:** Admin (`PROPERTY_ADMIN` and committee officers), Committee, Caretaker, Resident (`OWNER` / `RESIDENT_OCCUPANT`). The full set is enabled from P2/P3. Authorization also evaluates organization, building, unit relationship, ownership/occupancy and approval state.

Physical-only identities (domestic staff, visitors) are not automatically application users.

## 6. Client surfaces

| Surface | Users | Phase |
|---|---|---|
| Admin Web (responsive, Next.js) | Admin, committee, agency, finance | P1 |
| Caretaker PWA (Bangla-first, offline-first, large touch targets) | Caretaker | P1 |
| Resident mobile web + SMS links | Owner, tenant | P1 |
| Visitor pass link / QR (no account) | Visitor | P3 |
| Resident app (native) | Owner, tenant | P3 |
| Guard Kiosk | Guard | P4 |

## 7. Phase plan and release scope

| Phase | Goal | Scope | Exit test |
|---|---|---|---|
| **P0 Foundation** (4–6 wks) | Safe base | Organization/building isolation, login + roles, audit log, Bangla/English, file vault, ledger core, communication engine skeleton, notice/policy data model | Isolation test passes; admin can create a building |
| **P1 Pilot MVP** (8–10 wks) | One real building uses it daily | MOD-01, 02, 03 (manual MFS), 04, 05, 06, 15, 16, 17 (basic) + reports | One pilot building runs a full month with no unresolved cash dispute |
| **P2 Sellable v1** (6–8 wks) | Sell to 5–10 buildings | Self-onboarding, Excel import, plans + subscription billing, MOD-09, MOD-08 (committee), notice/policy versioning, month close, help content | 5 paying buildings; support load manageable |
| **P3 Scale** (8–12 wks) | Remove manual work | bKash/Nagad API + reconciliation, MOD-18, 19, 20, MOD-11, amenity booking, WhatsApp | An agency manages 10+ buildings in one login |
| **P4 Security & access** | Premium add-on | MOD-07, 10, 12 | Sold only with hardware agreement |
| **P5 Enterprise** | Larger deals | MOD-13, 14, ERP/SSO | Separate sales motion |

Do not start P3+ work until P2 has paying customers.

## 8. SaaS plans and pricing (DRAFT — to validate with committees)

Billing unit: **per building per month**. Prices in BDT. Estimates only; not market-validated.

### 8.1 Size bands
| Band | Flats |
|---|---|
| S | up to 30 |
| M | 31–80 |
| L | 81–200 |
| XL | 200+ (custom quote) |

### 8.2 Monthly price
| Plan | S | M | L | Includes |
|---|---|---|---|---|
| **Basic** | 1,500 | 2,500 | 4,000 | Billing, receipts, expense book, notices |
| **Standard** | 3,000 | 4,500 | 7,000 | Basic + staff and payroll, assets, DMP tenant pack, reminder engine, caretaker app, cash confirmation link |
| **Pro** | 5,000 | 7,500 | 11,000 | Standard + resident app, visitor pass, amenities, parking, maintenance schedules, OTP cash control |

- Yearly prepay: pay 10 months, get 12.
- OTP cash control: add-on for Standard at +500 per month; included in Pro.

### 8.3 SMS
- Included per month: S 200, M 500, L 1,000.
- Extra packs: 1,000 SMS = BDT 800 (prepaid per building).
- Provider cost assumption (about 0.35–0.50 per SMS) must be confirmed.

### 8.4 One-time setup (data import + caretaker training)
S 3,000, M 5,000, L 8,000. Waived with yearly prepay.

### 8.5 Discounts
- Agency: 10% for 5+ buildings, 15% for 15+, one invoice.
- Pilot building: free for 60 days.
- Founding customers (first 5 buildings): 40% off for 12 months.

### 8.6 SaaS requirements
- plan and feature flags gate modules per building;
- subscription lifecycle: trial, active, past-due, suspended, cancelled, with reactivation;
- suspension never deletes data; read-only grace period before suspension;
- SMS credit balance, low-balance warning, usage log;
- Super Admin console: create/suspend buildings, usage, audited support access;
- data export and offboarding for leaving customers.

Validation before launch: test the price list with 5 committee treasurers, confirm SMS provider price, confirm agency discount structure.

## 9. Platform layer (all modules depend on it)

- organization / building provisioning, self-onboarding (P2), Excel import (P2);
- authentication, MFA for privileged users, session management;
- policy-based authorization; organization/building scoping and row-level security;
- audit logging (append-only, tamper-evident for financial and access events);
- file / document vault with access logging;
- search, filter, export (PDF, Excel);
- English and Bangla, one language visible per screen;
- feature flags and entitlements; subscription metadata;
- background jobs; observability; backups with tested restore;
- data export and offboarding.

## 10. Modules

Each module lists goal, features, and acceptance criteria (AC). Phase tags: P0–P5.

### MOD-01 Property & Unit Registry — P1
**Goal:** the canonical building / floor / unit graph.
- building, floor, unit hierarchy; property type (residential first); unit area; numbering conventions;
- unit states `OCCUPIED`, `VACANT`, `TO_LET`; owner approval before `TO_LET`;
- parking bay as its own record (not a text field on a unit);
- owner linkage and ownership history; full audit trail of state changes.

**AC:** a building with floors and units can be created or imported; every state change is audited; a `TO_LET` unit cannot publish without owner approval.

### MOD-02 Owner, Tenant & DMP Hub — P1
**Goal:** owner-led tenant onboarding and DMP pack preparation.
- owner profile and deed records;
- **owner adds tenant** (name, NID/passport, photo, family members, previous address, contact, rent period);
- occupancy/lease records separate from user accounts;
- document upload; OCR-assisted extraction with human review (OCR optional in P1);
- configurable DMP tenant template; generated PDF for printing;
- DMP status: `DRAFT`, `GENERATED`, `PRINTED`, `SUBMITTED` (confirmed by a human), `ACKNOWLEDGED`, `REQUIRES_ACTION`, `REJECTED`;
- acknowledgement slip upload;
- tenant must accept current building policies during onboarding (MOD-17);
- ownership and tenancy history.

**AC:** an owner can onboard a tenant end to end and print the pack; the system never marks a form legally submitted from PDF generation alone; NID files are only visible to authorized roles and every view is logged.

### MOD-03 Service Charge & Payments — P1 (manual MFS), P3 (API)
**Goal:** transparent billing and collection.
- recurring charge rules: flat-rate and area-based; line-item invoices; credits and adjustments;
- configurable due dates;
- **reminder engine:** configurable schedule (default: 3 days before due, on due date, 7 / 15 / 30 days overdue), SMS + email, stops automatically once paid, respects quiet hours and per-building SMS balance;
- P1 bKash/Nagad: payer pays to the committee's number and submits the transaction ID; treasurer verifies manually;
- P3 bKash/Nagad provider adapters, signed idempotent webhooks, reconciliation jobs, direct merchant settlement (no platform custody);
- receipts; overdue aging; collection reports.

**AC:** invoices post to the ledger; reminders are sent once per scheduled step per invoice (idempotent); a paid invoice cancels pending reminders; overdue and collection reports reconcile to the ledger.

### MOD-04 Cash Collection & Custody — P1
**Goal:** prove who paid, how much, to whom.
- caretaker selects unit/invoice and enters cash amount;
- **per-building mode:**
  - *Confirmation link (default):* payer receives SMS with amount, caretaker and building; receipt issued; payer may confirm or dispute within 48 hours; a dispute flags the entry and freezes it for committee review;
  - *OTP (option):* six-digit OTP, valid 300 seconds, three failed attempts lock out for 60 minutes, payer sees amount/caretaker/building before sharing the code; settlement happens only after verification;
- payer may be the owner or an owner-authorized tenant;
- daily caretaker cash-custody ceiling BDT 50,000 (configurable);
- remittance from caretaker to authorized committee/treasury role, recorded;
- duplicate and replay prevention; immutable audit log.

**AC:** settlement and journal entry are atomic; the custody ceiling blocks further collection until remittance; disputes and remittances appear in the cash position report. Offline: a caretaker may capture a draft but financial settlement is never completed offline.

### MOD-05 Finance, Expenses & Assets — P1
**Goal:** one controlled flow for money out and what the building owns.

**Expenses**
- mandatory categories: utilities, staff remuneration, repairs and maintenance, procurement, generator fuel, other;
- configurable child accounts (WASA, DESCO/DPDC, Titas, internet, lift maintenance);
- vendor / payee records; voucher and photo evidence;
- recurring monthly bills;
- approval workflow; dual-officer approval above BDT 50,000 (configurable);
- budget vs actual; reserve-fund tracking; month/period close (P2).

**Fixed assets**
- purchase voucher creates an asset record (name, location, vendor, cost, date, warranty, photo, serial/model);
- configurable capitalization threshold: below it, the purchase stays an expense;
- depreciation optional, off by default;
- disposal / write-off with approval.

**Current assets**
- cash in hand (caretaker custody, treasurer), bank accounts;
- receivables (from invoices);
- advances paid (vendors, staff);
- stock / consumables with reorder threshold and low-stock alert.

**Ledger**
- append-only double-entry; integer money; idempotent writes; bank / cash / gateway clearing accounts; exportable statements and audit evidence.

**AC:** every journal balances; a fixed-asset purchase above the threshold produces both an asset record and the correct journal; closed periods reject posting; approvals above the threshold require two distinct officers.

### MOD-06 Caretaker Quick-Log — P1
- Bangla-first dashboard; large touch targets;
- cash collection entry (MOD-04);
- water/electric/sub-meter reading with photo; previous-reading comparison and anomaly flag; OCR suggestion with manual confirmation;
- daily / shift checklist;
- offline queue; deterministic per-item sync state; conflict resolution UI; failed sync is never hidden.

**AC:** works on low-cost Android over an unreliable network; every queued item shows a sync state.

### MOD-15 Communication Center — P0 skeleton, P1 full
**Goal:** reliable, affordable, provable messaging.
- channels: SMS (primary), email, in-app; WhatsApp in P3;
- adapter-based providers; Bangla and English templates with placeholders; admin-editable templates;
- per-event definitions: audience, trigger, retry policy, idempotency key, redaction;
- delivery log with status; retry; failure list for admins;
- per-building SMS credits, cost tracking, low-balance alert, daily limit, quiet hours, opt-out for non-essential messages;
- OTP and security messages are transactional and contain no unnecessary personal data.

Events at launch: invoice issued, reminder, overdue, receipt, cash confirmation / OTP, payslip, complaint update, notice, policy change.

**AC:** a message is never sent twice for the same event and recipient; every send has a stored delivery status; an exhausted SMS balance is visible to the admin before failures occur.

### MOD-16 Staff & Payroll — P1
**Goal:** manage building staff securely and pay them correctly.
- staff profile: caretaker, guard, cleaner, driver, others;
- **NID and documents in an encrypted vault, view-logged, masked in lists**, photo, emergency contact;
- contract, joining date, duty schedule;
- monthly salary sheet; advances; deductions; Eid bonus; payslip by SMS;
- payroll posts to the ledger (MOD-05);
- staff exit with document retention per policy.

**AC:** NID is never shown in plain text in lists or logs; every view and download is audited; payroll totals reconcile to ledger entries.

### MOD-17 Notices & Policies — P1 basic, P2 full
**Goal:** prove who was told, when, and who accepted.

**Notices**
- bilingual notices; audience targeting: everyone, owners only, tenants only, block/floor, overdue units;
- types: general, emergency (water, gas, lift, power), meeting, payment, rule change;
- channels: SMS short link, email, in-app, print-ready PDF for the physical noticeboard;
- scheduling, expiry; committee approval before publishing (P2);
- read receipts and a "not reached" list for caretaker follow-up.

**Policies**
- policy library: house rules, late-fee policy, parking, renovation, move-in/move-out, pets, noise, garbage, visitors and delivery, generator and utility policy;
- **versioning** with effective dates (P2);
- acceptance tracking by owner and tenant; **acceptance required during tenant onboarding**; re-acceptance requested on change (P2);
- reports: who accepted which version and when; who has not;
- default: reminder only. A building may turn on "block active status until policies are accepted".

**AC:** the system can show the exact policy version in force on any date and who accepted it; the not-reached list is accurate to the delivery log.

### MOD-09 Complaints & Service Requests — P2
- category, priority, description, attachments; assignment to caretaker, vendor or team;
- acknowledgement and resolution timestamps; configurable SLA timers and escalation (reference default: 2 h acknowledge, 24 h dispatch, 48 h resolve — configurable, not contractual);
- comments and status history; resident-visible progress; reopen with reason; analytics.

### MOD-08 Committee & Amenities — P2 (committee), P3 (amenities)
- committee roles, tenure records, handover reminders, meeting and event records;
- amenity registry, calendars, tariffs/deposits/rules; request → approve/reject → lock → complete/cancel; conflict prevention.

### MOD-18 Visitor Pass — P3
- resident pre-approves by SMS or QR; time-bound, minimum data; guard validation; no visitor account.

### MOD-19 Resident App / Portal — P3
- dues, receipts, notices and policies, complaints, visitor pass, amenities; native app after the mobile web version proves demand.

### MOD-20 Agency Dashboard — P3
- many buildings, one login; portfolio collection and dues; consolidated reports; one invoice for the agency.

### MOD-11 Asset Maintenance — P3
- builds on the MOD-05 asset register: service intervals by calendar / run-hours / meter; preventive work orders; inspection history; downtime and cost history.

### MOD-07 Parking & ANPR — P4
- bay allocation periods; vehicle registry; resident and visitor association; guard entry and override (audited); ANPR event ingestion; local allow/deny cache; barrier command abstraction; false-match workflow.

### MOD-10 Domestic Staff Access — P4
- domestic staff profile linked to units; documents; allowed schedule; credential issue and revocation; entry notifications; curfew / overstay events; privacy-aware retention. (Building employees are handled by MOD-16.)

### MOD-12 Edge Access & IoT — P4
- property-local Linux gateway; secure enrollment; local authorization cache; offline RFID/QR/ANPR validation; heartbeat; event buffering; signed config; manual fallback; hardware-in-the-loop tests. Latency targets are not promised until measured on real hardware.

### MOD-13 Commercial CAM / NNN — P5
- commercial leases and suites; GLA; CAM pool and eligible expense rules; proration; CapEx exclusion; direct metered utilities; audit worksheet per invoice; ERP adapters; corporate portal; SSO where contracted.

### MOD-14 Retail Mall Analytics — P5
- retail leases; common utility allocation; promotion schedule; footfall sensor ingestion; aggregated privacy-preserving counts; no facial identification.

## 11. Financial posting rules

| Event | Debit | Credit |
|---|---|---|
| Invoice issued | Accounts Receivable | Service Charge Revenue |
| MFS payment (verified) | Bank / Gateway Receivable | Accounts Receivable |
| Cash collected (confirmed or OTP-verified) | Caretaker Cash in Custody | Accounts Receivable |
| Cash remitted to treasurer / bank | Bank / Authorized Cash Custody | Caretaker Cash in Custody |
| Expense paid | Expense account | Cash / Bank |
| Expense bill received, unpaid | Expense account | Accounts Payable |
| Fixed asset purchased (above threshold) | Fixed Asset | Cash / Bank / Accounts Payable |
| Salary paid | Salary Expense | Cash / Bank |
| Salary advance | Staff Advance (current asset) | Cash / Bank |
| Depreciation (if enabled) | Depreciation Expense | Accumulated Depreciation |

Chart of accounts is configurable per building while journals stay balanced. Posted entries are never edited; corrections are reversing entries.

## 12. Notification requirements

Every notification-triggering feature defines audience, trigger, retry policy, idempotency key, localized template, sensitive-data redaction and opt-out / legal basis. See MOD-15.

## 13. Security and privacy of PII

- NID, passport, photos and deeds: encrypted at rest and in transit;
- access only for named roles; every view and download logged; masked in lists;
- retention periods set by policy after legal review (open decision);
- no cross-organization data exposure in any automated isolation test;
- support access to customer data is audited and time-limited.

## 14. Localization and accessibility

- English and Bangla are first-class. Show the person's chosen language only on a screen; editors that hold both versions use language tabs, and both versions stay required.
- Caretaker defaults to Bangla; admin may default to English with immediate switching.
- Do not mistranslate identifiers, amounts, unit numbers, timestamps or provider transaction IDs.
- Minimum touch target 48 x 48 for frontline interfaces; WCAG AA for critical status; aim for AAA on caretaker and guard critical controls.

## 15. Non-functional objectives (engineering objectives, not SLAs until measured)

- Cloud backend: Python FastAPI domain-oriented modular monolith; PostgreSQL primary store (SQLAlchemy 2.x, Alembic, psycopg 3); workers from the same codebase; no new framework or business microservice without architecture approval.
- Edge/PACS runtime is Python, deployed separately at the property (P4).
- API p95 under nominal load: reads <= 250 ms, writes <= 400 ms, excluding third-party latency.
- Financial mutations strongly consistent and idempotent.
- Availability design target 99.95%; DR launch target RPO <= 5 min, RTO <= 30 min; do not claim until tested.
- Audit trails for financial and access events are tamper-evident.

## 16. Out of scope unless separately approved

- acting as a bank, escrow, payment-system operator or custodian of client funds;
- facial-recognition surveillance;
- autonomous AI financial approval;
- autonomous legal or statutory submission without human confirmation;
- replacement of government police / CIMS systems;
- every elevator/PACS vendor protocol without an approved adapter;
- arbitrary custom ERP integrations outside contracted scope;
- hardware procurement and installation unless separately included.

## 17. Open decisions (do not block unrelated work)

1. Pilot building and committee.
2. SMS provider, sender identity and per-SMS cost.
3. Official DMP form and version at rollout location.
4. bKash / Nagad merchant or sub-merchant model for the first customer.
5. Who receives the cash confirmation / OTP by default (owner or tenant), and how an absent owner authorizes a tenant.
6. Whether link-mode cash is marked paid immediately with a 48-hour dispute window (proposed) or held until confirmed.
7. Capitalization threshold default and whether depreciation stays off in v1.
8. Policy acceptance: reminder only (proposed default) or blocking.
9. Final price list and size bands after committee validation.
10. Legally approved retention durations by data class.
11. Production region and data-localization after legal review.
12. Final product name.
13. Whether MOD-18, 19 and 20 numbering is accepted.

## 18. Acceptance criteria for the first residential production release (end of P1/P2)

The release is not accepted until it demonstrates:

- isolated organization / building data (automated test);
- user and role onboarding with least privilege;
- building / floor / unit lifecycle;
- owner and occupancy records, owner-led tenant onboarding and DMP pack with evidence tracking;
- recurring service-charge invoices, reminders and receipts;
- manual MFS payment verification (P1) and provider sandbox with reconciliation (P3);
- cash confirmation (and OTP where enabled) with custody limit and remittance;
- immutable, balanced ledger; expense approvals; fixed and current asset registers;
- staff registry with NID vault, payroll and payslips;
- notice delivery with read tracking, and policy acceptance records;
- SMS and email delivery log, with credit control;
- caretaker offline queue with safe sync;
- per-building plan gating and subscription billing (P2);
- module-by-module QA and security scores of at least 88;
- zero open P0 / P1 defects at the release gate.
