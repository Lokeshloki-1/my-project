# Finance & Accounts API — Sales Invoice → Payment → Receivables → Profit

Ninth and last module of the textile flow (export sales). Backend: `backend/apps/finance/` · Frontend: `frontend/src/pages/{ExportInvoices,Receivables,OrderProfit}.jsx`.
Domestic INR invoices with GST stay in `apps/billing` (menu "Domestic Billing"); export money is never mixed into them.
Write access: admins, managers and accountants (`IsFinanceOrReadOnly`); everyone logged in can read. Errors as in the [buyer onboarding API](buyer-onboarding.md).

```
invoice amount  = Σ shipped pcs × order price per style          (buyer's currency)
invoice INR     = amount × invoice exchange rate                   (shipping-bill rate)
receipt INR     = amount credited × realised rate
gain / loss     = (amount credited + bank charges) × (realised rate − invoice rate)
balance         = amount − Σ (credited + bank charges)             open → partly paid → paid
```

## Export invoices — `/api/export-invoices/`
- `POST /export-invoices/create-from-shipment/` `{"shipment": 3, "exchange_rate": "83.60", "invoice_date": null}` — shipment must be shipped or delivered. Uses the shipment's commercial invoice number and lines. 201 (200 with the existing invoice if already raised).
- Due date from the order's payment terms: advance 0 days, LC at sight +7, TT 30/60/90, LC usance and DA +60, DP +15. `PATCH {"due_date", "notes"}` may change it (not before the invoice date).
- Detail: `amount`, `amount_inr`, `amount_received`, `bank_charges`, `balance`, `balance_inr`, `days_overdue`, `lines`, `receipts`, `gain_loss_inr`, `allowed_actions` (`record_receipt`, `cancel`).
- `POST /{id}/cancel/` `{"reason"}` — managers/admins, only without receipts. `GET /{id}/pdf/` — the commercial invoice PDF.
- `GET /export-invoices/ageing/?as_of=` — open invoices in buckets *not due, 1–30, 31–60, 61–90, over 90 days* past due, per buyer (INR at invoice rate) with the buyer's approved credit limit and `over_limit`.
- `GET /export-invoices/summary/` — `receivable_inr`, `overdue_inr`, `overdue_invoices`, `invoiced_this_month_inr`, `collected_this_month_inr`, `exchange_gain_loss_inr`, `shipped_not_invoiced`.

## Receipts — `/api/export-receipts/`
`POST {"invoice": 2, "received_on": "2026-11-28", "amount": "1200", "bank_charges": "18", "exchange_rate": "84.15", "method": "tt", "bank_reference": "FIRC/…", "note": ""}`
- `method`: `tt`, `lc`, `da_dp`, `advance`. Amount + bank charges ≤ balance; not a future date.
- Returns `amount_inr` and `exchange_gain_loss_inr`. `DELETE` — managers/admins (the invoice is recalculated).

## Order expenses — `/api/order-expenses/`
CRUD: `order, date, category` (`freight`, `clearing`, `courier`, `testing`, `commission`, `bank`, `other`), `amount_inr`, `note`.

## Order profit — `/api/order-profit/` (list) and `/api/order-profit/{order_id}/`
```
revenue      invoiced INR (non-cancelled invoices)
− materials  material issued to production for the order (stores), attributed to the styles its requirement line serves,
             × each style's shipped share of its ordered quantity      (the rest is reported as materials_in_wip_inr)
− conversion cost-sheet CMT, washing, print/embroidery, testing and packing per piece × shipped pcs, at the invoice rate
− expenses   order expenses (INR)
− bank charges on receipts (at the invoice rate)
+ exchange gain / loss
= profit;  margin % of revenue;  planned margin from the cost sheets ((price − total cost) ÷ price)
```
Returns `invoiced`, `invoiced_inr`, `invoice_rate`, `received_inr`, `shipped_pcs`, `ordered_pcs`, `shipped_share_pct`, `materials_issued_inr`, `materials_in_wip_inr`, `costs` (with `expenses_by_category`), `exchange_gain_loss_inr`, `profit_inr`, `margin_pct`, `planned_margin_pct`, `styles` and `warnings`:
material allocated but not yet issued for styles that shipped (profit overstated), no material issued at all, and shipments shipped but not invoiced. The detail also lists the order's `expenses` and `invoices`.
