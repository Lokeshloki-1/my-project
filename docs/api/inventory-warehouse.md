# Inventory & Warehouse API — Goods Receipt → Inspection → Stock Allocation

Fifth module of the textile flow (raw materials). Backend: `backend/apps/stores/` · Frontend: `frontend/src/pages/{GoodsReceipts,GoodsReceiptDetail,MaterialStock,Allocation}.jsx`.
Warehouses are shared with the finished-goods stock (`apps/inventory`, `/api/warehouses/`). Auth and errors as in the [buyer onboarding API](buyer-onboarding.md).

```
Supplier PO (sent) ─▶ GRN draft ─submit─▶ received (awaiting inspection) ─inspect─▶ inspected
                                                       accepted qty → stock (at PO price), rejected → return to supplier
Stock: on_hand (physical) · allocated (reserved for orders) · available = on_hand − allocated
Allocation (confirmed order): active ─issue─▶ issued (leaves the store)   ─release─▶ released (free again)
```

Rules enforced by the database as well as the app: on hand ≥ 0, allocated ≤ on hand, inspected accepted + rejected = received. Every on-hand change writes a permanent `MaterialMovement` with the running balance; stock rows are locked while they change.

## Materials — `/api/materials/`
One row per stock item: `code` (`MAT-000001`), `category` (BOM categories), `description`, `colour`, `unit`, `reorder_level`, plus totals `on_hand`, `allocated`, `value`, `is_low`.
Created automatically on the first goods receipt of a PO line (matched case-insensitively on category + description + colour + unit). Managers edit; only `reorder_level` can change once there are movements.

## Goods receipts — `/api/goods-receipts/`

`GET /goods-receipts/receivable/?purchase_order=5` → the PO's lines with `ordered_qty`, `received_qty` (submitted GRNs), `accepted_qty`, `open_qty`, `unit_price`.

```json
POST /api/goods-receipts/
{"purchase_order": 5, "warehouse": 3, "received_on": "2026-12-01", "challan_no": "DC-4471",
 "invoice_no": "EOM/918", "vehicle_no": "TN 33 AB 4521", "notes": "",
 "lines": [{"po_line": 11, "received_qty": "2000", "lot_no": "DL-8812", "rolls": 80}]}
```

- The PO must be **sent**; the warehouse must be active and of the PO's company; each PO line once per GRN.
- A line may receive up to the PO quantity **+10%** minus what earlier submitted GRNs received. Drafts don't count until submitted, and submit checks again.
- Editable and deletable while `draft`.

| Action (POST) | Body | Rules |
|---|---|---|
| `/goods-receipts/{id}/submit/` | — | draft → received. Nothing is in stock yet. |
| `/goods-receipts/{id}/inspect/` | `{"notes": "4-point on 10% of rolls", "results": [{"line": 21, "accepted_qty": "1950", "rejected_qty": "50", "remarks": "Holes in 2 rolls"}]}` | received → inspected. A result for every line; accepted + rejected = received; rejections need remarks. Accepted quantity is booked into stock at the PO line price. |

Lines return `accepted_qty`, `rejected_qty`, `result` (`pending`, `passed`, `partial`, `failed`), `remarks`, `material`, `material_code`. Supplier PO lines (`/api/purchase-orders/{id}/`) now also show `received_qty` and `accepted_qty`.

## Stock — `/api/material-stock/`, `/api/material-movements/`
- `GET /material-stock/` per material × warehouse: `on_hand`, `allocated`, `available`, `average_cost`, `value`. Filters: `warehouse`, `material`, `material__category`, `material__company`, `on_hand__gt`.
- `GET /material-stock/summary/` → `{stock_value, low_stock, awaiting_inspection, allocations_active}`.
- `POST /material-stock/adjust/` (manager/admin) `{"material": 3, "warehouse": 3, "new_quantity": "398", "reason": "Stock count"}` — sets on hand to the counted quantity; can't go below what is allocated.
- `GET /material-movements/` — the ledger (read-only): `movement_type` (`receipt`, `issue`, `adjustment`), `quantity` (+ in / − out), `balance_after`, `unit_cost`, `reference`, `note`.

Value uses the moving average cost: receipts add at the PO price, issues and negative adjustments take out at the average.

## Allocation — `/api/material-allocations/`

- `POST /material-allocations/` `{"order": 2, "material": 3, "warehouse": 3, "quantity": "1450", "requirement_line": 7, "note": ""}` — order must be confirmed; quantity ≤ free stock in that warehouse.
- `GET /material-allocations/plan/?requirement=3` → per requirement line: matching `material`, `required_qty`, `allocated_qty` (active, not yet issued), `issued_qty`, `still_needed`, and `stock` (free per warehouse).
- `POST /material-allocations/auto/` `{"requirement": 3, "warehouse": 3}` — allocates free stock to every line that still needs it, preferred warehouse first (400 if there is nothing to allocate).
- `POST /material-allocations/{id}/issue/` `{"quantity": "500"}` (default: all remaining) — issue to production; stock goes down.
- `POST /material-allocations/{id}/release/` `{"quantity": "500"}` — back to free stock.

An allocation is `active` until nothing remains; then `issued` (if anything was issued) or `released`. Allocations can't be edited or deleted.
