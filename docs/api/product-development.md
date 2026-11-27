# Product Development API — Tech Pack → Sampling → Approval

Third module of the textile flow. Backend: `backend/apps/development/` · Frontend: `frontend/src/pages/{TechPacks,TechPackDetail,Samples,SampleDetail}.jsx`, `frontend/src/components/dev/`.
Auth, pagination and errors are the same as the [buyer onboarding API](buyer-onboarding.md) (400 field errors / `missing`, 403 role, 409 wrong status).

```
Tech pack: draft ──release (manager)──▶ released ──revise──▶ superseded   (+ new draft revision)
Sample (from a released tech pack):
  requested → in_progress → ready → sent → approved | approved_with_comments | rejected
                                                      └── resubmit → next round (requested)
Approved PP sample ⇒ tech pack.production_approved = true
```

## Tech packs — `/api/tech-packs/`

CRUD while `draft`. Filters: `company`, `buyer`, `status`, `category`, `season`, `production_approved`.

```json
POST /api/tech-packs/
{
  "buyer": 1, "style_no": "NT-101", "style_name": "Kids tee", "season": "SS27", "category": "kidswear",
  "fabric_composition": "100% organic cotton", "gsm": 180, "colourways": ["Navy", "Off white"],
  "sizes": ["4Y", "6Y", "8Y"], "base_size": "6Y", "cost_sheet": 3,
  "description": "", "construction": "Twin-needle hems", "wash_care": "40°C", "packing": "1 pc / polybag",
  "measurements": [{"code": "A", "point": "Chest width", "tolerance": "1", "values": {"4Y": 32, "6Y": 34, "8Y": 36}}],
  "bom": [{"category": "fabric", "description": "180 GSM jersey", "supplier": "…", "colour": "Navy",
           "placement": "Body", "consumption": "0.18", "unit": "kg"}]
}
```

- The buyer can be any buyer that isn't rejected (development often starts before approval). A linked cost sheet must be for the same buyer.
- `measurements` and `bom` replace all rows when sent. Measurement values are cm per size; sizes must be in `sizes`; `base_size` must be one of `sizes`.
- Response adds `tp_no` (`TP-2026-000001`, kept across revisions), `revision`, `previous`, `next_revision_id`, `status`, `production_approved`, `sample_count`, `missing_for_release`, `allowed_actions`, `history`.
- BOM `category`: `fabric`, `trim`, `label`, `thread`, `print`, `packaging`, `other`.

| Action (POST) | Who | Rules |
|---|---|---|
| `/tech-packs/{id}/release/` | manager/admin | Needs sizes, every point of measure filled for every size, and a fabric line. Else 400 with `missing`. |
| `/tech-packs/{id}/revise/` | anyone | Released only. Copies everything into a new draft (revision + 1); the old one becomes `superseded`. Idempotent. |

Delete: only a first-revision draft.

## Samples — `/api/samples/`

Create, list, retrieve; edit (`colourway`, `size`, `quantity`, `due_date`, `instructions`) until sent; delete only while `requested`.
Filters: `company`, `buyer`, `tech_pack`, `status` (also `status__in`), `sample_type`, `due_date__lte/gte`.

```json
POST /api/samples/
{"tech_pack": 1, "sample_type": "fit", "colourway": "Navy", "size": "6Y", "quantity": 2,
 "requested_on": "2026-11-27", "due_date": "2026-12-10", "instructions": "Check neck opening"}
```

- The tech pack must be `released`. Size defaults to the tech pack's base size; size and colourway must be on the tech pack.
- `round` = 1 + samples of that type for any revision of the style.
- `sample_type`: `proto`, `fit`, `size_set`, `salesman`, `photo`, `pp`, `top`.
- Response adds `sample_no` (`SMP-2026-000001`), `status`, `is_late`, `courier`, `tracking_no`, `sent_on`, `buyer_comments`, `decided_on`, `previous`, `resubmission_id`, `measurements`, `measurement_summary`, `allowed_actions`, `history`.

| Action | Body | Rules |
|---|---|---|
| `POST /samples/{id}/start/` | — | requested → in_progress |
| `POST /samples/{id}/mark-ready/` | — | in_progress → ready |
| `POST /samples/{id}/send/` | `{"courier": "DHL", "tracking_no": "…", "sent_on": "2026-12-01"}` | ready → sent. Courier required. |
| `POST /samples/{id}/decide/` | `{"decision": "approved" \| "approved_with_comments" \| "rejected", "comments": "…"}` | sent only. Comments required unless approved. Approving a `pp` sample approves the tech pack for production. |
| `POST /samples/{id}/resubmit/` | `{"instructions": "…"}` | After rejected / approved with comments. New sample, next round, from the latest released revision. Idempotent. |
| `PUT /samples/{id}/measurements/` | `{"readings": [{"measurement": 5, "actual": "34.5"}]}` | Before the decision. Replaces readings. Each is checked: `|actual − spec| ≤ tolerance`. |
| `GET /samples/board/` | — | Count per status. |

Measurement rows return `spec`, `tolerance`, `actual`, `deviation`, `within_tolerance`; `measurement_summary` = `{measured, out_of_tolerance, passed}`.

## Not yet included

Sketch / image uploads on tech packs: the project has no file storage yet (it needs a media volume, web-server route and backups in production).
