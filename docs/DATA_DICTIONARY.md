# Data dictionary

Generated from the models by `scripts/gen_data_dictionary.py`. Do not edit by hand; change the model comment and run the script again.

Conventions: money columns are **integer paisa** (100 paisa = 1 BDT); dates are UTC; every building-scoped table has `property_id` (the tenant boundary); ledger tables (`journals`, `journal_lines`) and `audit_log` are append-only.

117 tables.

## Identity and tenancy

### `audit_log`

Append-only. Never updated or deleted by the application.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `at` | DATETIME | no | index |  |
| `user_id` | INTEGER | yes |  |  |
| `org_id` | INTEGER | yes | index |  |
| `property_id` | INTEGER | yes | index |  |
| `action` | VARCHAR(60) | no | index |  |
| `entity` | VARCHAR(60) | no |  |  |
| `entity_id` | VARCHAR(40) | no |  |  |
| `meta` | JSON | no |  |  |
| `note` | TEXT | no |  |  |
| `prev_hash` | VARCHAR(64) | no |  |  |
| `row_hash` | VARCHAR(64) | no |  |  |

### `organizations`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `name` | VARCHAR(160) | no |  |  |
| `name_bn` | VARCHAR(160) | no |  |  |
| `kind` | VARCHAR(12) | no |  | committee / agency |
| `status` | VARCHAR(12) | no |  | trial / active / suspended |
| `city` | VARCHAR(80) | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `users`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `email` | VARCHAR(160) | no | unique |  |
| `phone` | VARCHAR(32) | no |  |  |
| `name` | VARCHAR(120) | no |  |  |
| `name_bn` | VARCHAR(120) | no |  |  |
| `password_hash` | VARCHAR(100) | no |  |  |
| `lang` | VARCHAR(4) | no |  |  |
| `saas_role` | VARCHAR(24) | yes |  |  |
| `is_active` | BOOLEAN | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `token_version` | INTEGER | no |  |  |
| `must_change_password` | BOOLEAN | no |  |  |
| `password_changed_at` | DATETIME | yes |  |  |
| `email_verified` | BOOLEAN | no |  |  |

### `properties`

A building. This is the unit SaaS plans are priced on.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `name` | VARCHAR(160) | no |  |  |
| `name_bn` | VARCHAR(160) | no |  |  |
| `address` | VARCHAR(240) | no |  |  |
| `city` | VARCHAR(80) | no |  |  |
| `kind` | VARCHAR(16) | no |  |  |
| `floors` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `memberships`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `user_id` | INTEGER | no | FK users.id |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `property_id` | INTEGER | yes | FK properties.id |  |
| `unit_id` | INTEGER | yes |  | FK added with the units table (M3) |
| `role` | VARCHAR(24) | no | index |  |
| `created_at` | DATETIME | no |  |  |

## Plans, subscriptions, leads

### `leads`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `name` | VARCHAR(120) | no |  |  |
| `phone` | VARCHAR(32) | no |  |  |
| `email` | VARCHAR(160) | no |  |  |
| `building` | VARCHAR(160) | no |  |  |
| `flats` | INTEGER | no |  |  |
| `city` | VARCHAR(80) | no |  |  |
| `message` | TEXT | no |  |  |
| `source` | VARCHAR(24) | no |  |  |
| `status` | VARCHAR(12) | no | index | new / contacted / demo / trial / won / lost |
| `owner_id` | INTEGER | yes |  | SaaS sales user working this lead |
| `created_at` | DATETIME | no |  |  |

### `plans`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(20) | no | PK | basic / standard / pro |
| `name` | VARCHAR(60) | no |  |  |
| `name_bn` | VARCHAR(60) | no |  |  |
| `sort` | INTEGER | no |  |  |
| `monthly` | JSON | no |  | {"S": paisa, "M": paisa, "L": paisa} |
| `setup` | JSON | no |  | one-time setup fee per band |
| `sms_included` | JSON | no |  | SMS per month per band |
| `features` | JSON | no |  | feature flags switched on by this plan |
| `email_included` | JSON | no |  | email credits per month per band (M19) |

### `cancellation_requests`

A building's request to end its subscription (raised from the Plan page), approved or rejected by FlatWise. A SaaS admin can also end a subscription directly; that is recorded here as an approved row with no requester.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `requested_by` | INTEGER | yes |  |  |
| `reason` | TEXT | no |  |  |
| `status` | VARCHAR(10) | no | index | pending / approved / rejected / withdrawn |
| `created_at` | DATETIME | no |  |  |
| `decided_by` | INTEGER | yes |  |  |
| `decided_at` | DATETIME | yes |  |  |
| `decision_note` | TEXT | no |  |  |

### `feature_overrides`

Per-organization switch that beats the plan (for example a goodwill extra during a trial).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `key` | VARCHAR(30) | no |  |  |
| `enabled` | BOOLEAN | no |  |  |

### `lead_notes`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `lead_id` | INTEGER | no | FK leads.id |  |
| `user_id` | INTEGER | yes |  |  |
| `text` | TEXT | no |  |  |
| `at` | DATETIME | no |  |  |

### `saas_invoices`

What FlatWise bills its customers (subscription, setup, SMS packs).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `number` | VARCHAR(24) | no | unique |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `kind` | VARCHAR(12) | no |  | subscription / setup / sms / credits |
| `period` | VARCHAR(8) | no |  | 2026-10, or 2026 for yearly |
| `description` | VARCHAR(200) | no |  |  |
| `amount` | BIGINT | no |  | paisa |
| `status` | VARCHAR(10) | no | index | issued / paid / void |
| `issued_at` | DATETIME | no |  |  |
| `due_at` | DATETIME | no |  |  |
| `paid_at` | DATETIME | yes |  |  |
| `method` | VARCHAR(16) | no |  |  |
| `trx_id` | VARCHAR(40) | no |  |  |
| `items` | JSON | no |  | M19 credit purchases: [{kind, name, name_bn, credits, amount}] |
| `vat_bps` | INTEGER | no |  | M19: VAT rate in basis points at the time of sale |
| `vat_amount` | BIGINT | no |  | M19: paisa, included in amount |

### `sms_ledger`

Prepaid SMS credits per organization. Append-only: balance is the sum of deltas.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `delta` | INTEGER | no |  |  |
| `reason` | VARCHAR(60) | no |  |  |
| `at` | DATETIME | no |  |  |
| `by_user_id` | INTEGER | yes |  |  |
| `invoice_id` | INTEGER | yes | index | M19: the invoice a purchased grant belongs to |

### `subscriptions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `plan_key` | VARCHAR(20) | no | FK plans.key |  |
| `band` | VARCHAR(3) | no |  |  |
| `cycle` | VARCHAR(8) | no |  | monthly / yearly |
| `status` | VARCHAR(12) | no |  | trial / active / past_due / suspended / cancelled |
| `flats` | INTEGER | no |  |  |
| `trial_ends` | DATETIME | yes |  |  |
| `started_at` | DATETIME | no |  |  |
| `discount_pct` | INTEGER | no |  |  |

## Flats and people

### `units`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `block` | VARCHAR(8) | no |  |  |
| `floor` | INTEGER | no |  |  |
| `number` | VARCHAR(16) | no |  | A-501 |
| `area_sqft` | FLOAT | no |  |  |
| `bedrooms` | INTEGER | no |  |  |
| `status` | VARCHAR(16) | no | index |  |
| `created_at` | DATETIME | no |  |  |

### `occupancies`

An owner or tenant of a unit. Kept even after move-out, so the history stays.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `kind` | VARCHAR(8) | no |  | owner / tenant |
| `user_id` | INTEGER | yes | FK users.id |  |
| `name` | VARCHAR(120) | no |  |  |
| `name_bn` | VARCHAR(120) | no |  |  |
| `phone` | VARCHAR(32) | no |  |  |
| `email` | VARCHAR(160) | no |  |  |
| `resides` | BOOLEAN | no |  | owner living in the flat |
| `start_date` | DATE | no |  |  |
| `end_date` | DATE | yes |  |  |
| `active` | BOOLEAN | no | index |  |

## Service charge and messages

### `charge_rules`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(80) | no |  |  |
| `name_bn` | VARCHAR(80) | no |  |  |
| `kind` | VARCHAR(10) | no |  | flat / per_sqft |
| `amount` | BIGINT | no |  | paisa. For per_sqft: paisa per square foot |
| `active` | BOOLEAN | no |  |  |

### `messages`

Every SMS or email the system sends, and why. The idempotency key stops duplicates.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | yes |  |  |
| `to_name` | VARCHAR(120) | no |  |  |
| `to_phone` | VARCHAR(32) | no |  |  |
| `to_email` | VARCHAR(160) | no |  |  |
| `channel` | VARCHAR(8) | no |  |  |
| `template` | VARCHAR(30) | no |  |  |
| `lang` | VARCHAR(2) | no |  |  |
| `body` | TEXT | no |  |  |
| `status` | VARCHAR(8) | no | index | queued / sent / failed |
| `error` | VARCHAR(120) | no |  |  |
| `idem_key` | VARCHAR(80) | no | unique |  |
| `created_at` | DATETIME | no |  |  |
| `sent_at` | DATETIME | yes |  |  |

### `invoices`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `period` | VARCHAR(16) | no | index | 2026-10, or HALL-12 for an amenity booking |
| `number` | VARCHAR(32) | no |  |  |
| `issue_date` | DATE | no |  |  |
| `due_date` | DATE | no |  |  |
| `total` | BIGINT | no |  | paisa |
| `paid` | BIGINT | no |  | paisa, verified payments only |
| `status` | VARCHAR(8) | no |  | open / partial / paid / void |

Unique together: (unit_id, period)

### `invoice_lines`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `invoice_id` | INTEGER | no | FK invoices.id |  |
| `description` | VARCHAR(120) | no |  |  |
| `description_bn` | VARCHAR(120) | no |  |  |
| `amount` | BIGINT | no |  | (paisa) |

### `payments`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `invoice_id` | INTEGER | no | FK invoices.id |  |
| `unit_id` | INTEGER | no | index |  |
| `amount` | BIGINT | no |  | (paisa) |
| `method` | VARCHAR(8) | no |  | bkash / nagad / bank / cash |
| `trx_id` | VARCHAR(40) | no |  |  |
| `paid_on` | DATE | no |  |  |
| `status` | VARCHAR(10) | no | index | pending / verified / rejected |
| `submitted_by` | INTEGER | yes |  |  |
| `verified_by` | INTEGER | yes |  |  |
| `verified_at` | DATETIME | yes |  |  |
| `receipt_no` | VARCHAR(24) | no |  |  |
| `note` | VARCHAR(200) | no |  |  |
| `created_at` | DATETIME | no |  |  |

## Cash collection

### `remittances`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `collector_id` | INTEGER | no |  |  |
| `amount` | BIGINT | no |  | (paisa) |
| `status` | VARCHAR(10) | no |  | submitted / accepted / rejected |
| `decided_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |
| `decided_at` | DATETIME | yes |  |  |

### `cash_entries`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `invoice_id` | INTEGER | no | FK invoices.id |  |
| `unit_id` | INTEGER | no | index |  |
| `amount` | BIGINT | no |  | paisa |
| `collector_id` | INTEGER | no | index |  |
| `mode` | VARCHAR(5) | no |  | otp / link |
| `code_hash` | VARCHAR(64) | no |  |  |
| `code_expires` | DATETIME | yes |  |  |
| `attempts` | INTEGER | no |  |  |
| `locked_until` | DATETIME | yes |  |  |
| `status` | VARCHAR(10) | no | index | pending / held / handover / remitted / cancelled |
| `payment_id` | INTEGER | yes |  |  |
| `remittance_id` | INTEGER | yes | index |  |
| `created_at` | DATETIME | no |  |  |
| `confirmed_at` | DATETIME | yes |  |  |

## Ledger, expenses, assets

### `accounts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `code` | VARCHAR(8) | no |  |  |
| `name` | VARCHAR(80) | no |  |  |
| `name_bn` | VARCHAR(80) | no |  |  |
| `type` | VARCHAR(10) | no |  | asset / liability / equity / income / expense |

Unique together: (property_id, code)

### `assets`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(120) | no |  |  |
| `name_bn` | VARCHAR(120) | no |  |  |
| `category` | VARCHAR(20) | no |  |  |
| `cost` | BIGINT | no |  | (paisa) |
| `bought_on` | DATE | no |  |  |
| `life_years` | INTEGER | no |  |  |
| `capitalised` | BOOLEAN | no |  |  |
| `status` | VARCHAR(10) | no |  | in_use / disposed |
| `note` | TEXT | no |  |  |

### `budgets`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `year` | INTEGER | no |  |  |
| `category` | VARCHAR(12) | no |  |  |
| `amount` | BIGINT | no |  | whole year, paisa |

Unique together: (property_id, year, category)

### `expenses`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `category` | VARCHAR(12) | no |  | utilities / repairs / salary / fuel / services / other |
| `vendor_id` | INTEGER | yes |  |  |
| `title` | VARCHAR(160) | no |  |  |
| `amount` | BIGINT | no |  | (paisa) |
| `spent_on` | DATE | no | index |  |
| `status` | VARCHAR(10) | no | index | pending / approved / rejected / paid |
| `needs_two` | BOOLEAN | no |  |  |
| `approvals` | JSON | no |  | [{user_id, name, at}] |
| `requested_by` | INTEGER | no |  |  |
| `method` | VARCHAR(8) | no |  |  |
| `paid_on` | DATE | yes |  |  |
| `reason` | VARCHAR(200) | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `journals`

One balanced entry. Rows are never edited or deleted: a mistake is fixed by a reversing entry.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `date` | DATE | no | index |  |
| `memo` | VARCHAR(200) | no |  |  |
| `source` | VARCHAR(20) | no |  | payment / expense / asset / opening / reversal |
| `source_id` | VARCHAR(30) | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

Unique together: (property_id, source, source_id)

### `vendors`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(100) | no |  |  |
| `name_bn` | VARCHAR(100) | no |  |  |
| `phone` | VARCHAR(32) | no |  |  |
| `category` | VARCHAR(12) | no |  |  |

### `journal_lines`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `journal_id` | INTEGER | no | FK journals.id |  |
| `account_id` | INTEGER | no | FK accounts.id |  |
| `debit` | BIGINT | no |  | (paisa) |
| `credit` | BIGINT | no |  | (paisa) |

## Staff and payroll

### `nid_views`

Every time someone reveals a full NID, it is written here. Rows are never edited.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | index |  |
| `staff_id` | INTEGER | no | index |  |
| `viewer_id` | INTEGER | no |  |  |
| `at` | DATETIME | no |  |  |

### `salary_sheets`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `period` | VARCHAR(7) | no |  |  |
| `status` | VARCHAR(10) | no |  | draft / approved / paid |
| `created_by` | INTEGER | no |  |  |
| `approved_by` | INTEGER | yes |  |  |
| `paid_on` | DATE | yes |  |  |
| `method` | VARCHAR(8) | no |  |  |
| `created_at` | DATETIME | no |  |  |

Unique together: (property_id, period)

### `staff`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(100) | no |  |  |
| `name_bn` | VARCHAR(100) | no |  |  |
| `role` | VARCHAR(12) | no |  | caretaker / guard / cleaner / driver / other |
| `phone` | VARCHAR(32) | no |  |  |
| `joined` | DATE | no |  |  |
| `salary` | BIGINT | no |  | monthly, paisa |
| `status` | VARCHAR(8) | no |  | active / left |
| `nid_enc` | VARCHAR(300) | no |  | encrypted NID number |
| `nid_last4` | VARCHAR(4) | no |  |  |

### `salary_lines`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `sheet_id` | INTEGER | no | FK salary_sheets.id |  |
| `staff_id` | INTEGER | no | index |  |
| `base` | BIGINT | no |  | (paisa) |
| `bonus` | BIGINT | no |  | (paisa) |
| `deduction` | BIGINT | no |  | (paisa) |
| `bonus_kind` | VARCHAR(8) | no |  | eid / other |
| `note` | VARCHAR(120) | no |  |  |

## Notices and policies

### `notices`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `title` | VARCHAR(160) | no |  |  |
| `title_bn` | VARCHAR(160) | no |  |  |
| `body` | TEXT | no |  |  |
| `body_bn` | TEXT | no |  |  |
| `audience` | VARCHAR(10) | no |  | all / owners / tenants / committee |
| `priority` | VARCHAR(8) | no |  | normal / urgent |
| `pinned` | BOOLEAN | no |  |  |
| `status` | VARCHAR(8) | no |  | live / archived |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no | index |  |

### `policies`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `title` | VARCHAR(160) | no |  |  |
| `title_bn` | VARCHAR(160) | no |  |  |

### `notice_receipts`

One row per person a notice is meant for. read_at is the proof.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `notice_id` | INTEGER | no | FK notices.id |  |
| `name` | VARCHAR(120) | no |  |  |
| `unit` | VARCHAR(20) | no |  |  |
| `phone` | VARCHAR(32) | no |  |  |
| `user_id` | INTEGER | yes | index |  |
| `token` | VARCHAR(24) | no | unique |  |
| `sms_at` | DATETIME | yes |  |  |
| `read_at` | DATETIME | yes |  |  |
| `read_via` | VARCHAR(5) | no |  | app / link |

### `policy_versions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `policy_id` | INTEGER | no | FK policies.id |  |
| `version` | INTEGER | no |  |  |
| `body` | TEXT | no |  |  |
| `body_bn` | TEXT | no |  |  |
| `change_note` | VARCHAR(200) | no |  |  |
| `published_by` | INTEGER | no |  |  |
| `published_at` | DATETIME | no |  |  |

Unique together: (policy_id, version)

### `policy_acceptances`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `version_id` | INTEGER | no | FK policy_versions.id |  |
| `user_id` | INTEGER | no | index |  |
| `at` | DATETIME | no |  |  |

Unique together: (version_id, user_id)

## Tenant onboarding

### `tenant_cases`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | no | index |  |
| `occupancy_id` | INTEGER | yes |  |  |
| `token` | VARCHAR(24) | no | unique |  |
| `status` | VARCHAR(10) | no | index |  |
| `name` | VARCHAR(120) | no |  |  |
| `phone` | VARCHAR(32) | no |  |  |
| `rent` | BIGINT | no |  | monthly, paisa |
| `advance` | BIGINT | no |  | paisa |
| `start_date` | DATE | no |  |  |
| `lease_months` | INTEGER | no |  |  |
| `details` | JSON | no |  |  |
| `nid_enc` | VARCHAR(300) | no |  |  |
| `nid_last4` | VARCHAR(4) | no |  |  |
| `submitted_at` | DATETIME | yes |  |  |
| `police_ref` | VARCHAR(60) | no |  |  |
| `police_on` | DATE | yes |  |  |
| `receipt_no` | VARCHAR(60) | no |  |  |
| `events` | JSON | no |  | [{at, by, key, note}] |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `tenant_docs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `case_id` | INTEGER | no | FK tenant_cases.id |  |
| `kind` | VARCHAR(16) | no |  | nid_front / nid_back / photo / agreement / noc / employer |
| `filename` | VARCHAR(160) | no |  |  |
| `stored` | VARCHAR(80) | no |  |  |
| `content_type` | VARCHAR(60) | no |  |  |
| `size` | INTEGER | no |  |  |
| `status` | VARCHAR(10) | no |  | pending / accepted / rejected |
| `note` | VARCHAR(160) | no |  |  |
| `uploaded_at` | DATETIME | no |  |  |

## Requests, committee, votes

### `committee_members`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `user_id` | INTEGER | yes |  |  |
| `name` | VARCHAR(120) | no |  |  |
| `name_bn` | VARCHAR(120) | no |  |  |
| `role` | VARCHAR(16) | no |  | president / secretary / treasurer / member |
| `start_date` | DATE | no |  |  |
| `end_date` | DATE | no |  |  |
| `note` | VARCHAR(200) | no |  |  |

### `meetings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `title` | VARCHAR(160) | no |  |  |
| `held_on` | DATE | no | index |  |
| `place` | VARCHAR(160) | no |  |  |
| `agenda` | TEXT | no |  |  |
| `status` | VARCHAR(10) | no |  | scheduled / held / cancelled |
| `attendance` | JSON | no |  | [{member_id, name, present}] |
| `minutes` | TEXT | no |  |  |
| `decisions` | JSON | no |  | [str] |
| `created_by` | INTEGER | no |  |  |

### `proposals`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `title` | VARCHAR(160) | no |  |  |
| `text` | TEXT | no |  |  |
| `status` | VARCHAR(8) | no |  | open / closed |
| `result` | VARCHAR(10) | no |  | approved / rejected / tied (locked at close) |
| `tally` | JSON | no |  | locked at close: {approve, reject, eligible} |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `closed_at` | DATETIME | yes |  |  |

### `sla_rules`

Admin-edited hours per category. A category with no row uses the default.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `category` | VARCHAR(12) | no |  |  |
| `hours` | INTEGER | no |  |  |

Unique together: (property_id, category)

### `proposal_votes`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `proposal_id` | INTEGER | no | FK proposals.id |  |
| `user_id` | INTEGER | no |  |  |
| `choice` | VARCHAR(8) | no |  | approve / reject |
| `at` | DATETIME | no |  |  |

Unique together: (proposal_id, user_id)

### `service_requests`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | yes | FK units.id |  |
| `raised_by` | INTEGER | no | index |  |
| `category` | VARCHAR(12) | no |  | lift / water / electricity / security / cleaning / noise / other |
| `title` | VARCHAR(160) | no |  |  |
| `text` | TEXT | no |  |  |
| `status` | VARCHAR(12) | no | index | open / assigned / in_progress / resolved / closed |
| `assignee_id` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no | index |  |
| `due_at` | DATETIME | no |  | created (or reopened) time plus the category SLA |
| `sla_hours` | INTEGER | no |  |  |
| `assigned_at` | DATETIME | yes |  |  |
| `resolved_at` | DATETIME | yes |  |  |
| `closed_at` | DATETIME | yes |  |  |
| `reopened` | INTEGER | no |  | a resident may reopen once |
| `rating` | INTEGER | yes |  | 1 to 5, given once |
| `rating_note` | VARCHAR(300) | no |  |  |

### `request_comments`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `request_id` | INTEGER | no | FK service_requests.id |  |
| `user_id` | INTEGER | no |  |  |
| `text` | TEXT | no |  |  |
| `kind` | VARCHAR(8) | no |  | comment / event |
| `at` | DATETIME | no |  |  |

## Online payments

### `gateway_configs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `enabled` | BOOLEAN | no |  |  |
| `providers` | JSON | no |  | subset of bkash / nagad / card |
| `fee_mode` | VARCHAR(16) | no |  | building_absorbs / payer_pays |
| `fee_bps` | INTEGER | no |  | basis points: 150 = 1.5% |
| `credentials_enc` | TEXT | no |  | vault-sealed, write-only through the API |
| `updated_at` | DATETIME | no |  |  |

### `gateway_sessions`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `token` | VARCHAR(48) | no | unique | the public session id (unguessable) |
| `property_id` | INTEGER | no | FK properties.id |  |
| `invoice_id` | INTEGER | no | FK invoices.id |  |
| `unit_id` | INTEGER | no | index |  |
| `user_id` | INTEGER | no |  |  |
| `provider` | VARCHAR(8) | no |  |  |
| `amount` | BIGINT | no |  | paisa credited to the invoice |
| `fee` | BIGINT | no |  | paisa, from fee_bps at checkout time |
| `fee_mode` | VARCHAR(16) | no |  |  |
| `charged` | BIGINT | no |  | paisa the payer is asked to pay (amount, or amount + fee) |
| `status` | VARCHAR(8) | no | index | created / paid / failed / expired |
| `provider_ref` | VARCHAR(40) | no |  |  |
| `trx_id` | VARCHAR(40) | no |  |  |
| `payment_id` | INTEGER | yes |  |  |
| `idem_key` | VARCHAR(60) | no | unique | one payment per session, whatever the provider replays |
| `expires_at` | DATETIME | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `completed_at` | DATETIME | yes |  |  |

## Monthly budget

### `budget_locks`

A closed month. Editing it again needs an explicit override and is audit-logged.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `year` | INTEGER | no |  |  |
| `month` | INTEGER | no |  |  |
| `locked_by` | INTEGER | yes |  |  |
| `locked_at` | DATETIME | no |  |  |

Unique together: (property_id, year, month)

### `budget_months`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `year` | INTEGER | no |  |  |
| `month` | INTEGER | no |  | 1..12 |
| `category` | VARCHAR(12) | no |  |  |
| `amount` | BIGINT | no |  | that month, paisa |

Unique together: (property_id, year, month, category)

## Profiles

### `profiles`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `kind` | VARCHAR(10) | no |  | user / occupant / staff |
| `ref_id` | INTEGER | no | index |  |
| `photo_file` | VARCHAR(120) | no |  |  |
| `photo_type` | VARCHAR(20) | no |  |  |
| `photo_ver` | INTEGER | no |  | bumps on every change, used to bust caches |
| `about` | VARCHAR(300) | no |  |  |
| `dob` | DATE | yes |  |  |
| `blood_group` | VARCHAR(4) | no |  |  |
| `profession` | VARCHAR(120) | no |  |  |
| `emergency_name` | VARCHAR(120) | no |  |  |
| `emergency_phone` | VARCHAR(32) | no |  |  |
| `address` | VARCHAR(240) | no |  |  |
| `languages` | JSON | no |  |  |
| `updated_at` | DATETIME | no |  |  |

Unique together: (kind, ref_id)

## Parking

### `parking_settings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `property_id` | INTEGER | no | PK |  |
| `page_size` | INTEGER | no |  |  |

### `parking_slots`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `code` | VARCHAR(32) | no |  | P-A-01, A-501-C1 |
| `level` | VARCHAR(32) | no |  | level or zone |
| `kind` | VARCHAR(12) | no |  | car / motorbike / bicycle |
| `cover` | VARCHAR(8) | no |  | covered / open |
| `status` | VARCHAR(8) | no |  | active / blocked |
| `visitor` | BOOLEAN | no |  | reserved for visitors, never given to a flat |
| `note` | VARCHAR(200) | no |  |  |
| `created_at` | DATETIME | no |  |  |

Unique together: (property_id, code)

### `parking_allocations`

A slot held by a flat. until is null while it is current; ended rows stay as history.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `slot_id` | INTEGER | no | FK parking_slots.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `vehicle_kind` | VARCHAR(12) | no |  |  |
| `since` | DATE | no |  |  |
| `until` | DATE | yes | index |  |

### `parking_entitlements`

How many slots of each vehicle kind a flat is promised.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `kind` | VARCHAR(12) | no |  |  |
| `count` | INTEGER | no |  |  |

Unique together: (unit_id, kind)

### `parking_visits`

A visitor car on a visitor bay. Plate, bay and times only; separate from the visitor-pass module.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `slot_id` | INTEGER | no | FK parking_slots.id |  |
| `plate` | VARCHAR(64) | no |  |  |
| `in_at` | DATETIME | no |  |  |
| `out_at` | DATETIME | yes | index |  |
| `logged_by` | INTEGER | yes | FK users.id |  |

### `vehicles`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `reg_no` | VARCHAR(64) | no |  | as shown, normalised |
| `reg_norm` | VARCHAR(64) | no | index | letters and digits only, for duplicate checks and search |
| `kind` | VARCHAR(12) | no |  |  |
| `make_model` | VARCHAR(80) | no |  |  |
| `colour` | VARCHAR(32) | no |  |  |
| `sticker` | VARCHAR(32) | no |  |  |
| `holder_kind` | VARCHAR(8) | no |  | owner / tenant |
| `temporary` | BOOLEAN | no |  | admin-issued extra permit |
| `status` | VARCHAR(10) | no |  | active / to_review |
| `photo` | VARCHAR(80) | no |  |  |
| `photo_type` | VARCHAR(24) | no |  |  |
| `registered_by` | INTEGER | yes | FK users.id |  |
| `created_at` | DATETIME | no |  |  |

## Hall and amenity booking

### `amenities`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `kind` | VARCHAR(12) | no |  | hall / rooftop / gym / playground / guest_room |
| `name` | VARCHAR(80) | no |  |  |
| `name_bn` | VARCHAR(80) | no |  |  |
| `capacity` | INTEGER | no |  |  |
| `rules` | TEXT | no |  |  |
| `rules_bn` | TEXT | no |  |  |
| `photo_url` | VARCHAR(300) | no |  |  |
| `active` | BOOLEAN | no |  |  |
| `slots` | JSON | no |  |  |
| `ext_hour_fee` | BIGINT | no |  | paisa per extra hour, 0 = no extension offered |
| `max_ext_hours` | INTEGER | no |  |  |
| `deposit` | BIGINT | no |  | refundable security deposit |
| `cleaning_fee` | BIGINT | no |  |  |
| `generator_fee` | BIGINT | no |  | optional, chosen by the resident |
| `free_quota` | INTEGER | no |  | free bookings per flat per year |
| `min_notice_days` | INTEGER | no |  |  |
| `max_advance_days` | INTEGER | no |  |  |
| `hold_days` | INTEGER | no |  | days to pay after approval before the slot is freed |
| `cancel_rules` | JSON | no |  | [{"days": 7, "pct": 100}, ...] refund % of the fees by days before the event |

### `amenity_blackouts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `amenity_id` | INTEGER | yes | FK amenities.id | null = every amenity |
| `on_date` | DATE | no | index |  |
| `reason` | VARCHAR(120) | no |  |  |
| `reason_bn` | VARCHAR(120) | no |  |  |
| `created_by` | INTEGER | yes |  |  |

### `amenity_bookings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `amenity_id` | INTEGER | no | FK amenities.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `user_id` | INTEGER | no | index |  |
| `party` | VARCHAR(8) | no |  | owner / tenant: decides which fee applies |
| `on_date` | DATE | no | index |  |
| `slot` | VARCHAR(8) | no |  | morning / evening / night / full |
| `purpose` | VARCHAR(24) | no |  |  |
| `guests` | INTEGER | no |  |  |
| `catering` | BOOLEAN | no |  |  |
| `contact` | VARCHAR(32) | no |  |  |
| `note` | VARCHAR(300) | no |  |  |
| `ext_hours` | INTEGER | no |  |  |
| `use_generator` | BOOLEAN | no |  |  |
| `status` | VARCHAR(10) | no | index |  |
| `reason` | VARCHAR(300) | no |  | rejection or cancellation reason |
| `decided_by` | INTEGER | yes |  |  |
| `decided_at` | DATETIME | yes |  |  |
| `expires_at` | DATETIME | yes |  |  |
| `invoice_id` | INTEGER | yes | index |  |
| `fee` | BIGINT | no |  | all in paisa, fixed when approved |
| `ext_fee` | BIGINT | no |  |  |
| `cleaning` | BIGINT | no |  |  |
| `generator` | BIGINT | no |  |  |
| `deposit` | BIGINT | no |  | (paisa) |
| `total` | BIGINT | no |  | (paisa) |
| `free_used` | BOOLEAN | no |  | the yearly free quota paid the slot fee |
| `confirmed_at` | DATETIME | yes |  |  |
| `damage_amount` | BIGINT | no |  |  |
| `damage_note` | VARCHAR(300) | no |  |  |
| `handover_by` | INTEGER | yes |  |  |
| `handover_at` | DATETIME | yes |  |  |
| `refund_amount` | BIGINT | no |  |  |
| `refund_method` | VARCHAR(8) | no |  |  |
| `refunded_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no |  |  |

### `amenity_slot_holds`

One row per part of the day a live booking occupies. The unique key is what makes a double booking impossible.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `amenity_id` | INTEGER | no | FK amenities.id |  |
| `on_date` | DATE | no |  |  |
| `part` | VARCHAR(8) | no |  | morning / evening / night ("full" takes all three) |
| `booking_id` | INTEGER | no | FK amenity_bookings.id |  |

Unique together: (amenity_id, on_date, part)

## Owner rental records

### `rental_agreements`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `title` | VARCHAR(160) | no |  |  |
| `start_date` | DATE | no |  |  |
| `end_date` | DATE | yes |  |  |
| `rent` | BIGINT | no |  | monthly, paisa |
| `advance` | BIGINT | no |  | paisa |
| `filename` | VARCHAR(160) | no |  |  |
| `stored` | VARCHAR(80) | no |  |  |
| `content_type` | VARCHAR(60) | no |  |  |
| `size` | INTEGER | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

### `rental_followups`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `text` | VARCHAR(300) | no |  |  |
| `due_date` | DATE | yes |  |  |
| `ref_kind` | VARCHAR(8) | no |  | rent / issue / "" |
| `ref` | VARCHAR(16) | no |  | a period (rent) or an issue id |
| `done` | BOOLEAN | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |
| `done_at` | DATETIME | yes |  |  |

### `rental_issues`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `title` | VARCHAR(160) | no |  |  |
| `body` | TEXT | no |  |  |
| `status` | VARCHAR(12) | no | index | open / in_progress / fixed / closed |
| `cost` | BIGINT | yes |  | paisa |
| `cost_note` | VARCHAR(200) | no |  |  |
| `photo_name` | VARCHAR(160) | no |  |  |
| `photo_stored` | VARCHAR(80) | no |  |  |
| `photo_type` | VARCHAR(60) | no |  |  |
| `raised_by` | INTEGER | yes |  |  |
| `raised_side` | VARCHAR(8) | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `updated_at` | DATETIME | no |  |  |

### `rental_notes`

Follow-up history on rent: reminders sent and the owner's notes.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `kind` | VARCHAR(10) | no |  | note / reminder |
| `period` | VARCHAR(7) | no |  |  |
| `body` | VARCHAR(400) | no |  |  |
| `sms_status` | VARCHAR(8) | no |  | sent / failed / "" |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

### `rental_payments`

Rent received for a month. The owner's entries are confirmed at once; a tenant's "I paid" waits for the owner.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `period` | VARCHAR(7) | no | index | YYYY-MM |
| `amount` | BIGINT | no |  | paisa |
| `method` | VARCHAR(8) | no |  | cash / bank |
| `paid_on` | DATE | no |  |  |
| `note` | VARCHAR(300) | no |  |  |
| `bank_ref` | VARCHAR(60) | no |  |  |
| `status` | VARCHAR(10) | no | index | confirmed / pending / rejected |
| `source` | VARCHAR(8) | no |  | owner / tenant |
| `receipt_no` | VARCHAR(30) | no |  |  |
| `receipt_seq` | INTEGER | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |
| `decided_at` | DATETIME | yes |  |  |

### `rental_settings`

The per-flat switch. Off by default (no row = off). Also holds the flat's receipt counter.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `enabled` | BOOLEAN | no |  |  |
| `receipt_seq` | INTEGER | no |  |  |
| `updated_by` | INTEGER | yes |  |  |
| `updated_at` | DATETIME | no |  |  |

### `rental_comments`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `issue_id` | INTEGER | no | FK rental_issues.id |  |
| `user_id` | INTEGER | yes |  |  |
| `side` | VARCHAR(8) | no |  |  |
| `body` | VARCHAR(1000) | no |  |  |
| `created_at` | DATETIME | no |  |  |

## SMS and email credits

### `credit_packs`

A pack FlatWise sells. Prices are set by SaaS finance in the console.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `kind` | VARCHAR(6) | no | index | sms / email |
| `name` | VARCHAR(80) | no |  |  |
| `name_bn` | VARCHAR(80) | no |  |  |
| `credits` | INTEGER | no |  |  |
| `price` | BIGINT | no |  | paisa, before VAT |
| `active` | BOOLEAN | no |  |  |
| `sort` | INTEGER | no |  |  |

### `platform_settings`

FlatWise-wide key/value settings (VAT, where manual payments are sent).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(30) | no | PK |  |
| `value` | VARCHAR(200) | no |  |  |

### `credit_settings`

Per-organization low-balance thresholds.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `sms_low` | INTEGER | no |  |  |
| `email_low` | INTEGER | no |  |  |

### `credit_purchases`

One attempt to buy a pack, by sandbox gateway (mode gateway) or by manual transfer (mode manual).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `token` | VARCHAR(48) | no | unique | public session id (unguessable) |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `property_id` | INTEGER | yes |  |  |
| `user_id` | INTEGER | no |  |  |
| `pack_id` | INTEGER | yes |  |  |
| `kind` | VARCHAR(6) | no |  |  |
| `pack_name` | VARCHAR(80) | no |  |  |
| `pack_name_bn` | VARCHAR(80) | no |  |  |
| `credits` | INTEGER | no |  |  |
| `price` | BIGINT | no |  | paisa, before VAT (snapshot) |
| `vat_bps` | INTEGER | no |  |  |
| `vat` | BIGINT | no |  |  |
| `total` | BIGINT | no |  | what the buyer pays |
| `mode` | VARCHAR(8) | no |  | gateway / manual |
| `method` | VARCHAR(8) | no |  | bkash / nagad / card / bank |
| `status` | VARCHAR(10) | no | index | created / pending / paid / failed / expired / rejected |
| `provider_ref` | VARCHAR(40) | no |  |  |
| `trx_id` | VARCHAR(40) | no |  |  |
| `claimed_amount` | BIGINT | yes |  | manual: what the buyer says they sent |
| `invoice_id` | INTEGER | yes | FK saas_invoices.id |  |
| `idem_key` | VARCHAR(60) | no | unique |  |
| `note` | VARCHAR(200) | no |  |  |
| `expires_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no |  |  |
| `completed_at` | DATETIME | yes |  |  |
| `verified_by` | INTEGER | yes |  |  |

### `email_ledger`

Prepaid email credits per organization. Append-only, parallel to SmsLedger.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `delta` | INTEGER | no |  |  |
| `reason` | VARCHAR(60) | no |  |  |
| `at` | DATETIME | no |  |  |
| `by_user_id` | INTEGER | yes |  |  |
| `invoice_id` | INTEGER | yes | FK saas_invoices.id |  |

## Agencies and duty roster

### `agencies`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(120) | no |  |  |
| `name_bn` | VARCHAR(120) | no |  |  |
| `kind` | VARCHAR(10) | no |  | security / cleaning / both |
| `trade_licence` | VARCHAR(60) | no |  |  |
| `reg_no` | VARCHAR(80) | no |  | registration / TIN / BIN, free text |
| `psc_licence` | VARCHAR(60) | no |  | private security company licence |
| `address` | VARCHAR(200) | no |  |  |
| `contact_name` | VARCHAR(100) | no |  |  |
| `contact_phone` | VARCHAR(32) | no |  |  |
| `emergency_phone` | VARCHAR(32) | no |  | 24h number |
| `contract_start` | DATE | yes |  |  |
| `contract_end` | DATE | yes |  |  |
| `fee_mode` | VARCHAR(10) | no |  | flat (monthly) / per_post (per post per month) |
| `monthly_fee` | BIGINT | no |  | paisa |
| `notice_days` | INTEGER | no |  |  |
| `sla_notes` | TEXT | no |  |  |
| `status` | VARCHAR(8) | no |  | active / ended |
| `vendor_id` | INTEGER | yes |  | the Vendor row its invoices are booked under |
| `created_at` | DATETIME | no |  |  |

### `agency_settings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `shortfall_rate` | BIGINT | no |  | paisa deducted for each missing person-shift |

### `duty_posts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(80) | no |  |  |
| `name_bn` | VARCHAR(80) | no |  |  |
| `kind` | VARCHAR(10) | no |  | security / cleaning |
| `headcount` | INTEGER | no |  | people required on each shift |
| `shift_ids` | JSON | no |  | shifts this post is staffed on; empty means every shift |
| `agency_id` | INTEGER | yes |  | who supplies it; none means building staff |
| `active` | BOOLEAN | no |  |  |

### `duty_shifts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `name` | VARCHAR(40) | no |  |  |
| `name_bn` | VARCHAR(40) | no |  |  |
| `start` | VARCHAR(5) | no |  | HH:MM |
| `end` | VARCHAR(5) | no |  |  |
| `active` | BOOLEAN | no |  |  |

### `agency_bills`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `agency_id` | INTEGER | no | FK agencies.id |  |
| `period` | VARCHAR(7) | no |  |  |
| `number` | VARCHAR(60) | no |  |  |
| `amount` | BIGINT | no |  | invoiced, paisa |
| `expected` | INTEGER | no |  | computed when recorded |
| `shortfall_units` | INTEGER | no |  |  |
| `deduction` | BIGINT | no |  | (paisa) |
| `note` | VARCHAR(200) | no |  |  |
| `expense_id` | INTEGER | yes |  |  |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |

Unique together: (agency_id, period)

### `agency_docs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `agency_id` | INTEGER | no | FK agencies.id |  |
| `kind` | VARCHAR(24) | no |  | licence / contract / insurance / police_verification |
| `filename` | VARCHAR(160) | no |  |  |
| `stored` | VARCHAR(60) | no |  |  |
| `content_type` | VARCHAR(40) | no |  |  |
| `size` | INTEGER | no |  |  |
| `uploaded_by` | INTEGER | no |  |  |
| `uploaded_at` | DATETIME | no |  |  |

### `roster_replacements`

A request to the agency to send someone for an empty slot.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `slot_id` | INTEGER | no | index |  |
| `agency_id` | INTEGER | no | FK agencies.id |  |
| `day` | DATE | no |  |  |
| `post_id` | INTEGER | no |  |  |
| `shift_id` | INTEGER | no |  |  |
| `absent_staff_id` | INTEGER | no |  |  |
| `status` | VARCHAR(10) | no |  | requested / fulfilled |
| `sub_staff_id` | INTEGER | yes |  |  |
| `sms_status` | VARCHAR(8) | no |  |  |
| `note` | VARCHAR(160) | no |  |  |
| `requested_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `roster_slots`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `day` | DATE | no | index |  |
| `post_id` | INTEGER | no | FK duty_posts.id |  |
| `shift_id` | INTEGER | no | FK duty_shifts.id |  |
| `staff_id` | INTEGER | no | FK staff.id |  |
| `status` | VARCHAR(8) | no |  | planned / present / late / absent / leave |
| `substitute` | BOOLEAN | no |  |  |
| `note` | VARCHAR(160) | no |  |  |
| `marked_by` | INTEGER | yes |  |  |
| `marked_at` | DATETIME | yes |  |  |

Unique together: (post_id, shift_id, day, staff_id)

### `staff_postings`

Links a Staff row to the agency that employs them. No row means a direct (building) employee. Agency staff are never on the building's salary sheets.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `staff_id` | INTEGER | no | FK staff.id |  |
| `agency_id` | INTEGER | no | FK agencies.id |  |
| `emp_no` | VARCHAR(40) | no |  |  |
| `deployed_on` | DATE | yes |  |  |
| `substitute` | BOOLEAN | no |  |  |

## Visitors

### `visitor_settings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `page_size` | INTEGER | no |  |  |
| `overstay_hours` | INTEGER | no |  |  |

### `frequent_visitors`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `name` | VARCHAR(120) | no |  |  |
| `phone` | VARCHAR(32) | no |  |  |
| `role` | VARCHAR(10) | no |  | maid / driver / tutor / cook / other |
| `valid_from` | DATE | no |  |  |
| `valid_to` | DATE | no |  |  |
| `active` | BOOLEAN | no |  |  |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `visitor_passes`

A pre-approved visitor. The 6-digit code is stored only as a keyed hash and shown once.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `name` | VARCHAR(120) | no |  |  |
| `purpose` | VARCHAR(10) | no |  |  |
| `people` | INTEGER | no |  |  |
| `vehicle` | VARCHAR(32) | no |  |  |
| `valid_from` | DATETIME | no |  |  |
| `valid_to` | DATETIME | no |  |  |
| `code_hash` | VARCHAR(64) | no | index |  |
| `status` | VARCHAR(10) | no |  | active / used / cancelled |
| `used_at` | DATETIME | yes |  |  |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no |  |  |

### `visits`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `name` | VARCHAR(120) | no | index |  |
| `phone` | VARCHAR(32) | no |  |  |
| `purpose` | VARCHAR(10) | no |  | guest / delivery / courier / service / cab / official / other |
| `people` | INTEGER | no |  |  |
| `vehicle` | VARCHAR(32) | no |  |  |
| `kind` | VARCHAR(10) | no |  | walkin / delivery / pass / frequent |
| `status` | VARCHAR(10) | no | index | waiting / approved / denied / in / out / cancelled |
| `photo_file` | VARCHAR(80) | no |  |  |
| `photo_type` | VARCHAR(12) | no |  |  |
| `decided_by` | INTEGER | yes |  |  |
| `decided_at` | DATETIME | yes |  |  |
| `decision_via` | VARCHAR(10) | no |  | resident / pass / frequent / delivery / override |
| `note` | VARCHAR(200) | no |  |  |
| `pass_id` | INTEGER | yes |  |  |
| `frequent_id` | INTEGER | yes |  |  |
| `in_at` | DATETIME | yes | index |  |
| `out_at` | DATETIME | yes |  |  |
| `created_by` | INTEGER | no |  |  |
| `created_at` | DATETIME | no | index |  |

### `visitor_notices`

One notification entry per resident login of the flat.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `user_id` | INTEGER | no | index |  |
| `unit_id` | INTEGER | no | FK units.id |  |
| `visit_id` | INTEGER | no | FK visits.id |  |
| `kind` | VARCHAR(10) | no |  | ask / info |
| `created_at` | DATETIME | no | index |  |
| `read_at` | DATETIME | yes |  |  |

## FlatWise invoices and reports

### `saas_number_seq`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `series` | VARCHAR(8) | no | PK |  |
| `fy` | INTEGER | no | PK |  |
| `last` | INTEGER | no |  |  |

### `saas_settings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `legal_name` | VARCHAR(160) | no |  |  |
| `legal_name_bn` | VARCHAR(160) | no |  |  |
| `address` | VARCHAR(300) | no |  |  |
| `address_bn` | VARCHAR(300) | no |  |  |
| `phone` | VARCHAR(40) | no |  |  |
| `email` | VARCHAR(120) | no |  |  |
| `bin_no` | VARCHAR(40) | no |  | VAT registration (BIN) |
| `tin` | VARCHAR(40) | no |  |  |
| `bank_details` | TEXT | no |  |  |
| `bkash_merchant` | VARCHAR(40) | no |  |  |
| `nagad_merchant` | VARCHAR(40) | no |  |  |
| `logo_url` | TEXT | no |  |  |
| `footer_text` | TEXT | no |  |  |
| `footer_text_bn` | TEXT | no |  |  |
| `invoice_prefix` | VARCHAR(8) | no |  |  |
| `credit_prefix` | VARCHAR(8) | no |  |  |
| `default_vat_pct` | DOUBLE | no |  |  |
| `fy_start_month` | INTEGER | no |  | 1 = calendar year, 7 = July to June |
| `updated_at` | DATETIME | no |  |  |

### `lead_stage_events`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `lead_id` | INTEGER | no | FK leads.id |  |
| `status` | VARCHAR(12) | no |  |  |
| `at` | DATETIME | no |  |  |

### `subscription_events`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `at` | DATETIME | no | index |  |
| `kind` | VARCHAR(14) | no |  | trial_start / activate / plan_change / suspend / cancel |
| `plan_key` | VARCHAR(20) | no |  |  |
| `band` | VARCHAR(3) | no |  |  |
| `cycle` | VARCHAR(8) | no |  |  |
| `status` | VARCHAR(12) | no |  | subscription status after the event |
| `mrr` | BIGINT | no |  | paisa per month after the event, 0 when not paying |
| `by_user_id` | INTEGER | yes |  |  |

### `saas_credit_notes`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `doc_no` | VARCHAR(32) | no | unique |  |
| `fy` | INTEGER | no |  |  |
| `seq` | INTEGER | no |  |  |
| `invoice_id` | INTEGER | no | FK saas_invoices.id |  |
| `org_id` | INTEGER | no | FK organizations.id |  |
| `kind` | VARCHAR(8) | no |  | void / refund |
| `amount` | BIGINT | no |  | paisa, VAT included |
| `vat` | BIGINT | no |  |  |
| `reason` | VARCHAR(200) | no |  |  |
| `issued_at` | DATETIME | no |  |  |
| `issued_by` | INTEGER | yes |  |  |

Unique together: (invoice_id, kind, amount, issued_at)

### `saas_invoice_docs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `invoice_id` | INTEGER | no | FK saas_invoices.id |  |
| `doc_no` | VARCHAR(32) | no | unique |  |
| `fy` | INTEGER | no |  |  |
| `seq` | INTEGER | no |  |  |
| `issued_at` | DATETIME | no |  |  |
| `vat_pct` | DOUBLE | no |  |  |
| `net` | BIGINT | no |  | paisa, before VAT |
| `vat` | BIGINT | no |  | paisa |
| `total` | BIGINT | no |  | paisa, equals SaasInvoice.amount |
| `items` | JSON | no |  | [{desc, desc_bn, qty, net}] |
| `lang` | VARCHAR(2) | no |  |  |
| `quote_ref` | VARCHAR(40) | no |  |  |
| `emailed_at` | DATETIME | yes |  |  |
| `issued_by` | INTEGER | yes |  |  |

## Email campaigns

### `mail_audiences`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `name` | VARCHAR(120) | no |  |  |
| `kind` | VARCHAR(12) | no |  | stage / trial / active / churned / plan / city / band / csv |
| `params` | JSON | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

### `mail_settings`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(40) | no | PK |  |
| `value` | VARCHAR(200) | no |  |  |

### `mail_suppressions`

Global do-not-email list. unsubscribe blocks promotional mail; bounce, complaint and manual block everything.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `email` | VARCHAR(160) | no | unique |  |
| `reason` | VARCHAR(12) | no |  | unsubscribe / bounce / complaint / manual |
| `source` | VARCHAR(80) | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `by_user_id` | INTEGER | yes |  |  |

### `mail_templates`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `key` | VARCHAR(40) | no | unique |  |
| `name` | VARCHAR(120) | no |  |  |
| `name_bn` | VARCHAR(120) | no |  |  |
| `kind` | VARCHAR(14) | no |  | transactional / promotional |
| `subject_en` | VARCHAR(200) | no |  |  |
| `subject_bn` | VARCHAR(200) | no |  |  |
| `blocks_en` | JSON | no |  |  |
| `blocks_bn` | JSON | no |  |  |
| `updated_at` | DATETIME | no |  |  |
| `updated_by` | INTEGER | yes |  |  |

### `mail_campaigns`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `name` | VARCHAR(160) | no |  |  |
| `audience_id` | INTEGER | no | FK mail_audiences.id |  |
| `template_id` | INTEGER | no | FK mail_templates.id |  |
| `lang_rule` | VARCHAR(10) | no |  | recipient / bn / en |
| `status` | VARCHAR(10) | no | index | draft / scheduled / sending / sent / cancelled |
| `scheduled_at` | DATETIME | yes |  |  |
| `throttle_per_hour` | INTEGER | no |  | 0 = use the global setting |
| `simulate` | BOOLEAN | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |
| `started_at` | DATETIME | yes |  |  |
| `finished_at` | DATETIME | yes |  |  |

### `mail_consents`

Where a lead's permission to email came from, and their preferred language.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `lead_id` | INTEGER | no | PK |  |
| `source` | VARCHAR(60) | no |  |  |
| `lang` | VARCHAR(2) | no |  |  |
| `at` | DATETIME | no |  |  |

### `mail_prospects`

A row from an uploaded CSV. Belongs to one csv audience.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `audience_id` | INTEGER | no | FK mail_audiences.id |  |
| `email` | VARCHAR(160) | no | index |  |
| `name` | VARCHAR(120) | no |  |  |
| `company` | VARCHAR(160) | no |  |  |
| `city` | VARCHAR(80) | no |  |  |
| `lang` | VARCHAR(2) | no |  |  |
| `consent_source` | VARCHAR(60) | no |  |  |

### `mail_outbox`

One rendered email to one person. This is also the per-recipient result row.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `campaign_id` | INTEGER | yes | FK mail_campaigns.id |  |
| `template_key` | VARCHAR(40) | no |  |  |
| `kind` | VARCHAR(14) | no |  |  |
| `to_email` | VARCHAR(160) | no | index |  |
| `to_name` | VARCHAR(120) | no |  |  |
| `lang` | VARCHAR(2) | no |  |  |
| `lead_id` | INTEGER | yes | index |  |
| `org_id` | INTEGER | yes |  |  |
| `subject` | VARCHAR(240) | no |  |  |
| `html` | TEXT | no |  |  |
| `text` | TEXT | no |  |  |
| `vars` | JSON | no |  |  |
| `status` | VARCHAR(12) | no | index | queued / sent / bounced / suppressed / skipped / failed |
| `reason` | VARCHAR(60) | no |  |  |
| `is_test` | BOOLEAN | no |  |  |
| `provider` | VARCHAR(12) | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `sent_at` | DATETIME | yes | index |  |
| `delivered_at` | DATETIME | yes |  |  |
| `opened_at` | DATETIME | yes |  |  |
| `clicked_at` | DATETIME | yes |  |  |
| `bounced_at` | DATETIME | yes |  |  |
| `unsubscribed_at` | DATETIME | yes |  |  |
| `clicks` | JSON | no |  | URLs clicked |

## Scheduled jobs and SMS dispatch

### `job_locks`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `name` | VARCHAR(60) | no | PK |  |
| `owner` | VARCHAR(80) | no |  |  |
| `expires_at` | DATETIME | no |  |  |

### `job_marks`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(120) | no | PK |  |
| `at` | DATETIME | no | index |  |

### `job_runs`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `name` | VARCHAR(60) | no | index |  |
| `started_at` | DATETIME | no | index |  |
| `finished_at` | DATETIME | yes |  |  |
| `status` | VARCHAR(10) | no | index | running / ok / warn / failed / skipped |
| `trigger` | VARCHAR(10) | no |  | schedule / manual |
| `owner` | VARCHAR(80) | no |  | lock owner (host:pid:rand) |
| `lock_expires_at` | DATETIME | yes |  |  |
| `by_user_id` | INTEGER | yes |  |  |
| `result` | JSON | no |  |  |
| `error` | TEXT | no |  |  |

### `system_alerts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `dedupe_key` | VARCHAR(120) | no | unique |  |
| `kind` | VARCHAR(30) | no | index | integrity / payment_stuck / dunning / job_failed / low_credit |
| `severity` | VARCHAR(8) | no |  | info / warn / error |
| `message` | TEXT | no |  |  |
| `meta` | JSON | no |  |  |
| `org_id` | INTEGER | yes |  |  |
| `property_id` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no | index |  |
| `resolved_at` | DATETIME | yes |  |  |

### `building_automation`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `property_id` | INTEGER | no | PK |  |
| `auto_billing` | BOOLEAN | no |  | opt-in: create the month's invoices by itself |
| `bill_day` | INTEGER | no |  | day of month (1-28) the run happens on |
| `due_day` | INTEGER | no |  | due day written on those invoices |
| `updated_at` | DATETIME | no |  |  |

### `sms_dispatch`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `message_id` | INTEGER | no | PK |  |
| `provider` | VARCHAR(20) | no |  |  |
| `provider_ref` | VARCHAR(80) | no | index |  |
| `segments` | INTEGER | no |  |  |
| `encoding` | VARCHAR(8) | no |  | gsm / unicode |
| `credits` | INTEGER | no |  | credits spent for this message |
| `dlr_status` | VARCHAR(16) | no |  | delivered / undelivered / "" (no report yet) |
| `dlr_detail` | VARCHAR(120) | no |  |  |
| `dlr_at` | DATETIME | yes |  |  |
| `refunded` | BOOLEAN | no |  |  |

## Sessions and tokens

### `audit_head`

One row holding the newest audit hash. Its row lock serialises audit writers on PostgreSQL and MySQL, so the hash chain cannot fork.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `hash` | VARCHAR(64) | no |  |  |

### `rate_limits`

Fixed-window counter shared by every worker. `key` never holds raw e-mail addresses (they are hashed).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(190) | no | PK |  |
| `count` | INTEGER | no |  |  |
| `window_start` | DATETIME | yes |  |  |
| `locked_until` | DATETIME | yes |  |  |
| `strikes` | INTEGER | no |  |  |
| `updated_at` | DATETIME | no | index |  |

### `auth_sessions`

One signed-in device. The refresh token rotates on every use; the access token carries this row's id and dies with it.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `user_id` | INTEGER | no | FK users.id |  |
| `token_hash` | VARCHAR(64) | no | unique | SHA-256 of the current refresh token |
| `prev_hash` | VARCHAR(64) | no | index | the token it replaced (reuse = theft signal) |
| `rotated_at` | DATETIME | yes |  |  |
| `device` | VARCHAR(120) | no |  |  |
| `ip` | VARCHAR(45) | no |  |  |
| `user_agent` | VARCHAR(200) | no |  |  |
| `created_at` | DATETIME | no |  |  |
| `last_used_at` | DATETIME | no |  |  |
| `expires_at` | DATETIME | no |  |  |
| `revoked_at` | DATETIME | yes |  |  |
| `revoked_reason` | VARCHAR(30) | no |  |  |

### `auth_tokens`

Single-use token sent by e-mail or SMS: password reset (kind=reset) or e-mail verification (kind=verify).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `user_id` | INTEGER | no | FK users.id |  |
| `kind` | VARCHAR(8) | no | index |  |
| `token_hash` | VARCHAR(64) | no | unique |  |
| `expires_at` | DATETIME | no |  |  |
| `used_at` | DATETIME | yes |  |  |
| `created_at` | DATETIME | no |  |  |
| `ip` | VARCHAR(45) | no |  |  |

## Agency contracts

### `contracts`

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `kind` | VARCHAR(12) | no |  | lift / generator / cctv / fire / pest / other |
| `title` | VARCHAR(160) | no |  |  |
| `vendor_id` | INTEGER | yes | FK vendors.id |  |
| `vendor_name` | VARCHAR(100) | no |  | used when the vendor is not in the vendor list |
| `start_date` | DATE | no |  |  |
| `end_date` | DATE | no | index |  |
| `annual_cost` | BIGINT | no |  | paisa per year |
| `interval_days` | INTEGER | no |  | a service visit is due this many days after the last one |
| `status` | VARCHAR(8) | no |  | active / ended |
| `note` | TEXT | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

### `contract_visits`

One service visit by the vendor. cost is optional; 'create expense' turns it into a finance Expense (expense_id).

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `contract_id` | INTEGER | no | FK contracts.id |  |
| `visited_on` | DATE | no | index |  |
| `technician` | VARCHAR(100) | no |  |  |
| `notes` | TEXT | no |  |  |
| `cost` | BIGINT | no |  | paisa, 0 = covered by the annual fee |
| `expense_id` | INTEGER | yes | FK expenses.id |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

### `contract_docs`

The signed contract, or a visit report. Stored under uploads/contracts/<property>/.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `contract_id` | INTEGER | no | FK contracts.id |  |
| `visit_id` | INTEGER | yes | FK contract_visits.id |  |
| `kind` | VARCHAR(10) | no |  | contract / report / other |
| `filename` | VARCHAR(160) | no |  |  |
| `stored` | VARCHAR(80) | no |  |  |
| `content_type` | VARCHAR(60) | no |  |  |
| `size` | INTEGER | no |  |  |
| `created_by` | INTEGER | yes |  |  |
| `created_at` | DATETIME | no |  |  |

## Setup wizard and deletion requests

### `deletion_requests`

A person asking FlatWise to erase their personal details. Processing anonymises the account; ledger rows stay balanced.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `user_id` | INTEGER | no | index | no FK on purpose: the row outlives the user's details |
| `status` | VARCHAR(10) | no | index | pending / completed / rejected / cancelled |
| `reason` | VARCHAR(300) | no |  |  |
| `requested_at` | DATETIME | no |  |  |
| `processed_at` | DATETIME | yes |  |  |
| `processed_by` | INTEGER | yes |  |  |
| `note` | TEXT | no |  | why it was rejected, or what was done |

### `setup_progress`

One row per building that is (or was) in the setup wizard. Saved on the server so a person can stop and continue on another phone.

| Column | Type | Null | Key | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | PK |  |
| `property_id` | INTEGER | no | FK properties.id |  |
| `steps` | JSON | no |  | {"building": "done" / "skipped"}; a missing step is still to do |
| `data` | JSON | no |  | small answers: {"due_day": 10, "reminders": {"enabled": true, "steps": [...]}} |
| `completed_at` | DATETIME | yes |  |  |
| `dismissed_at` | DATETIME | yes |  | the dashboard card was hidden |
| `created_at` | DATETIME | no |  |  |
| `updated_at` | DATETIME | no |  |  |
| `updated_by` | INTEGER | yes |  |  |
