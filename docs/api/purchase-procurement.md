# Purchase & Procurement API — Material Requirement → RFQ → Supplier PO

Fourth module of the textile flow. Backend: `backend/apps/procurement/` · Frontend: `frontend/src/pages/{Suppliers,MaterialRequirements,MaterialRequirementDetail,RFQs,RFQDetail,PurchaseOrders,PurchaseOrderDetail}.jsx`.
Auth, pagination and errors as in the [buyer onboarding API](buyer-onboarding.md) (400 / 403 / 409).

```
Confirmed order ──generate──▶ Material requirement (draft ─approve (manager)─▶ approved)
                                   │ selected open lines
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
     RFQ (draft → sent → awarded | cancelled)   Supplier PO (direct)
        quotes from invited suppliers               │
        award a complete quote ──▶ draft PO ─────────┘
Supplier PO: draft ─approve (manager)─▶ approved ─send─▶ sent;  cancel frees the quantity
```

## Suppliers — `/api/suppliers/`

CRUD. Fields: `company, name, contact_name, email, phone, city, country, address, tax_id, categories, payment_terms, lead_time_days, is_active`.
`categories` uses the BOM categories (`fabric`, `trim`, `label`, `thread`, `print`, `packaging`, `other`). A supplier with RFQs/POs can't be deleted (409) — set `is_active: false`.

## Material requirements — `/api/material-requirements/`

`POST /material-requirements/generate/` `{"order": 12, "wastage_pct": "5"}` → for a **confirmed** order (201; 200 with the existing one if already made).

```
required qty = Σ over the order's styles (order pcs × BOM consumption) × (1 + wastage %)   (rounded up to 0.01)
```

- Uses the latest **released** tech pack of each style (same buyer and style number). Same material (type + description + colour + unit) across styles is merged; `styles` lists them.
- `warnings` lists styles without a released tech pack, BOM items without consumption and styles whose PP sample isn't approved yet.
- `needed_by` defaults to the order's ship date − 45 days.

Editable while `draft`: `title`, `needed_by`, `notes`, `lines`. Lines are matched by `id` (send the id to keep a line; omit it to add one; leave a line out to remove it). Manual requirements (no order) can be created with `POST /material-requirements/`.

Each line returns `required_qty`, `net_qty` (before wastage), `ordered_qty` (Σ non-cancelled PO lines), `open_qty`, `rfq_nos`, `po_nos`. The requirement returns `progress: {lines, fully_ordered}`.

| Action (POST) | Who | Rules |
|---|---|---|
| `/{id}/recalculate/` | anyone | Draft, from an order, no line on an RFQ/PO yet. Rebuilds from current tech packs. |
| `/{id}/approve/` | manager/admin | Needs a line with quantity > 0. Approved requirements are locked. |
| `/{id}/reopen/` | manager/admin | Approved → draft. |

## RFQs — `/api/rfqs/`

```json
POST /api/rfqs/
{"company": 1, "requirement": 3, "title": "Fabric for OC-2026-000002", "reply_by": "2026-12-02",
 "required_by": "2027-01-24", "currency": "INR", "notes": "GOTS certified",
 "suppliers": [1, 3],
 "lines": [{"requirement_line": 7, "category": "fabric", "description": "200 GSM stripe jersey", "colour": "", "unit": "kg", "quantity": "2541"}]}
```

Requirement lines must come from an **approved** requirement of the same company; suppliers must be active and of the same company.

| Action | Body | Rules |
|---|---|---|
| `POST /rfqs/{id}/send/` | — | Draft → sent. Needs lines and suppliers. |
| `POST /rfqs/{id}/quotes/` | `{"supplier": 3, "currency": "INR", "payment_terms": "45 days", "valid_until": "…", "notes": "", "lines": [{"rfq_line": 9, "unit_price": "598", "lead_time_days": 21}]}` | While sent, invited suppliers only. Replaces that supplier's quote. Lines left out = not quoted (partial). |
| `POST /rfqs/{id}/award/` | `{"supplier": 3}` | Supplier must have a complete quote. Creates a draft PO from their prices (201, returns the PO). Idempotent. |
| `POST /rfqs/{id}/cancel/` | `{"reason": "…"}` | Draft or sent. |

Detail includes `comparison`:
```json
{"lines": [{"rfq_line": 9, "offers": [{"supplier": 3, "unit_price": "598.00", "amount": "1519518.00", "lead_time_days": 21, "best": true}]}],
 "suppliers": [{"supplier": 3, "supplier_name": "…", "currency": "INR", "total": "1546818.00", "complete": true, "lowest": true, "payment_terms": "…"}]}
```
`best` = lowest unit price on that line; `lowest` = lowest total among complete quotes.

## Supplier POs — `/api/purchase-orders/`

```json
POST /api/purchase-orders/
{"supplier": 4, "requirement": 3, "order_date": "2026-11-27", "delivery_date": "2026-12-10",
 "lines": [{"requirement_line": 8, "category": "label", "description": "Woven main label", "unit": "pc", "quantity": "10500", "unit_price": "2.40"}]}
```

Defaults: `currency` = company currency, `payment_terms` = supplier's. Lines return `required_qty` and `ordered_total` (all non-cancelled ordering of that requirement line, this PO included) so over-ordering is visible. Detail also returns `company_name`, `company_address`, `supplier_address` for printing.

| Action (POST) | Who | Rules |
|---|---|---|
| `/purchase-orders/{id}/approve/` | manager/admin | Draft, has lines, supplier active. Over-ordering is allowed but written in the history note. |
| `/purchase-orders/{id}/send/` | anyone | Approved → sent. |
| `/purchase-orders/{id}/cancel/` | `{"reason"}` required | Draft: anyone. Approved/sent: manager/admin. Frees the ordered quantity. |

Delete: draft POs that did not come from an RFQ award.

## Next

Goods receipt against a PO (quantities received, inspection, stock) belongs to the Inventory & Warehouse module.
