import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import History from '../components/merch/History'
import ProcBadge from '../components/proc/ProcBadge'
import { qty } from '../components/proc/constants'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { fmtDate, fmtDateTime, labelOf } from '../components/buyers/constants'
import { Progress } from './MaterialRequirements'

export default function MaterialRequirementDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [mr, setMr] = useState(null)
  const [form, setForm] = useState(null)
  const [selected, setSelected] = useState([])
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  const apply = (data) => { setMr(data); setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) }) }
  const load = useCallback(() => api.get(`/material-requirements/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => mr.allowed_actions.includes(a)
  const editable = can('edit')
  const set = (name, v) => { setSaved(false); setForm((f) => ({ ...f, [name]: v })) }
  const setLine = (i, patch) => set('lines', form.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const openLines = mr.lines.filter((l) => Number(l.open_qty) > 0)
  const toggle = (lid) => setSelected((s) => (s.includes(lid) ? s.filter((x) => x !== lid) : [...s, lid]))
  const pick = selected.length ? selected : openLines.map((l) => l.id)

  const save = async (e) => {
    e?.preventDefault(); setBusy(true); setError('')
    try {
      const { data } = await api.patch(`/material-requirements/${id}/`, {
        title: form.title, needed_by: form.needed_by || null, notes: form.notes,
        lines: form.lines.map(({ id: lid, category, description, colour, unit, supplier_hint, required_qty }) => ({ id: lid, category, description, colour, unit, supplier_hint, required_qty })),
      })
      apply(data); setSaved(true)
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }
  const act = async (action) => {
    setBusy(true); setError('')
    try { const { data } = await api.post(`/material-requirements/${id}/${action}/`); apply(data) } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const approve = async () => { if (await save()) act('approve') }

  return (
    <>
      <div className="crumbs small"><Link to="/requirements">Material requirements</Link> / {mr.mr_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{mr.mr_no} <ProcBadge kind="mr" status={mr.status} /></h1>
          <p className="muted">{mr.title}{mr.order && <> · <Link to={`/orders/${mr.order}`}>{mr.oc_no}</Link></>} · wastage {Number(mr.wastage_pct)}%</p>
        </div>
        <div className="actions">
          {can('recalculate') && <button className="secondary" onClick={() => act('recalculate')} disabled={busy} title="Rebuild from the order and current tech packs">Recalculate</button>}
          {can('reopen') && <button className="secondary" onClick={() => act('reopen')} disabled={busy}>Reopen</button>}
          {can('approve') && <button className="approve" onClick={approve} disabled={busy}>Save & approve</button>}
          {can('create_rfq') && <button className="secondary" disabled={!pick.length} onClick={() => navigate(`/rfqs/new?mr=${mr.id}&lines=${pick.join(',')}`)}>Create RFQ{selected.length ? ` (${selected.length})` : ''}</button>}
          {mr.status === 'approved' && mr.order && <Link className="button secondary" to={`/allocation/${mr.id}`}>Stock allocation</Link>}
          {can('create_po') && <button disabled={!pick.length} onClick={() => navigate(`/purchase-orders/new?mr=${mr.id}&lines=${pick.join(',')}`)}>Create PO{selected.length ? ` (${selected.length})` : ''}</button>}
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {mr.warnings.length > 0 && (
        <div className="notice warn block"><b>Check before buying:</b><ul>{mr.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>
      )}
      {mr.status === 'draft' && <div className="notice">Check the quantities, add anything the tech packs don’t cover, then a manager approves. RFQs and POs are made from approved requirements.</div>}
      {mr.status === 'approved' && <div className="notice ok"><span>Approved by {mr.approved_by_name} on {fmtDateTime(mr.approved_at)}. Tick materials (or none for all still open) and create an RFQ or a PO.</span><Progress done={mr.progress.fully_ordered} total={mr.progress.lines} /></div>}

      <form onSubmit={save}>
        <fieldset className="plain" disabled={!editable}>
          <div className="card">
            <div className="form-grid">
              <FormField field={{ name: 'title', label: 'Title', required: true, full: true }} value={form.title} onChange={set} />
              <FormField field={{ name: 'needed_by', label: 'Needed in factory by', type: 'date' }} value={form.needed_by} onChange={set} />
              <FormField field={{ name: 'notes', label: 'Notes', type: 'textarea', full: true }} value={form.notes} onChange={set} />
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h2>Materials</h2>{mr.status === 'approved' && openLines.length === 0 && <span className="badge badge-po-sent">Everything ordered</span>}</div>
            <div className="table-wrap">
              <table className="cost-lines mr-lines">
                <thead>
                  <tr>{!editable && <th />}<th>Type</th><th>Material</th><th>Colour</th><th>Styles</th><th className="num">Net</th><th className="num">Required</th><th>Unit</th>
                    {!editable && <><th className="num">Ordered</th><th className="num">Open</th><th>On</th></>}{editable && <th />}</tr>
                </thead>
                <tbody>
                  {form.lines.map((l, i) => {
                    const done = Number(l.open_qty) <= 0 && l.id
                    return (
                      <tr key={l.id ?? `n${i}`} className={done ? 'row-done' : ''}>
                        {!editable && <td><input type="checkbox" checked={selected.includes(l.id)} onChange={() => toggle(l.id)} disabled={done} aria-label={`Select ${l.description}`} /></td>}
                        <td>{editable ? <select value={l.category} onChange={(e) => setLine(i, { category: e.target.value })} aria-label="Type">{BOM_CATEGORIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select> : labelOf(BOM_CATEGORIES, l.category)}</td>
                        <td>{editable ? <input className="pom" value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} required aria-label="Material" /> : <><b>{l.description}</b>{l.supplier_hint && <div className="muted small">{l.supplier_hint}</div>}</>}</td>
                        <td>{editable ? <input className="w-md" value={l.colour} onChange={(e) => setLine(i, { colour: e.target.value })} aria-label="Colour" /> : l.colour}</td>
                        <td className="muted small">{l.styles || 'added by hand'}</td>
                        <td className="num muted">{l.net_qty ? qty(l.net_qty) : '—'}</td>
                        <td className="num">{editable ? <input className="num w-md" type="number" min="0" step="0.01" value={l.required_qty} onChange={(e) => setLine(i, { required_qty: e.target.value })} required aria-label="Required" /> : <b>{qty(l.required_qty)}</b>}</td>
                        <td>{editable ? <input className="w-xs" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} aria-label="Unit" /> : l.unit}</td>
                        {!editable && <>
                          <td className="num">{qty(l.ordered_qty)}</td>
                          <td className={`num ${Number(l.open_qty) > 0 ? 'warn-text' : 'pos'}`}>{Number(l.open_qty) > 0 ? qty(l.open_qty) : '✓'}</td>
                          <td className="small">{[...l.rfq_nos, ...l.po_nos].join(', ') || '—'}</td>
                        </>}
                        {editable && <td><button type="button" className="link" onClick={() => set('lines', form.lines.filter((_, j) => j !== i))} aria-label="Remove">✕</button></td>}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {editable && <button type="button" className="secondary" style={{ marginTop: 10 }}
              onClick={() => set('lines', [...form.lines, { category: 'trim', description: '', colour: '', unit: 'pc', supplier_hint: '', required_qty: '' }])}>+ Add material</button>}
          </div>
        </fieldset>
        {editable && <div className="form-actions">{saved && <span className="pos small">✓ Saved</span>}<button type="submit" className="secondary" disabled={busy}>Save draft</button></div>}
      </form>
      {mr.needed_by && <p className="muted small">Needed by {fmtDate(mr.needed_by)} (45 days before the order’s shipment date by default).</p>}
      <History items={mr.history} />
    </>
  )
}
