# Packing & Export API — Packing List → Shipping → Export Documents

Eighth module of the textile flow. Backend: `backend/apps/exports/` (PDFs in `pdf.py`) · Frontend: `frontend/src/pages/{PackingLists,ExportShipments}.jsx`.
The older DDP shipments screen (`/ddp`, `apps/ddp`) is unchanged. Auth and errors as in the [buyer onboarding API](buyer-onboarding.md).

```
Packing list (draft ─finalize─▶ finalized; a manager can reopen until it ships)
  packable per work order = min(finished good pcs, Σ passed final-inspection lots) − pcs on finalized packing lists
Export shipment: planned ─book─▶ booked ─ship─▶ shipped ─deliver─▶ delivered;  planned/booked ─cancel─▶ cancelled
```

## Packing lists — `/api/packing-lists/`

`GET /packing-lists/pack-status/?order=2` → per work order: `sizes` (in garment order), `finished`, `passed_inspection`, `packed`, `packable`.

```json
POST /api/packing-lists/
{"order": 2, "pack_date": "2026-11-27", "method": "solid", "shipping_marks": "…", "notes": "",
 "groups": [{"production_order": 3, "colourway": "Navy", "from_carton": 1, "to_carton": 10,
             "sizes": {"S": 10, "M": 20, "L": 10}, "net_weight": "6.0", "gross_weight": "6.8",
             "length_cm": "58", "width_cm": "38", "height_cm": "28"}]}
```
- `sizes` are pieces per size in **one** carton; sizes must exist on the work order.
- Carton ranges may not overlap; finalizing also needs numbering from 1 with no gaps.
- The pieces per work order may not exceed `packable` — **nothing can be packed without a passed final inspection**.
- Returns `total_cartons`, `total_pcs`, `net_weight`, `gross_weight`, `cbm` (L × W × H ÷ 1,000,000 per carton) and per group `cartons`, `pcs_per_carton`, `total_pcs`.
- Empty `shipping_marks` is filled with buyer, PO, carton number and "Made in India".

| Action | Rules |
|---|---|
| `POST /packing-lists/{id}/finalize/` | Draft; rechecks packable quantities with the order locked. |
| `POST /packing-lists/{id}/reopen/` | Managers; not once the shipment has shipped. Removes it from its shipment. |
| `GET /packing-lists/{id}/pdf/` | Packing list PDF (landscape, sizes as columns, shipping marks). |

## Export shipments — `/api/export-shipments/`

```json
POST /api/export-shipments/
{"order": 2, "mode": "sea", "packing_list_ids": [3], "port_of_loading": "Chennai, India", "port_of_discharge": "Gothenburg, Sweden",
 "final_destination": "Stockholm", "forwarder": "DHL Global Forwarding", "carrier": "Hapag-Lloyd", "etd": "2026-12-02", "eta": "2027-01-02",
 "vessel": "", "voyage": "", "container_type": "", "container_no": "", "seal_no": "", "bl_no": "", "shipping_bill_no": "",
 "shipping_bill_date": null, "hs_codes": {"NT-310": "61091000"}, "notes": ""}
```
- Packing lists must be finalized, for the same order, and not on another active shipment.
- Creating a shipment gives it a `shipment_no` (`EXP-…`), a commercial `invoice_no` (`CI-…`) and the document checklist.
- Detail adds `packing_lists`, `totals` (cartons, pcs, net/gross kg, CBM), `invoice` (per style: cartons, pcs, order price, amount, HS code; total), `documents`, `warnings` (ETD after the agreed ship date, missing HS codes, documents still pending after shipping), `allowed_actions`, `history`.
- After shipping only `notes`, `hs_codes`, `eta` and `shipping_bill_date` can change.

| Action (POST) | Needs |
|---|---|
| `/{id}/book/` | Packing lists, port of discharge, ETD, forwarder. |
| `/{id}/ship/` `{"on_board_date": "2026-11-27"}` | Vessel/flight, B/L or AWB no., shipping bill no., container type for sea; date not in the future. Sets the invoice date and marks the B/L and shipping bill documents ready. |
| `/{id}/deliver/` `{"delivered_date": "…"}` | Shipped. |
| `/{id}/cancel/` `{"reason"}` | Planned or booked; frees the packing lists. |

`GET /export-shipments/{id}/commercial-invoice/` — commercial invoice PDF (exporter, consignee, terms, routing, lines with HS codes, total and amount in words, weights and CBM).

## Export documents — `/api/export-documents/{id}/`
One row per shipment for each of: `commercial_invoice`, `packing_list`, `shipping_bill`, `bill_of_lading`, `certificate_of_origin`, `inspection_certificate`, `insurance`, `beneficiary_certificate`. `PATCH` `number`, `date`, `status` (`pending`, `ready`, `sent`, `not_needed`), `note`. The commercial invoice, packing list, B/L and shipping bill rows are filled in automatically.

## Size order
The database does not keep the order of keys in JSON size breakdowns, so sizes are always ordered by the tech pack's size list, then by garment order (0-3M … 2Y … 12Y … XS, S, M, L, XL, XXL…) — `apps.production.services.ordered_sizes`. Work orders return `size_order`.
