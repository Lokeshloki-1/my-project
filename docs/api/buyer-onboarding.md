# Buyer Onboarding API

First module of the textile ERP flow:

```
Buyer Enquiry → Buyer Registration → Buyer Profile → Contact Details → Buyer Requirements → Credit Verification → Buyer Approval
```

Backend: `backend/apps/buyers/` · Frontend: `frontend/src/pages/Buyer*.jsx`, `frontend/src/components/buyers/`

When a buyer is **approved**, a `sales.Customer` is created and linked to it. Only approved buyers
become customers, so only they can receive quotations, sales orders, invoices and DDP shipments.

## Basics

- All endpoints are under `/api/` and need `Authorization: Bearer <access token>` (get it from `POST /api/auth/login/`).
- Lists are paginated: `{ "count": 12, "next": "...", "previous": null, "results": [...] }`. `?page=2`, `?page_size=100` (max 500), `?search=`, `?ordering=`.
- Errors:

| Status | When | Body |
|---|---|---|
| 400 | Invalid field values, or a step is incomplete | `{"field": ["message"]}` · submit: `{"missing": ["Address", ...], "detail": "..."}` |
| 403 | Your role may not do this | `{"detail": "..."}` |
| 404 | Not found | `{"detail": "..."}` |
| 409 | Record is in the wrong status for this action (e.g. approve a buyer that has not passed credit) | `{"detail": "..."}` (code `invalid_transition`) |

## Roles

| Action | Sales | Accountant | Manager / Admin |
|---|:-:|:-:|:-:|
| Read everything | ✓ | ✓ | ✓ |
| Create / edit enquiries, buyers, contacts, requirements (while editable) | ✓ | ✓ | ✓ |
| Submit for credit check | ✓ | ✓ | ✓ |
| Record credit check | | ✓ | ✓ |
| Approve / reject / reopen buyer | | | ✓ |
| Edit a buyer after submission | | | ✓ |

## Buyer status machine

Status is **read-only** on every endpoint. It changes only through the action endpoints, and each change is written to the timeline.

```
registered ──submit──▶ pending_credit ──credit pass──▶ pending_approval ──approve──▶ approved
     ▲                   │      ▲                              │
     │             credit fail  └── submit again               │ reject (from any open status)
     │                   ▼                                     ▼
     │             credit_failed                            rejected
     └───────────────── reopen (manager) ◀─────────────────────┘
```

| Status | Meaning | Editable by sales |
|---|---|:-:|
| `registered` | Being filled in | ✓ |
| `pending_credit` | Submitted, waiting for accounts | |
| `credit_failed` | Credit check failed — fix and submit again | ✓ |
| `pending_approval` | Credit passed, waiting for a manager | |
| `approved` | Customer created | |
| `rejected` | Stopped; a manager can reopen | |

## Enquiries — `/api/buyer-enquiries/`

CRUD. Filters: `company`, `status`, `source`, `country`, `assigned_to`. Search: number, buyer name, contact, email, country, products.

```json
POST /api/buyer-enquiries/
{
  "company": 1, "source": "trade_fair", "buyer_name": "Fjord Kids AS", "contact_name": "Ingrid Olsen",
  "email": "ingrid@fjord.example", "phone": "", "country": "Norway",
  "product_interest": "Organic kidswear, 180 GSM jersey", "expected_volume": 40000,
  "received_on": "2026-11-27", "assigned_to": null, "status": "new", "notes": ""
}
→ 201 { "id": 10, "enquiry_no": "ENQ-2026-000010", "company_name": "...", "assigned_to_name": null,
        "status": "new", "reject_reason": "", "buyer_id": null, ... }
```

- `status` can be set to `new` or `qualified` only. Converted and rejected enquiries cannot be edited.
- `POST /api/buyer-enquiries/{id}/convert/` → creates a `registered` buyer (name, country, notes, plus the contact as primary contact if it has an email or phone). Returns the **buyer detail** (201). Calling it again returns the same buyer (200). A rejected enquiry gives 409.
- `POST /api/buyer-enquiries/{id}/reject/` `{"reason": "Volume too small"}` → the enquiry. Reason is required.

## Buyers — `/api/buyers/`

Filters: `company`, `status`, `country`, `buyer_type`. Search: code, names, country, city, contact name/email.

**Create / update** (list rows have the same fields except the detail-only ones):

```json
POST /api/buyers/
{
  "company": 1, "legal_name": "Coastline Retail Ltd", "trade_name": "", "buyer_type": "retailer",
  "country": "United Kingdom", "city": "Leeds", "address": "1 Mill Road", "tax_id": "GB123456789",
  "website": "", "year_established": 1998, "annual_turnover": "25000000", "preferred_currency": "GBP",
  "default_incoterm": "FOB", "bank_name": "HSBC", "notes": ""
}
```

**Detail** (`GET /api/buyers/{id}/`, and the response of every action):

```json
{
  "id": 7, "buyer_code": "BYR-2026-000007", "status": "pending_approval", "status_label": "Pending approval",
  "enquiry": 10, "enquiry_no": "ENQ-2026-000010", "customer_id": null,
  "approved_by": null, "approved_by_name": null, "approved_at": null, "rejection_reason": "",
  "primary_contact": { "name": "Ingrid Olsen", "email": "ingrid@fjord.example", "phone": "" },
  "contacts": [ { "id": 3, "buyer": 7, "name": "Ingrid Olsen", "department": "merchandising", "is_primary": true, ... } ],
  "requirement": { "id": 2, "product_categories": ["kidswear"], "certifications": ["GOTS"], "gsm_min": 160, ... },
  "latest_credit_check": { "result": "pass", "approved_limit": "60000.00", "currency": "USD", "payment_terms": "lc_sight", ... },
  "onboarding": [
    { "key": "enquiry",      "label": "Buyer Enquiry",       "optional": true,  "done": true,  "missing": [] },
    { "key": "registration", "label": "Buyer Registration",  "optional": false, "done": true,  "missing": [] },
    { "key": "profile",      "label": "Buyer Profile",       "optional": false, "done": true,  "missing": [] },
    { "key": "contacts",     "label": "Contact Details",     "optional": false, "done": true,  "missing": [] },
    { "key": "requirements", "label": "Buyer Requirements",  "optional": false, "done": true,  "missing": [] },
    { "key": "credit",       "label": "Credit Verification", "optional": false, "done": true,  "missing": [] },
    { "key": "approval",     "label": "Buyer Approval",      "optional": false, "done": false, "missing": ["Approval by a manager"] }
  ],
  "allowed_actions": ["edit", "approve", "reject"],
  ...all profile fields
}
```

- `onboarding` drives the stepper; `missing` lists what to fill in, in plain words.
- `allowed_actions` is computed for the **current user**: any of `edit`, `submit`, `record_credit_check`, `approve`, `reject`, `reopen`, `delete`. Show a button only when its action is in the list.

**Actions** (all `POST`, return the buyer detail):

| Endpoint | Body | Rules |
|---|---|---|
| `/api/buyers/{id}/submit/` | — | From `registered` or `credit_failed`. Needs legal name, country, address, city, preferred currency, a primary contact with email, and requirements with ≥1 category. Otherwise 400 with `missing`. |
| `/api/buyers/{id}/approve/` | `{"reason": "optional note"}` | Manager/admin. From `pending_approval` with a passing latest credit check. Creates the Customer. Repeating it on an approved buyer is a no-op. |
| `/api/buyers/{id}/reject/` | `{"reason": "required"}` | Manager/admin. From any open status. |
| `/api/buyers/{id}/reopen/` | `{"reason": "optional"}` | Manager/admin. From `rejected` back to `registered`. |

Other:
- `GET /api/buyers/{id}/timeline/` → `[{ "from_status": "registered", "to_status": "pending_credit", "note": "...", "user_name": "Sales", "created_at": "..." }]` (oldest first).
- `GET /api/buyers/pipeline/` (same filters as the list) → `{ "stages": [{ "status": "registered", "label": "Registered", "count": 1 }, ...], "total": 6, "open_enquiries": 2 }`.
- `DELETE /api/buyers/{id}/` only while `registered` and with no credit history (else 409). The enquiry goes back to `qualified`.

## Contacts — `/api/buyer-contacts/`

CRUD, filter `?buyer=`. Fields: `buyer, name, designation, department, email, phone, is_primary`.
- Email or phone is required.
- Setting `is_primary: true` makes the old primary non-primary. The first contact becomes primary automatically. Deleting the primary promotes another contact.
- 409 when the buyer is locked (after submission, unless you are a manager).

## Requirements — `/api/buyer-requirements/`

One per buyer (second POST → 400). Filter `?buyer=`.

```json
{
  "buyer": 7, "product_categories": ["knits", "kidswear"], "fabric_composition": "100% organic cotton",
  "gsm_min": 160, "gsm_max": 200, "size_range": "2-14Y", "annual_volume": 40000,
  "target_price_min": "3.50", "target_price_max": "6.00", "price_currency": "USD",
  "certifications": ["GOTS", "OEKO-TEX"], "packaging": "", "labelling": "", "testing_lab": "SGS",
  "delivery_port": "Chennai", "payment_terms_requested": "LC at sight", "notes": ""
}
```

Min must be ≤ max for GSM and price. Unknown categories/certifications → 400.

## Credit checks — `/api/credit-checks/`

List, retrieve and create only — no edit or delete (audit record). Filter `?buyer=`, `result`, `risk_rating`.
Create needs accountant, manager or admin, and the buyer must be `pending_credit` (else 409).

```json
POST /api/credit-checks/
{
  "buyer": 7, "requested_limit": "80000", "approved_limit": "60000", "currency": "USD",
  "payment_terms": "lc_sight", "risk_rating": "low", "bank_reference": "DNB confirms good standing",
  "trade_references": "", "ecgc_cover": false, "result": "pass", "remarks": ""
}
```

- `pass` needs `approved_limit` > 0 and moves the buyer to `pending_approval`.
- `fail` forces `approved_limit` to 0 and moves the buyer to `credit_failed`.

## Choice values

| Field | Values |
|---|---|
| enquiry `source` | `email`, `website`, `trade_fair`, `agent`, `referral`, `other` |
| enquiry `status` | `new`, `qualified`, `converted`, `rejected` |
| `buyer_type` | `brand`, `retailer`, `importer`, `wholesaler`, `buying_agent` |
| `default_incoterm` | `EXW`, `FOB`, `CIF`, `DDP` |
| contact `department` | `merchandising`, `sourcing`, `qa`, `accounts`, `logistics`, `management` |
| `product_categories` | `knits`, `wovens`, `denim`, `activewear`, `innerwear`, `kidswear`, `home_textiles`, `fabric`, `yarn` |
| `certifications` | `GOTS`, `OEKO-TEX`, `BSCI`, `SEDEX`, `WRAP`, `GRS`, `OCS`, `BCI`, `ISO 9001` |
| `payment_terms` | `advance`, `lc_sight`, `lc_usance`, `tt_30`, `tt_60`, `tt_90`, `da`, `dp` |
| `risk_rating` | `low`, `medium`, `high` |
| credit `result` | `pass`, `fail` |

The frontend copy of these lists is `frontend/src/components/buyers/constants.js`; keep it in sync with `backend/apps/buyers/models.py`.

## Screens

| Route | Screen |
|---|---|
| `/buyer-enquiries` | Enquiry list with status filter; edit modal has **Convert to buyer** and **Reject** |
| `/buyers/pipeline` | Board with one column per status |
| `/buyers` | Buyer list with status filter; **+ New** registers a buyer and opens it |
| `/buyers/:id` | Header with status and role-based action buttons, 7-step stepper, tabs: Profile · Contacts · Requirements · Credit · Timeline |
| `/` | Dashboard card with onboarding counts and "waiting for your approval" |

Screenshots: `docs/screenshots/`.
