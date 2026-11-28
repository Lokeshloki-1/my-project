# Production Management API — Planning → Cutting → Sewing → Finishing

Sixth module of the textile flow. Backend: `backend/apps/production/` · Frontend: `frontend/src/pages/{ProductionPlan,ProductionOrderDetail,DailyOutput,ProductionLines}.jsx`.
Auth and errors as in the [buyer onboarding API](buyer-onboarding.md).

```
daily target (pcs) = operators × working minutes × efficiency % ÷ SMV
working days       = planned pcs ÷ daily target (rounded up; Sundays off)

Work order: planned ─first entry─▶ in production ─finished ≥ planned─▶ completed
                                                 └ manager closes short with a reason
            planned ─cancel─▶ cancelled
Output limits (checked with the work order locked):
  cut per size ≤ planned per size × (1 + cut allowance %, default 3)
  sewn good + sewing rejects ≤ cut
  finished good + finishing rejects ≤ sewn good
```

## Sewing lines — `/api/production-lines/`
CRUD (managers write): `company, code, name, operators, working_minutes (default 480), efficiency_pct, is_active`. A line with work orders can't be deleted (409).

## Work orders — `/api/production-orders/`

`GET /production-orders/order-lines/?order=2` — styles of a confirmed order with `quantity`, `planned` (already on non-cancelled work orders), the released tech pack, its `sizes` and `colourways`, and `production_approved`.

`GET /production-orders/capacity/?line=3&smv=9&quantity=10000&start=2026-11-27` → `{daily_target, working_days, suggested_end}`.

```json
POST /api/production-orders/
{"order": 2, "order_line": 4, "quantity": 10000, "sizes": {"S": 3000, "M": 4000, "L": 3000},
 "line": 3, "smv": "9", "planned_start": "2026-11-27", "planned_end": null, "colourway": "", "cut_allowance_pct": "3", "notes": ""}
```

- The order must be confirmed; the line active and of the order's company.
- `sizes` must add up to `quantity` and use the tech pack's sizes (the latest released tech pack of the style is linked automatically).
- A style can be planned up to its order quantity **+5%** across work orders.
- `planned_end` defaults to the capacity suggestion.
- Editable only while `planned`.

Detail adds:
- `capacity` — `{daily_target, working_days, suggested_end}`
- `progress` — `cut, cut_sizes, sewn, sewing_rejected, finished, finishing_rejected, wip_sewing, wip_finishing, balance_to_finish, percent_done`
- `warnings` — ends after shipment, less than a week before shipment, line booked by another work order, not enough days for the line's capacity, PP sample not approved, **behind plan**, projected finish after shipment at the current sewing rate
- `materials` — the order's material requirement lines with required / allocated / issued quantity (from the stores)
- `entries`, `allowed_actions` (`edit`, `cancel`, `record`, `complete`), `history`

| Action (POST) | Body | Rules |
|---|---|---|
| `/production-orders/{id}/entries/` | cutting: `{"stage": "cutting", "date": "…", "sizes": {"S": 1500}, "lay_no": "LAY-A1", "fabric_used": "545"}` · sewing / finishing: `{"stage": "sewing", "date": "…", "quantity": 900, "rejected": 10, "line": 3, "remarks": ""}` | Planned or in production; not a future date; limits above. First entry starts the work order; finishing that reaches the planned quantity completes it. |
| `/production-orders/{id}/complete/` | `{"reason": "…"}` | Manager/admin; in production; reason required if short. |
| `/production-orders/{id}/cancel/` | `{"reason": "…"}` | Only before any output. |

`GET /production-orders/daily/?date=2026-11-27` → per active line: running work order, `smv`, `target`, `sewn`, `rejected`, `achievement_pct`, `efficiency_pct` (= pieces × SMV ÷ operator minutes); plus totals per stage.

## Entries — `/api/production-entries/`
List (filters `production_order`, `stage`, `date`, `line`). `DELETE` is manager-only and refused if a later stage already used those pieces (delete the later entries first). Entries are never edited.
