import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import useOptions from '../components/useOptions'
import History from '../components/merch/History'
import StoresBadge from '../components/stores/StoresBadge'
import { qty } from '../components/proc/constants'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { fmtDateTime, labelOf } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)

export default function GoodsReceiptDetail() {
  const { id } = useParams()
  const isNew = id === undefined
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [grn, setGrn] = useState(null)
  const [form, setForm] = useState(() => (isNew ? { purchase_order: query.get('po') || '', warehouse: '', received_on: todayStr(), challan_no: '', invoice_no: '', vehicle_no: '', notes: '', lines: [] } : null))
  const [receivable, setReceivable] = useState(null)
  const [results, setResults] = useState({})
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const apply = (data) => {
    setGrn(data)
    setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) })
    setResults(Object.fromEntries(data.lines.map((l) => [l.id, { accepted_qty: l.result === 'pending' ? l.received_qty : l.accepted_qty, rejected_qty: l.rejected_qty && Number(l.rejected_qty) ? l.rejected_qty : '0', remarks: l.remarks || '' }])))
  }
  const load = useCallback(() => {
    if (!isNew) api.get(`/goods-receipts/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e)))
  }, [id, isNew])
  useEffect(() => { load() }, [load])

  const poId = form?.purchase_order
  useEffect(() => {
    if (!poId) return
    api.get('/goods-receipts/receivable/', { params: { purchase_order: poId } }).then((r) => {
      setReceivable(r.data)
      if (isNew) setForm((f) => ({ ...f, lines: r.data.lines.filter((l) => Number(l.open_qty) > 0).map((l) => ({ po_line: l.po_line, received_qty: l.open_qty, lot_no: '', rolls: '' })) }))
    }).catch((e) => setError(errorMessage(e)))
  }, [poId, isNew])

  const pos = useOptions(isNew ? '/purchase-orders/' : null, isNew ? { status: 'sent' } : null)
  const warehouses = useOptions('/warehouses/', receivable ? { company: receivable.company, is_active: true } : null)

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => (isNew ? a === 'edit' : grn.allowed_actions.includes(a))
  const editable = can('edit')
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const info = (poLine) => receivable?.lines.find((l) => l.po_line === poLine)
  const setLine = (i, patch) => set('lines', form.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const setResult = (lid, patch) => setResults((r) => {
    const next = { ...r[lid], ...patch }
    const line = grn.lines.find((l) => l.id === lid)
    if ('rejected_qty' in patch) next.accepted_qty = String(Math.max(0, Number(line.received_qty) - (Number(patch.rejected_qty) || 0)))
    return { ...r, [lid]: next }
  })

  const save = async ({ submit = false } = {}) => {
    setBusy(true); setError('')
    const body = {
      purchase_order: form.purchase_order, warehouse: form.warehouse, received_on: form.received_on, challan_no: form.challan_no,
      invoice_no: form.invoice_no, vehicle_no: form.vehicle_no, notes: form.notes,
      lines: form.lines.filter((l) => Number(l.received_qty) > 0).map((l) => ({ po_line: l.po_line, received_qty: l.received_qty, lot_no: l.lot_no, rolls: l.rolls === '' ? null : l.rolls })),
    }
    try {
      let { data } = isNew ? await api.post('/goods-receipts/', body) : await api.put(`/goods-receipts/${id}/`, body)
      if (submit) data = (await api.post(`/goods-receipts/${data.id}/submit/`)).data
      if (isNew) navigate(`/receipts/${data.id}`, { replace: true })
      else apply(data)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const inspect = async () => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/goods-receipts/${id}/inspect/`, {
        notes, results: grn.lines.map((l) => ({ line: l.id, ...results[l.id] })),
      })
      apply(data)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const rejectedTotal = grn ? grn.lines.reduce((a, l) => a + (Number(results[l.id]?.rejected_qty) || 0), 0) : 0

  return (
    <>
      <div className="crumbs small"><Link to="/receipts">Goods receipts</Link> / {isNew ? 'New' : grn.grn_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{isNew ? 'Receive goods' : grn.grn_no} {!isNew && <StoresBadge kind="grn" status={grn.status} />}</h1>
          {!isNew && <p className="muted">{grn.supplier_name} · <Link to={`/purchase-orders/${grn.purchase_order}`}>{grn.po_no}</Link> · into {grn.warehouse_name}{grn.challan_no && <> · challan {grn.challan_no}</>}</p>}
        </div>
        <div className="actions">
          {editable && <button className="secondary" onClick={() => save()} disabled={busy}>{isNew ? 'Save draft' : 'Save'}</button>}
          {editable && <button onClick={() => save({ submit: true })} disabled={busy || !form.lines.length}>Save & send to inspection</button>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {grn?.status === 'received' && <div className="notice">Goods are in the store, waiting for quality inspection. Nothing is in stock until inspection is complete.</div>}
      {grn?.status === 'inspected' && (
        <div className={`notice block ${Number(grn.totals.rejected) > 0 ? 'warn' : 'ok'}`}>
          Inspected by {grn.inspected_by_name} on {fmtDateTime(grn.inspected_at)}. Accepted material is now in stock in {grn.warehouse_name}.
          {Number(grn.totals.rejected) > 0 && <ul>{grn.lines.filter((l) => Number(l.rejected_qty) > 0).map((l) => <li key={l.id}><b>Return to supplier:</b> {qty(l.rejected_qty, l.unit)} of {l.description} — {l.remarks}</li>)}</ul>}
          {grn.inspection_notes && <div className="small">Notes: {grn.inspection_notes}</div>}
        </div>
      )}

      {editable && (
        <div className="card">
          <div className="form-grid">
            {isNew
              ? <FormField field={{ name: 'purchase_order', label: 'Supplier PO (sent)', type: 'select', required: true, options: pos.map((p) => ({ value: p.id, label: `${p.po_no} · ${p.supplier_name}` })) }} value={form.purchase_order} onChange={(n, v) => { set(n, v); setReceivable(null) }} />
              : <label className="field"><span>Supplier PO</span><input value={`${grn.po_no} · ${grn.supplier_name}`} disabled /></label>}
            <FormField field={{ name: 'warehouse', label: 'Received into', type: 'select', required: true, options: warehouses.map((w) => ({ value: w.id, label: w.name })) }} value={form.warehouse} onChange={set} />
            <FormField field={{ name: 'received_on', label: 'Received on', type: 'date', required: true }} value={form.received_on} onChange={set} />
            <FormField field={{ name: 'challan_no', label: 'Delivery challan no.' }} value={form.challan_no} onChange={set} />
            <FormField field={{ name: 'invoice_no', label: 'Supplier invoice no.' }} value={form.invoice_no} onChange={set} />
            <FormField field={{ name: 'vehicle_no', label: 'Vehicle no.' }} value={form.vehicle_no} onChange={set} />
            <FormField field={{ name: 'notes', label: 'Notes', type: 'textarea', full: true }} value={form.notes} onChange={set} />
          </div>
        </div>
      )}

      {editable && (
        <div className="card">
          <h2>What arrived</h2>
          {!receivable ? <p className="muted small">Choose a sent PO.</p> : (
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Material</th><th className="num">Ordered</th><th className="num">Already received</th><th className="num">Open</th><th className="num">Received now</th><th>Lot / dye lot</th><th className="num">Rolls</th><th /></tr></thead>
                <tbody>
                  {form.lines.length === 0 && <tr><td colSpan={8} className="muted center">Everything on this PO has been received.</td></tr>}
                  {form.lines.map((l, i) => {
                    const r = info(l.po_line) || {}
                    return (
                      <tr key={l.po_line}>
                        <td><b>{r.description}</b><div className="muted small">{labelOf(BOM_CATEGORIES, r.category)}{r.colour && ` · ${r.colour}`}</div></td>
                        <td className="num">{qty(r.ordered_qty, r.unit)}</td>
                        <td className="num muted">{qty(r.received_qty)}</td>
                        <td className="num">{qty(r.open_qty)}</td>
                        <td><input className="num w-md" type="number" min="0" step="0.01" value={l.received_qty} onChange={(e) => setLine(i, { received_qty: e.target.value })} aria-label={`Received ${r.description}`} /></td>
                        <td><input className="w-md" value={l.lot_no} onChange={(e) => setLine(i, { lot_no: e.target.value })} aria-label="Lot" /></td>
                        <td><input className="num w-sm" type="number" min="0" step="1" value={l.rolls ?? ''} onChange={(e) => setLine(i, { rolls: e.target.value })} aria-label="Rolls" /></td>
                        <td><button type="button" className="link" onClick={() => set('lines', form.lines.filter((_, j) => j !== i))} aria-label="Remove">✕</button></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted small">Up to 10% more than ordered can be received. Remove lines that didn’t arrive.</p>
        </div>
      )}

      {grn && grn.status !== 'draft' && (
        <div className="card">
          <div className="card-head">
            <div><h2>Quality inspection</h2>{grn.status === 'received' && <p className="muted small">Enter the rejected quantity per line (the rest is accepted). Rejections need a reason.</p>}</div>
            {grn.status === 'received' && rejectedTotal > 0 && <span className="badge badge-res-partial">{rejectedTotal.toLocaleString('en-IN')} to reject</span>}
          </div>
          <div className="table-wrap">
            <table className="cost-lines">
              <thead><tr><th>Material</th><th>Lot</th><th className="num">Received</th><th className="num">Accepted</th><th className="num">Rejected</th><th>Findings</th><th>Result</th></tr></thead>
              <tbody>
                {grn.lines.map((l) => {
                  const r = results[l.id] || {}
                  const live = grn.status === 'received'
                  return (
                    <tr key={l.id} className={live && Number(r.rejected_qty) > 0 ? 'row-bad' : ''}>
                      <td><b>{l.description}</b><div className="muted small">{l.material_code} · {l.colour || labelOf(BOM_CATEGORIES, l.category)}</div></td>
                      <td>{l.lot_no || '—'}{l.rolls != null && <div className="muted small">{l.rolls} rolls</div>}</td>
                      <td className="num">{qty(l.received_qty, l.unit)}</td>
                      <td className="num">{live ? qty(r.accepted_qty) : qty(l.accepted_qty)}</td>
                      <td className="num">{live ? <input className="num w-md" type="number" min="0" max={l.received_qty} step="0.01" value={r.rejected_qty} onChange={(e) => setResult(l.id, { rejected_qty: e.target.value })} aria-label={`Rejected ${l.description}`} /> : qty(l.rejected_qty)}</td>
                      <td>{live ? <input value={r.remarks} placeholder={Number(r.rejected_qty) > 0 ? 'Why rejected? *' : 'Optional'} onChange={(e) => setResult(l.id, { remarks: e.target.value })} aria-label={`Findings ${l.description}`} /> : l.remarks || '—'}</td>
                      <td>{live ? <span className="muted small">—</span> : <StoresBadge kind="res" status={l.result} />}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {grn.status === 'received' && (
            <>
              <label className="field" style={{ marginTop: 12 }}><span>Inspection notes (method, sample size)</span>
                <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. 4-point inspection on 10% of rolls, GSM and shade checked" /></label>
              <div className="form-actions"><button className="approve" onClick={inspect} disabled={busy}>Complete inspection & put into stock</button></div>
            </>
          )}
        </div>
      )}
      {!isNew && <History items={grn.history} />}
    </>
  )
}
