# Costing → Quotation → Order Confirmation API

Second module of the textile flow. Backend: `backend/apps/merchandising/` · Frontend: `frontend/src/pages/{CostSheets,CostSheetDetail,Quotations,QuotationDetail,Orders,OrderDetail}.jsx`, `frontend/src/components/merch/`.

Auth, pagination and error shapes are the same as the [buyer onboarding API](buyer-onboarding.md): 400 field errors, 403 wrong role, 409 wrong status (`invalid_transition`) or over credit limit (`credit_limit_exceeded`).

```
Cost sheet (draft → approved by manager)
      ↓ only approved cost sheets of the same buyer and currency
Quotation (draft → sent → accepted | rejected | cancelled), only for approved buyers
      ↓ POST /quotations/{id}/create-order/
Order confirmation (draft → confirmed | cancelled), credit limit checked on confirm
```

## Cost sheets — `/api/cost-sheets/`

CRUD while `draft`. Filters: `company`, `buyer`, `status`, `category`, `currency`. Search: number, style, buyer name.

```json
POST /api/cost-sheets/
{
  "buyer": 1, "style_no": "NT-101", "style_name": "Kids organic tee", "category": "kidswear",
  "fabric_composition": "100% organic cotton", "gsm": 180, "size_range": "2-12Y", "quantity": 6000,
  "currency": "USD", "overhead_pct": "8", "margin_pct": "15", "commission_pct": "3",
  "lines": [
    {"category": "fabric", "description": "180 GSM jersey", "unit": "kg", "consumption": "0.18", "rate": "6.20", "wastage_pct": "8"},
    {"category": "cmt", "description": "Cut, make, trim", "unit": "pc", "consumption": "1", "rate": "0.55"}
  ]
}
```

`currency` defaults to the buyer's preferred currency. Sending `lines` replaces all lines. The server calculates every amount (per piece):

```
line amount  = consumption × rate × (1 + wastage % / 100)
direct cost  = Σ line amounts
overhead     = direct cost × overhead %
total cost   = direct cost + overhead
margin       = total cost × margin %
FOB price    = (total cost + margin) ÷ (1 − commission % / 100)
commission   = FOB price − (total cost + margin)
```

Response adds `cost_no` (`CS-2026-000001`), `direct_cost`, `overhead_amount`, `total_cost`, `margin_amount`, `commission_amount`, `fob_price`, `status`, `allowed_actions`, `history`.

Line `category`: `fabric`, `trims`, `accessories`, `print_embroidery`, `washing`, `cmt`, `testing`, `packing`, `freight`, `other`.

| Action (POST) | Who | Rules |
|---|---|---|
| `/cost-sheets/{id}/approve/` | manager/admin | Needs lines and a price > 0. Approved sheets are locked. |
| `/cost-sheets/{id}/reopen/` | manager/admin | Back to draft, only if no sent/accepted quotation or order uses it. |
| `/cost-sheets/{id}/copy/` | anyone | New draft with the same lines (revised costing / similar style). |

## Quotations — `/api/quotations/`

CRUD while `draft`. Filters: `company`, `buyer`, `status`, `quote_date__gte/lte`.

```json
POST /api/quotations/
{
  "buyer": 1, "quote_date": "2026-11-27", "delivery_port": "Chennai", "delivery_date": "2027-02-10",
  "lines": [{"cost_sheet": 3, "quantity": 6000}]
}
```

- The buyer must be **approved**. Each line's cost sheet must be approved, for the same buyer, in the quotation currency.
- Defaults: `valid_until` = date + 30 days, `currency` = buyer's currency, `incoterm` = buyer's default, `payment_terms` = from the buyer's credit check, line `unit_price` = cost sheet FOB, `style_no`/`description` from the cost sheet.
- Each line returns `cost_fob_price`, `cost_total_cost` and `below_cost` (price under total cost).
- `is_expired` is true for a draft/sent quotation past `valid_until`.

| Action (POST) | Body | Rules |
|---|---|---|
| `/quotations/{id}/send/` | — | Draft → sent. Needs lines, an approved buyer, not expired. |
| `/quotations/{id}/reopen/` | — | Sent → draft, to change it. |
| `/quotations/{id}/accept/` | `{"note": "..."}` | Sent → accepted. Not when expired. |
| `/quotations/{id}/reject/` | `{"reason": "required"}` | Sent → rejected. |
| `/quotations/{id}/cancel/` | `{"reason": "..."}` | Draft or sent → cancelled. |
| `/quotations/{id}/create-order/` | — | Accepted → creates the order confirmation (201), or returns the existing one (200). |

## Order confirmations — `/api/order-confirmations/`

List, retrieve and update while `draft`. No create (use `create-order`) and no delete.
Editable: `buyer_po_no`, `po_date`, `ship_date`, `delivery_port`, `notes`, `lines` (quantities and prices can be changed to match the buyer's PO).

The detail includes `credit`:

```json
"credit": {
  "has_limit": true, "limit": "60000.00", "currency": "USD", "currency_matches": true,
  "exposure": "35850.00", "this_order": "31500.00", "after_order": "67350.00",
  "available": "24150.00", "within_limit": false, "payment_terms": "lc_sight"
}
```

`exposure` = the buyer's other **confirmed** orders in the same currency. Cancelled orders free their credit.

| Action (POST) | Body | Rules |
|---|---|---|
| `/order-confirmations/{id}/confirm/` | `{"override_reason": "..."}` | Needs `buyer_po_no`, `ship_date` and lines (400 lists what's missing). Over the limit, no limit, or a different currency → 409 `credit_limit_exceeded`, unless a manager/admin sends `override_reason`; the override is recorded on the order. |
| `/order-confirmations/{id}/cancel/` | `{"reason": "required"}` | Draft: anyone. Confirmed: manager/admin. |

## Not yet connected

Order confirmations are kept in their own table, in the buyer's currency. They do not yet create
sales orders, stock movements or invoices: the existing sales order, invoice and report screens work
in INR with GST. They will be connected when the Finance & Accounts module (export invoices with
currency) is built.
