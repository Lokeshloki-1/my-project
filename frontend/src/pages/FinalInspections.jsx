import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import ResourcePage from '../components/ResourcePage'
import useOptions from '../components/useOptions'
import { FI_STATUSES, SEVERITIES } from '../components/qa/constants'
import { pcs } from '../components/prod/constants'
import { fmtDate, fmtDateTime, labelOf } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)

export default function FinalInspections() {
  const { id } = useParams()
  return id ? <FinalInspectionDetail id={id === 'new' ? null : id} /> : <FinalList />
}

function FinalList() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Final Inspections"
      subtitle="AQL inspection of finished lots before shipment (General Level II, normal single sampling)"
      endpoint="/final-inspections/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={<>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All</option>{FI_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <button onClick={() => navigate('/quality/final/new')}>+ New inspection</button>
      </>}
      onRowClick={(r) => navigate(`/quality/final/${r.id}`)}
      columns={[
        { key: 'fi_no', label: 'Inspection', render: (r) => <>{r.fi_no}{r.round > 1 && <div className="muted small">round {r.round}</div>}</> },
        { key: 'style_no', label: 'Style', render: (r) => <><b>{r.style_no}</b><div className="muted small">{r.oc_no} · {r.buyer_name}</div></> },
        { key: 'inspection_date', label: 'Date', render: (r) => fmtDate(r.inspection_date) },
        { key: 'inspected_by_party', label: 'By' },
        { key: 'lot_size', label: 'Lot / sample', num: true, render: (r) => <>{pcs(r.lot_size)}<div className="muted small">{r.sample_size} sampled</div></> },
        { key: 'found', label: 'Crit / major / minor', num: true, render: (r) => <><span className={r.critical_found ? 'neg' : ''}>{r.critical_found}</span> / <span className={r.major_found > r.accept_major ? 'neg' : ''}>{r.major_found}</span> / <span className={r.minor_found > r.accept_minor ? 'neg' : ''}>{r.minor_found}</span></> },
        { key: 'status', label: 'Result', render: (r) => <span className={`badge badge-fi-${r.status}`}>{labelOf(FI_STATUSES, r.status)}</span> },
      ]}
      fields={[]}
    />
  )
}

function FinalInspectionDetail({ id }) {
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [fi, setFi] = useState(null)
  const [form, setForm] = useState(() => (id ? null : { production_order: query.get('wo') || '', inspection_date: todayStr(), inspected_by_party: 'Own QA', lot_size: '', aql_major: '2.5', aql_minor: '4.0', checklist: {}, cartons_checked: '', remarks: '', defects: [] }))
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const orders = useOptions(id ? null : '/production-orders/', id ? null : { status__in: 'in_progress,completed' })
  const types = useOptions('/defect-types/', { is_active: true })

  const apply = (data) => { setFi(data); setForm({ ...data, defects: data.defects.map((d) => ({ ...d })) }) }
  const load = useCallback(() => { if (id) api.get(`/final-inspections/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))) }, [id])
  useEffect(() => { load() }, [load])
  const lot = form?.lot_size, am = form?.aql_major, an = form?.aql_minor
  useEffect(() => {
    if (!(Number(lot) >= 2)) return
    api.get('/final-inspections/plan/', { params: { lot_size: lot, aql_major: am, aql_minor: an } }).then((r) => setPlan(r.data)).catch(() => setPlan(null))
  }, [lot, am, an])

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const editable = !fi || fi.allowed_actions.includes('edit')
  const can = (a) => fi?.allowed_actions.includes(a)
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const wo = orders.find((o) => String(o.id) === String(form.production_order))
  // Coming from a work order: offer all finished pieces as the lot.
  if (!fi && wo && form.lot_size === '' && wo.progress.finished >= 2) setForm((f) => ({ ...f, lot_size: wo.progress.finished }))
  const finished = fi ? fi.finished_pcs : wo?.progress.finished
  const items = fi?.checklist_items || [
    { key: 'quantity', label: 'Quantity and size ratio match the PO' }, { key: 'measurements', label: 'Measurements within tolerance' },
    { key: 'shade', label: 'Shade matches the approved sample' }, { key: 'labels', label: 'Labels, care labels and hang tags correct' },
    { key: 'packing', label: 'Folding and packing as instructed' }, { key: 'cartons', label: 'Carton marks and dimensions correct' },
  ]
  const count = (sev) => form.defects.filter((d) => d.severity === sev).reduce((a, d) => a + (Number(d.count) || 0), 0)
  const p = plan || (fi && { sample_size: fi.sample_size, accept_major: fi.accept_major, accept_minor: fi.accept_minor, code_letter: fi.code_letter })
  const setDefect = (i, patch) => set('defects', form.defects.map((d, j) => (j === i ? { ...d, ...patch } : d)))
  const addDefect = () => set('defects', [...form.defects, { defect_type: '', severity: 'major', count: 1 }])

  const save = async (submit = false) => {
    setBusy(true); setError('')
    const body = {
      production_order: form.production_order, inspection_date: form.inspection_date, inspected_by_party: form.inspected_by_party,
      lot_size: form.lot_size, aql_major: form.aql_major, aql_minor: form.aql_minor, checklist: form.checklist,
      cartons_checked: form.cartons_checked || null, remarks: form.remarks,
      defects: form.defects.filter((d) => d.defect_type && Number(d.count) > 0).map((d) => ({ defect_type: Number(d.defect_type), severity: d.severity, count: Number(d.count) })),
    }
    try {
      let { data } = fi ? await api.put(`/final-inspections/${fi.id}/`, body) : await api.post('/final-inspections/', body)
      if (submit) data = (await api.post(`/final-inspections/${data.id}/submit/`)).data
      if (!fi) navigate(`/quality/final/${data.id}`, { replace: true })
      else apply(data)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const reinspect = async () => {
    try { const { data } = await api.post(`/final-inspections/${fi.id}/reinspect/`); navigate(`/quality/final/${data.id}`) } catch (err) { setError(errorMessage(err)) }
  }
  const verdict = (found, accept) => (found > accept ? 'neg' : 'pos')

  return (
    <>
      <div className="crumbs small"><Link to="/quality/final">Final inspections</Link> / {fi ? fi.fi_no : 'New'}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{fi ? `${fi.fi_no}` : 'Final inspection'} {fi && <span className={`badge badge-fi-${fi.status}`}>{fi.status_label}</span>}{fi?.round > 1 && <span className="badge">round {fi.round}</span>}</h1>
          {fi && <p className="muted"><Link to={`/production/${fi.production_order}`}>{fi.style_no} · {fi.wo_no}</Link> · {fi.oc_no} · {fi.buyer_name}{fi.previous && <> · after <Link to={`/quality/final/${fi.previous}`}>round {fi.round - 1}</Link></>}</p>}
        </div>
        <div className="actions">
          {editable && <button className="secondary" onClick={() => save(false)} disabled={busy}>Save draft</button>}
          {editable && <button className="approve" onClick={() => save(true)} disabled={busy}>Complete inspection</button>}
          {can('reinspect') && <button onClick={reinspect}>Re-inspect →</button>}
          {fi?.reinspection_id && <Link className="button secondary" to={`/quality/final/${fi.reinspection_id}`}>Round {fi.round + 1} →</Link>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {fi?.status === 'passed' && <div className="result-banner pass"><b>PASSED</b><span>Lot of {pcs(fi.lot_size)} pcs accepted on {fmtDateTime(fi.completed_at)} by {fi.inspector_name}. Ready for packing and shipment.</span></div>}
      {fi?.status === 'failed' && (
        <div className="result-banner fail"><b>FAILED</b>
          <div><ul>{fi.fail_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            <span className="small">Sort and rework the lot, then re-inspect. {fi.capa_id && <Link to="/quality">Corrective action #{fi.capa_id}</Link>}</span></div>
        </div>
      )}

      <div className="order-layout">
        <div>
          <fieldset className="plain" disabled={!editable}>
            <div className="card">
              <h2>Lot</h2>
              <div className="form-grid">
                {!fi ? <label className="field"><span>Work order *</span>
                  <select value={form.production_order} onChange={(e) => { const o = orders.find((x) => String(x.id) === e.target.value); setForm((f) => ({ ...f, production_order: e.target.value, lot_size: o ? o.progress.finished : '' })) }} required>
                    <option value="">— choose —</option>
                    {orders.map((o) => <option key={o.id} value={o.id}>{o.style_no} · {o.wo_no} · {pcs(o.progress.finished)} finished</option>)}
                  </select></label> : <label className="field"><span>Work order</span><input value={`${fi.style_no} · ${fi.wo_no}`} disabled /></label>}
                <label className="field"><span>Lot size (pcs offered){finished != null && ` · ${pcs(finished)} finished`}</span><input type="number" min="2" max={finished || undefined} value={form.lot_size} onChange={(e) => set('lot_size', e.target.value)} /></label>
                <label className="field"><span>Date</span><input type="date" value={form.inspection_date} onChange={(e) => set('inspection_date', e.target.value)} /></label>
                <label className="field"><span>Inspected by</span><input value={form.inspected_by_party} onChange={(e) => set('inspected_by_party', e.target.value)} placeholder="Own QA, buyer QA, SGS…" /></label>
                <label className="field"><span>AQL major</span><select value={form.aql_major} onChange={(e) => set('aql_major', e.target.value)}>{['1.5', '2.5', '4.0', '6.5'].map((a) => <option key={a}>{a}</option>)}</select></label>
                <label className="field"><span>AQL minor</span><select value={form.aql_minor} onChange={(e) => set('aql_minor', e.target.value)}>{['1.5', '2.5', '4.0', '6.5'].map((a) => <option key={a}>{a}</option>)}</select></label>
              </div>
            </div>
            <div className="card">
              <div className="card-head"><h2>Defects in the sample</h2>{editable && <button type="button" className="secondary small-btn" onClick={addDefect}>+ Add defect</button>}</div>
              <div className="table-wrap">
                <table className="cost-lines">
                  <thead><tr><th>Defect</th><th>Severity</th><th className="num">Count</th><th /></tr></thead>
                  <tbody>
                    {form.defects.length === 0 && <tr><td colSpan={4} className="muted center">No defects recorded{editable && ' — add each defect found in the sample'}.</td></tr>}
                    {form.defects.map((d, i) => (
                      <tr key={i}>
                        <td><select value={d.defect_type} onChange={(e) => { const t = types.find((x) => String(x.id) === e.target.value); setDefect(i, { defect_type: e.target.value, severity: t?.severity || d.severity }) }} aria-label="Defect">
                          <option value="">— choose —</option>{types.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}</select></td>
                        <td><select value={d.severity} onChange={(e) => setDefect(i, { severity: e.target.value })} aria-label="Severity">{SEVERITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
                        <td><input className="num w-sm" type="number" min="1" value={d.count} onChange={(e) => setDefect(i, { count: e.target.value })} aria-label="Count" /></td>
                        <td>{editable && <button type="button" className="link" onClick={() => set('defects', form.defects.filter((_, j) => j !== i))} aria-label="Remove">✕</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card">
              <h2>Checklist</h2>
              <div className="checklist">
                {items.map((it) => {
                  const v = form.checklist[it.key]
                  return (
                    <div key={it.key} className={`check-row ${v === false ? 'bad' : v === true ? 'good' : ''}`}>
                      <span>{it.label}</span>
                      <span className="seg">
                        <button type="button" className={v === true ? 'on ok' : ''} onClick={() => set('checklist', { ...form.checklist, [it.key]: true })}>OK</button>
                        <button type="button" className={v === false ? 'on nok' : ''} onClick={() => set('checklist', { ...form.checklist, [it.key]: false })}>Not OK</button>
                      </span>
                    </div>
                  )
                })}
              </div>
              <div className="form-grid" style={{ marginTop: 12 }}>
                <label className="field"><span>Cartons opened</span><input type="number" min="0" value={form.cartons_checked ?? ''} onChange={(e) => set('cartons_checked', e.target.value)} /></label>
                <label className="field full"><span>Remarks</span><textarea rows={2} value={form.remarks} onChange={(e) => set('remarks', e.target.value)} /></label>
              </div>
            </div>
          </fieldset>
        </div>
        <aside>
          <div className="card aql-card">
            <h2>AQL plan</h2>
            {!p ? <p className="muted small">Enter the lot size.</p> : (
              <>
                <div className="aql-sample"><span>Inspect</span><strong>{p.sample_size}</strong><span>pcs (code {p.code_letter})</span></div>
                <dl className="summary">
                  <div><dt>Critical (accept 0)</dt><dd className={verdict(count('critical'), 0)}>{count('critical')} found</dd></div>
                  <div><dt>Major (AQL {form.aql_major}, accept ≤ {p.accept_major})</dt><dd className={verdict(count('major'), p.accept_major)}>{count('major')} found</dd></div>
                  <div><dt>Minor (AQL {form.aql_minor}, accept ≤ {p.accept_minor})</dt><dd className={verdict(count('minor'), p.accept_minor)}>{count('minor')} found</dd></div>
                </dl>
                {editable && <p className={`small ${count('critical') || count('major') > p.accept_major || count('minor') > p.accept_minor || Object.values(form.checklist).includes(false) ? 'neg' : 'pos'}`}>
                  {count('critical') || count('major') > p.accept_major || count('minor') > p.accept_minor || Object.values(form.checklist).includes(false) ? 'As entered, this lot will fail.' : 'As entered, this lot will pass (once the checklist is complete).'}</p>}
              </>
            )}
          </div>
        </aside>
      </div>
    </>
  )
}
