# Quality Management API — Inline QC → Final Inspection → Defect Control

Seventh module of the textile flow. Backend: `backend/apps/quality/` (AQL table in `aql.py`) · Frontend: `frontend/src/pages/{InlineQC,FinalInspections,DefectControl,DefectTypes}.jsx`.
Auth and errors as in the [buyer onboarding API](buyer-onboarding.md).

```
Inline QC:   DHU = defects ÷ pieces checked × 100   → green ≤ 2.5 · amber ≤ 5 · red > 5 (opens a corrective action)
Final (AQL): lot passes when critical = 0, major ≤ accept(AQL major), minor ≤ accept(AQL minor), checklist all OK
             failed → corrective action + re-inspection (round 2, …)
Corrective action: open ─close (manager, root cause + action)─▶ closed
```

## Defect library — `/api/defect-types/`
`company, code, name, category` (`sewing`, `fabric`, `measurement`, `finishing`, `print`, `trims`, `packing`, `other`), `severity` (`minor`, `major`, `critical` — the default when recording), `is_active`. Managers edit; recorded types can't be deleted (409).
`seed_demo` creates a standard list of 20 garment defects (`apps.quality.services.ensure_default_defects`).

## Inline QC — `/api/inline-inspections/`
Create and read only (a check is a record of what was found).

```json
POST /api/inline-inspections/
{"production_order": 3, "line": 3, "date": "2026-11-27", "operation": "Side seam", "operator": "Op 21",
 "pieces_checked": 30, "defective_pieces": 2, "action_taken": "Tension corrected",
 "defects": [{"defect_type": 1, "count": 2}, {"defect_type": 4, "count": 1}]}
```
- The work order must be in production; `line` defaults to its line.
- `defective_pieces` ≤ pieces checked and ≤ total defects; if there are defects, it can't be 0.
- Returns `total_defects`, `dhu`, `result` (`green`, `amber`, `red`) and `capa_id` (red checks open a corrective action).
- Filters: `production_order`, `line`, `result`, `date` (`gte`/`lte`).

## Final inspection — `/api/final-inspections/`

`GET /final-inspections/plan/?lot_size=600&aql_major=2.5&aql_minor=4.0` → `{code_letter, sample_size, accept_major, accept_minor}`.

AQL plans: single sampling, normal, General Level II (ANSI/ASQ Z1.4 / ISO 2859-1) in the simplified garment-chart form — where the standard table has an arrow, the row's own sample size is kept with accept 0. AQL choices `1.5`, `2.5`, `4.0`, `6.5`; critical defects always accept 0. Examples: lot 600 → 80 pcs, accept 5 major (2.5) / 7 minor (4.0); lot 6,000 → 200 pcs, 10 / 14.

```json
POST /api/final-inspections/
{"production_order": 3, "inspection_date": "2026-11-27", "inspected_by_party": "Own QA", "lot_size": 600,
 "aql_major": "2.5", "aql_minor": "4.0", "cartons_checked": 6, "remarks": "",
 "checklist": {"quantity": true, "measurements": true, "shade": true, "labels": true, "packing": true, "cartons": true},
 "defects": [{"defect_type": 1, "severity": "major", "count": 6}]}
```
- Work order in production or completed; `lot_size` ≤ its finished pieces.
- Editable while `draft`; `defects` replaces the findings; the plan is recalculated from lot size and AQLs.
- Checklist keys: `quantity`, `measurements`, `shade`, `labels`, `packing`, `cartons` (`checklist_items` gives the labels).

| Action (POST) | Rules |
|---|---|
| `/final-inspections/{id}/submit/` | Every checklist item answered. Sets `status` to `passed` or `failed` with `fail_reasons`; a failure opens a corrective action (`capa_id`). |
| `/final-inspections/{id}/reinspect/` | Failed only; creates the next round as a draft with the same lot and AQLs. Idempotent. |

Completed inspections can't be edited or deleted.

## Corrective actions — `/api/corrective-actions/`
Created automatically from red inline checks and failed final inspections, or by hand (`source: other`). Fields: `problem, root_cause, action, owner, due_date, status, is_overdue`. Editable while open.
`POST /corrective-actions/{id}/close/` `{"root_cause": "…", "action": "…"}` — managers/admins; both required.

## Defect control — `/api/quality-summary/?from=2026-11-01&to=2026-11-30` (default: last 30 days)
```json
{"inline": {"checks": 9, "pieces": 350, "defects": 20, "defective": 13, "dhu": 5.71, "red": 4},
 "by_line": [{"id": 3, "name": "Line 3", "checks": 1, "pieces": 30, "defects": 3, "dhu": 10.0}],
 "by_style": [...],
 "pareto": [{"name": "Broken stitch", "category": "sewing", "inline": 6, "final": 13, "total": 19, "percent": 40.4, "cumulative_percent": 40.4}],
 "final": {"inspections": 4, "passed": 2, "failed": 2, "pass_rate": 50.0},
 "capa": {"open": 5, "overdue": 2}}
```
