import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import useOptions from '../components/useOptions'
import History from '../components/merch/History'
import ReasonDialog from '../components/merch/ReasonDialog'
import { money, num } from '../components/merch/constants'
import ProcBadge from '../components/proc/ProcBadge'
import { qty } from '../components/proc/constants'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { fmtDate, fmtDateTime } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)
const blankPO = () => ({ supplier: '', requirement: null, order_date: todayStr(), delivery_date: '', currency: 'INR', payment_terms: '', delivery_address: '', notes: '', lines: [] })

export default function PurchaseOrderDetail() {
  const { id } = useParams()
  const isNew = id === undefined
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [po, setPo] = useState(null)
  const [form, setForm] = useState(() => (isNew && !query.get('mr') ? blankPO() : null))
  const [company, setCompany] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)

  const apply = (data) => { setPo(data); setCompany(data.company); setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) }) }
  const load = useCallback(() => {
    if (!isNew) { api.get(`/purchase-orders/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))); return }
    const mrId = query.get('mr')
    if (!mrId) return
    const base = blankPO()
    const ids = (query.get('lines') || '').split(',').map(Number)
    api.get(`/material-requirements/${mrId}/`).then(({ data }) => {
      setCompany(data.company)
      setForm({
        ...base, requirement: data.id, delivery_date: data.needed_by || '',
        lines: data.lines.filter((l) => ids.includes(l.id) && Number(l.open_qty) > 0).map((l) => ({
          requirement_line: l.id, mr_no: data.mr_no, category: l.category, description: l.description, colour: l.colour,
          unit: l.unit, quantity: l.open_qty, unit_price: '', required_qty: l.required_qty, ordered_total: l.ordered_qty,
        })),
      })
    }).catch((e) => setError(errorMessage(e)))
  }, [id, isNew, query])
  useEffect(() => { load() }, [load])
  const suppliers = useOptions('/suppliers/', company ? { company, is_active: true } : { is_active: true })

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => (isNew ? a === 'edit' : po.allowed_actions.includes(a))
  const editable = can('edit')
  const set = (name, v) => { setSaved(false); setForm((f) => ({ ...f, [name]: v })) }
  const setLine = (i, patch) => set('lines', form.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const total = form.lines.reduce((a, l) => a + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0)
  const pickSupplier = (n, v) => {
    const s = suppliers.find((x) => String(x.id) === String(v))
    setForm((f) => ({ ...f, supplier: v, payment_terms: f.payment_terms || s?.payment_terms || '' }))
  }

  const save = async (e) => {
    e?.preventDefault(); setBusy(true); setError('')
    const body = {
      supplier: form.supplier, requirement: form.requirement, order_date: form.order_date, delivery_date: form.delivery_date || null,
      currency: form.currency, payment_terms: form.payment_terms, delivery_address: form.delivery_address, notes: form.notes,
      lines: form.lines.map(({ requirement_line, category, description, colour, unit, quantity, unit_price }) => ({ requirement_line: requirement_line || null, category, description, colour, unit, quantity, unit_price })),
    }
    try {
      const { data } = isNew ? await api.post('/purchase-orders/', body) : await api.put(`/purchase-orders/${id}/`, body)
      if (isNew) navigate(`/purchase-orders/${data.id}`, { replace: true })
      else { apply(data); setSaved(true) }
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }
  const act = async (action, body = {}) => {
    setBusy(true); setError('')
    try { const { data } = await api.post(`/purchase-orders/${id}/${action}/`, body); apply(data); setDialog(null) } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const approve = async () => { if (await save()) act('approve') }

  return (
    <>
      <div className="crumbs small no-print"><Link to="/purchase-orders">Supplier POs</Link> / {isNew ? 'New' : po.po_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{isNew ? 'New purchase order' : `Purchase order ${po.po_no}`} {!isNew && <ProcBadge kind="po" status={po.status} />}</h1>
          {!isNew && <p className="muted">{po.supplier_name}{po.mr_no && <> · <Link to={`/requirements/${po.requirement}`}>{po.mr_no}</Link></>}{po.rfq_no && <> · <Link to={`/rfqs/${po.rfq}`}>{po.rfq_no}</Link></>}</p>}
        </div>
        <div className="actions no-print">
          {!isNew && po.status !== 'draft' && <button className="secondary" onClick={() => window.print()}>Print</button>}
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')} disabled={busy}>Cancel PO</button>}
          {can('approve') && <button className="approve" onClick={approve} disabled={busy}>Save & approve</button>}
          {can('send') && <button onClick={() => setDialog('send')} disabled={busy}>Mark sent to supplier</button>}
          {po?.status === 'sent' && po.lines.some((l) => Number(l.received_qty) < Number(l.quantity)) && <Link className="button" to={`/receipts/new?po=${po.id}`}>Receive goods</Link>}
        </div>
      </div>
      <div className="no-print">
        {error && <div className="error">{error}</div>}
        {po?.status === 'draft' && <div className="notice">A manager approves the PO before it goes to the supplier.</div>}
        {po?.status === 'approved' && <div className="notice">Approved by {po.approved_by_name} on {fmtDateTime(po.approved_at)}. Print or email it to {po.supplier_email || 'the supplier'}, then mark it sent.</div>}
        {po?.status === 'sent' && <div className="notice ok">Sent to the supplier on {fmtDateTime(po.sent_at)}. Goods are received in the Inventory module.</div>}
        {po?.status === 'cancelled' && <div className="notice warn"><b>Cancelled:</b>&nbsp;{po.cancel_reason}</div>}
      </div>

      {!isNew && (
        <div className="print-only print-parties">
          <div><small>From</small><b>{po.company_name}</b><pre>{po.company_address}</pre></div>
          <div><small>To</small><b>{po.supplier_name}</b><pre>{po.supplier_address}</pre></div>
        </div>
      )}
      <form onSubmit={save}>
        <fieldset className="plain" disabled={!editable}>
          <div className="card">
            <div className="form-grid">
              <FormField field={{ name: 'supplier', label: 'Supplier', type: 'select', required: true, options: suppliers.map((s) => ({ value: s.id, label: `${s.name} (${s.city})` })) }}
                value={form.supplier} onChange={pickSupplier} />
              <FormField field={{ name: 'order_date', label: 'PO date', type: 'date', required: true }} value={form.order_date} onChange={set} />
              <FormField field={{ name: 'delivery_date', label: 'Delivery date', type: 'date' }} value={form.delivery_date} onChange={set} />
              <FormField field={{ name: 'currency', label: 'Currency' }} value={form.currency} onChange={set} />
              <FormField field={{ name: 'payment_terms', label: 'Payment terms' }} value={form.payment_terms} onChange={set} />
              <FormField field={{ name: 'delivery_address', label: 'Deliver to', type: 'textarea', full: true }} value={form.delivery_address} onChange={set} />
              <FormField field={{ name: 'notes', label: 'Notes for the supplier', type: 'textarea', full: true }} value={form.notes} onChange={set} />
            </div>
          </div>
          <div className="card">
            <h2>Items</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Type</th><th>Material</th><th>Colour</th><th className="num">Quantity</th><th>Unit</th><th className="num">Price / unit</th><th className="num">Amount</th><th className="no-print">{po?.status === 'sent' ? 'Received' : ''}</th></tr></thead>
                <tbody>
                  {form.lines.length === 0 && <tr><td colSpan={8} className="muted center">No items yet.</td></tr>}
                  {form.lines.map((l, i) => {
                    const over = l.required_qty != null && isNew
                      ? Number(l.ordered_total || 0) + Number(l.quantity || 0) > Number(l.required_qty)
                      : l.required_qty != null && Number(l.ordered_total) > Number(l.required_qty)
                    return (
                      <tr key={l.id ?? `n${i}`}>
                        <td><select value={l.category} onChange={(e) => setLine(i, { category: e.target.value })} aria-label="Type">{BOM_CATEGORIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></td>
                        <td><input className="pom" value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} required aria-label="Material" />
                          {l.mr_no && <small className={`no-print ${over ? 'neg' : 'muted'}`}>{l.mr_no}: need {qty(l.required_qty)}{over && ' — this PO orders more'}</small>}</td>
                        <td><input className="w-md" value={l.colour} onChange={(e) => setLine(i, { colour: e.target.value })} aria-label="Colour" /></td>
                        <td><input className="num w-md" type="number" min="0.01" step="0.01" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} required aria-label="Quantity" /></td>
                        <td><input className="w-xs" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} aria-label="Unit" /></td>
                        <td><input className="num w-md" type="number" min="0" step="0.01" value={l.unit_price} onChange={(e) => setLine(i, { unit_price: e.target.value })} required aria-label="Price" /></td>
                        <td className="num">{num((Number(l.quantity) || 0) * (Number(l.unit_price) || 0))}</td>
                        <td className="no-print">{editable ? <button type="button" className="link" onClick={() => set('lines', form.lines.filter((_, j) => j !== i))} aria-label="Remove">✕</button>
                          : po?.status === 'sent' && <span className={`small ${Number(l.received_qty) >= Number(l.quantity) ? 'pos' : 'muted'}`}>{qty(l.received_qty)}{Number(l.accepted_qty) > 0 && <><br />{qty(l.accepted_qty)} accepted</>}</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot><tr><td colSpan={6}>{editable && <button type="button" className="secondary no-print" onClick={() => set('lines', [...form.lines, { category: 'trim', description: '', colour: '', unit: 'pc', quantity: '', unit_price: '' }])}>+ Add item</button>}</td>
                  <td className="num"><b>{money(total, form.currency)}</b></td><td className="no-print" /></tr></tfoot>
              </table>
            </div>
          </div>
        </fieldset>
        {editable && <div className="form-actions no-print">{saved && <span className="pos small">✓ Saved</span>}<button type="submit" className="secondary" disabled={busy}>{isNew ? 'Create draft' : 'Save draft'}</button></div>}
      </form>
      {!isNew && <div className="no-print"><History items={po.history} /></div>}
      {!isNew && po.delivery_date && <p className="print-only">Delivery by {fmtDate(po.delivery_date)}. Please quote {po.po_no} on your invoice and delivery challan.</p>}

      {dialog === 'cancel' && <ReasonDialog title={`Cancel ${po.po_no}?`} text="The quantity becomes open again on the material requirement." label="Reason" required button="Cancel PO" tone="danger" busy={busy} onClose={() => setDialog(null)} onConfirm={(r) => act('cancel', { reason: r })} />}
      {dialog === 'send' && <ReasonDialog title="Sent to the supplier?" text={`Confirm ${po.po_no} has been emailed or handed to ${po.supplier_name}.`} button="Mark sent" busy={busy} onClose={() => setDialog(null)} onConfirm={() => act('send')} />}
    </>
  )
}
