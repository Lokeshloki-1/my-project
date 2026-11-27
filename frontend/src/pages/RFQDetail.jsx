import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import Modal from '../components/Modal'
import useOptions from '../components/useOptions'
import History from '../components/merch/History'
import ReasonDialog from '../components/merch/ReasonDialog'
import { num } from '../components/merch/constants'
import ProcBadge from '../components/proc/ProcBadge'
import { qty } from '../components/proc/constants'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { fmtDate, labelOf } from '../components/buyers/constants'

const plusDays = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10)
const blankRFQ = (mrId) => ({ company: '', requirement: mrId ? Number(mrId) : null, title: '', reply_by: plusDays(5), required_by: '', currency: 'INR', notes: '', suppliers: [], lines: [] })

export default function RFQDetail() {
  const { id } = useParams()
  const isNew = id === undefined
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [rfq, setRfq] = useState(null)
  const [form, setForm] = useState(() => (isNew && !query.get('mr') ? blankRFQ(null) : null))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [quoteFor, setQuoteFor] = useState(null)
  const [dialog, setDialog] = useState(null)

  const apply = (data) => { setRfq(data); setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) }) }
  const load = useCallback(() => {
    if (isNew) {
      const mrId = query.get('mr')
      if (!mrId) return
      const base = blankRFQ(mrId)
      const ids = (query.get('lines') || '').split(',').map(Number)
      api.get(`/material-requirements/${mrId}/`).then(({ data }) => setForm({
        ...base, company: data.company, title: `Materials for ${data.oc_no || data.mr_no}`, required_by: data.needed_by || '',
        lines: data.lines.filter((l) => ids.includes(l.id)).map((l) => ({
          requirement_line: l.id, mr_no: data.mr_no, category: l.category, description: l.description, colour: l.colour, unit: l.unit, quantity: l.open_qty,
        })),
      })).catch((e) => setError(errorMessage(e)))
      return
    }
    api.get(`/rfqs/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e)))
  }, [id, isNew, query])
  useEffect(() => { load() }, [load])

  const suppliers = useOptions(form?.company ? '/suppliers/' : null, form?.company ? { company: form.company, is_active: true } : null)
  const companies = useOptions('/companies/')

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => (isNew ? a === 'edit' : rfq.allowed_actions.includes(a))
  const editable = can('edit')
  const set = (name, v) => setForm((f) => ({ ...f, [name]: v }))
  const setLine = (i, patch) => set('lines', form.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const lineCats = new Set(form.lines.map((l) => l.category))
  const toggleSupplier = (sid) => set('suppliers', form.suppliers.includes(sid) ? form.suppliers.filter((x) => x !== sid) : [...form.suppliers, sid])

  const save = async (e, { stay = false } = {}) => {
    e?.preventDefault(); setBusy(true); setError('')
    const body = {
      company: form.company, requirement: form.requirement, title: form.title, reply_by: form.reply_by,
      required_by: form.required_by || null, currency: form.currency, notes: form.notes, suppliers: form.suppliers,
      lines: form.lines.map(({ requirement_line, category, description, colour, unit, quantity }) => ({ requirement_line: requirement_line || null, category, description, colour, unit, quantity })),
    }
    try {
      const { data } = isNew ? await api.post('/rfqs/', body) : await api.put(`/rfqs/${id}/`, body)
      if (isNew && !stay) navigate(`/rfqs/${data.id}`, { replace: true })
      else if (!isNew) apply(data)
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }
  const act = async (action, body = {}) => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/rfqs/${id}/${action}/`, body)
      setDialog(null)
      if (action === 'award') navigate(`/purchase-orders/${data.id}`)
      else apply(data)
    } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const saveAndSend = async () => {
    const data = await save(null, { stay: true })
    if (!data) return
    if (!isNew) { act('send'); return }
    try { await api.post(`/rfqs/${data.id}/send/`) } catch (err) { setError(errorMessage(err)) }
    navigate(`/rfqs/${data.id}`, { replace: true })
  }

  const cmp = rfq?.comparison
  const supplierName = (sid) => cmp?.suppliers.find((s) => s.supplier === sid)?.supplier_name || suppliers.find((s) => s.id === sid)?.name || rfq?.supplier_names[rfq.suppliers.indexOf(sid)]

  return (
    <>
      <div className="crumbs small"><Link to="/rfqs">RFQs</Link> / {isNew ? 'New' : rfq.rfq_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{isNew ? 'New RFQ' : rfq.rfq_no} {!isNew && <ProcBadge kind="rfq" status={rfq.status} />}</h1>
          {!isNew && <p className="muted">{rfq.title}{rfq.requirement && <> · <Link to={`/requirements/${rfq.requirement}`}>{rfq.mr_no}</Link></>} · reply by {fmtDate(rfq.reply_by)}</p>}
        </div>
        <div className="actions">
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')} disabled={busy}>Cancel RFQ</button>}
          {(can('send') || isNew) && <button onClick={saveAndSend} disabled={busy}>{isNew ? 'Create & send to suppliers' : 'Save & send to suppliers'}</button>}
          {can('view_po') && rfq.po_id && <Link className="button" to={`/purchase-orders/${rfq.po_id}`}>Open PO →</Link>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {rfq?.status === 'sent' && <div className="notice">Sent to {rfq.supplier_names.join(', ')}. Enter each supplier’s prices as they reply, then award the best offer — a draft PO is created.</div>}
      {rfq?.status === 'awarded' && <div className="notice ok">Awarded to {rfq.awarded_supplier_name}.</div>}

      {(editable || isNew) && (
        <form onSubmit={save}>
          <div className="card">
            <div className="form-grid">
              {!form.requirement && <FormField field={{ name: 'company', label: 'Our company', type: 'select', required: true, options: companies.map((c) => ({ value: c.id, label: c.name })) }} value={form.company} onChange={(n, v) => setForm((f) => ({ ...f, company: Number(v), suppliers: [] }))} />}
              <FormField field={{ name: 'title', label: 'Title', required: true }} value={form.title} onChange={set} />
              <FormField field={{ name: 'reply_by', label: 'Suppliers reply by', type: 'date', required: true }} value={form.reply_by} onChange={set} />
              <FormField field={{ name: 'required_by', label: 'Material needed by', type: 'date' }} value={form.required_by} onChange={set} />
              <FormField field={{ name: 'currency', label: 'Currency' }} value={form.currency} onChange={set} />
              <FormField field={{ name: 'notes', label: 'Terms for suppliers (quality, certification, delivery)', type: 'textarea', full: true }} value={form.notes} onChange={set} />
            </div>
          </div>
          <div className="card">
            <h2>Suppliers to ask</h2>
            {!form.company ? <p className="muted small">Choose the company first.</p> : (
              <div className="supplier-pick">
                {suppliers.map((s) => {
                  const match = s.categories.some((c) => lineCats.has(c))
                  return (
                    <button key={s.id} type="button" className={`supplier-chip ${form.suppliers.includes(s.id) ? 'on' : ''}`} onClick={() => toggleSupplier(s.id)} aria-pressed={form.suppliers.includes(s.id)}>
                      <b>{form.suppliers.includes(s.id) ? '✓ ' : ''}{s.name}</b>
                      <small>{s.categories.map((c) => labelOf(BOM_CATEGORIES, c)).join(', ') || 'No categories'} · {s.lead_time_days} days</small>
                      {match && <span className="badge badge-po-sent">supplies this</span>}
                    </button>
                  )
                })}
                {suppliers.length === 0 && <p className="muted small">No active suppliers. <Link to="/suppliers">Add suppliers</Link> first.</p>}
              </div>
            )}
          </div>
          <div className="card">
            <h2>Materials</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Type</th><th>Material</th><th>Colour</th><th className="num">Quantity</th><th>Unit</th><th /></tr></thead>
                <tbody>
                  {form.lines.length === 0 && <tr><td colSpan={6} className="muted center">No materials. Start from an approved material requirement, or add lines.</td></tr>}
                  {form.lines.map((l, i) => (
                    <tr key={i}>
                      <td><select value={l.category} onChange={(e) => setLine(i, { category: e.target.value })} aria-label="Type">{BOM_CATEGORIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></td>
                      <td><input className="pom" value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} required aria-label="Material" />{l.mr_no && <small className="muted">from {l.mr_no}</small>}</td>
                      <td><input className="w-md" value={l.colour} onChange={(e) => setLine(i, { colour: e.target.value })} aria-label="Colour" /></td>
                      <td><input className="num w-md" type="number" min="0.01" step="0.01" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} required aria-label="Quantity" /></td>
                      <td><input className="w-xs" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} aria-label="Unit" /></td>
                      <td><button type="button" className="link" onClick={() => set('lines', form.lines.filter((_, j) => j !== i))} aria-label="Remove">✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button type="button" className="secondary" style={{ marginTop: 10 }} onClick={() => set('lines', [...form.lines, { category: 'fabric', description: '', colour: '', unit: 'kg', quantity: '' }])}>+ Add material</button>
          </div>
          <div className="form-actions"><button type="submit" className="secondary" disabled={busy}>{isNew ? 'Create draft' : 'Save draft'}</button></div>
        </form>
      )}

      {!isNew && rfq.status !== 'draft' && (
        <div className="card">
          <div className="card-head"><h2>Price comparison ({rfq.currency})</h2><span className="muted small">Lowest price per line in green</span></div>
          <div className="table-wrap">
            <table className="cost-lines compare">
              <thead>
                <tr><th>Material</th><th className="num">Qty</th>
                  {rfq.suppliers.map((sid) => (
                    <th key={sid} className="num">{supplierName(sid)}
                      {can('record_quote') && <div><button type="button" className="link small" onClick={() => setQuoteFor(sid)}>{cmp.suppliers.some((s) => s.supplier === sid) ? 'Edit prices' : 'Enter prices'}</button></div>}
                    </th>
                  ))}</tr>
              </thead>
              <tbody>
                {rfq.lines.map((l) => {
                  const offers = cmp.lines.find((x) => x.rfq_line === l.id)?.offers || []
                  return (
                    <tr key={l.id}>
                      <td><b>{l.description}</b><div className="muted small">{labelOf(BOM_CATEGORIES, l.category)}{l.colour && ` · ${l.colour}`}</div></td>
                      <td className="num">{qty(l.quantity, l.unit)}</td>
                      {rfq.suppliers.map((sid) => {
                        const o = offers.find((x) => x.supplier === sid)
                        return <td key={sid} className={`num ${o?.best ? 'best' : ''}`}>{o ? <>{num(o.unit_price)}<small className="muted">{num(o.amount, 0)}{o.lead_time_days != null && ` · ${o.lead_time_days}d`}</small></> : <span className="muted">—</span>}</td>
                      })}
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr><td colSpan={2}><b>Total</b></td>
                  {rfq.suppliers.map((sid) => {
                    const s = cmp.suppliers.find((x) => x.supplier === sid)
                    return (
                      <td key={sid} className={`num ${s?.lowest ? 'best' : ''}`}>
                        {s ? <><b>{num(s.total, 0)}</b>{!s.complete && <small className="warn-text">partial</small>}{s.payment_terms && <small className="muted">{s.payment_terms}</small>}</> : <span className="muted">no quote</span>}
                        {can('award') && s?.complete && <div><button type="button" className={s.lowest ? 'approve small-btn' : 'secondary small-btn'} onClick={() => setDialog({ award: sid, name: s.supplier_name, total: s.total })}>Award</button></div>}
                      </td>
                    )
                  })}
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
      {!isNew && <History items={rfq.history} />}

      {quoteFor && <QuoteDialog rfq={rfq} supplierId={quoteFor} name={supplierName(quoteFor)} onClose={() => setQuoteFor(null)} onSaved={(data) => { apply(data); setQuoteFor(null) }} />}
      {dialog === 'cancel' && <ReasonDialog title="Cancel this RFQ?" label="Reason" button="Cancel RFQ" tone="danger" busy={busy} onClose={() => setDialog(null)} onConfirm={(r) => act('cancel', { reason: r })} />}
      {dialog?.award && <ReasonDialog title={`Award to ${dialog.name}?`} text={`A draft PO for ${rfq.currency} ${num(dialog.total, 0)} is created from their prices. The RFQ is then closed.`} button="Award & create PO" tone="approve" busy={busy} onClose={() => setDialog(null)} onConfirm={() => act('award', { supplier: dialog.award })} />}
    </>
  )
}

function QuoteDialog({ rfq, supplierId, name, onClose, onSaved }) {
  const existing = rfq.comparison.suppliers.find((s) => s.supplier === supplierId)
  const price = (lineId) => rfq.comparison.lines.find((x) => x.rfq_line === lineId)?.offers.find((o) => o.supplier === supplierId)
  const [form, setForm] = useState(() => ({
    currency: existing?.currency || rfq.currency, payment_terms: existing?.payment_terms || '', valid_until: existing?.valid_until || '', notes: existing?.notes || '',
    lines: Object.fromEntries(rfq.lines.map((l) => [l.id, { unit_price: price(l.id)?.unit_price ?? '', lead_time_days: price(l.id)?.lead_time_days ?? '' }])),
  }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const setLine = (lid, patch) => setForm((f) => ({ ...f, lines: { ...f.lines, [lid]: { ...f.lines[lid], ...patch } } }))
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const { data } = await api.post(`/rfqs/${rfq.id}/quotes/`, {
        supplier: supplierId, currency: form.currency, payment_terms: form.payment_terms, valid_until: form.valid_until || null, notes: form.notes,
        lines: Object.entries(form.lines).filter(([, v]) => v.unit_price !== '').map(([lid, v]) => ({ rfq_line: Number(lid), unit_price: v.unit_price, lead_time_days: v.lead_time_days === '' ? null : v.lead_time_days })),
      })
      onSaved(data)
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }
  return (
    <Modal title={`Prices from ${name}`} onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="table-wrap">
          <table className="cost-lines">
            <thead><tr><th>Material</th><th className="num">Qty</th><th className="num">Price / unit</th><th className="num">Lead time (days)</th><th className="num">Amount</th></tr></thead>
            <tbody>
              {rfq.lines.map((l) => (
                <tr key={l.id}>
                  <td>{l.description}</td><td className="num">{qty(l.quantity, l.unit)}</td>
                  <td><input className="num w-md" type="number" min="0" step="0.01" value={form.lines[l.id].unit_price} onChange={(e) => setLine(l.id, { unit_price: e.target.value })} aria-label={`Price ${l.description}`} /></td>
                  <td><input className="num w-sm" type="number" min="0" step="1" value={form.lines[l.id].lead_time_days} onChange={(e) => setLine(l.id, { lead_time_days: e.target.value })} aria-label={`Lead time ${l.description}`} /></td>
                  <td className="num">{form.lines[l.id].unit_price !== '' ? num(Number(l.quantity) * Number(form.lines[l.id].unit_price), 0) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="form-grid" style={{ marginTop: 12 }}>
          <FormField field={{ name: 'currency', label: 'Currency' }} value={form.currency} onChange={set} />
          <FormField field={{ name: 'payment_terms', label: 'Payment terms offered' }} value={form.payment_terms} onChange={set} />
          <FormField field={{ name: 'valid_until', label: 'Prices valid until', type: 'date' }} value={form.valid_until} onChange={set} />
          <FormField field={{ name: 'notes', label: 'Notes', type: 'textarea', full: true }} value={form.notes} onChange={set} />
        </div>
        <p className="muted small">Leave a price empty if the supplier didn’t quote that material. Only suppliers who priced every line can be awarded.</p>
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy}>Save prices</button>
        </div></div>
      </form>
    </Modal>
  )
}
