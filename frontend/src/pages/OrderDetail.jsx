import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import FormField from '../components/FormField'
import useOptions from '../components/useOptions'
import DocBadge from '../components/merch/DocBadge'
import DocLines from '../components/merch/DocLines'
import History from '../components/merch/History'
import ReasonDialog from '../components/merch/ReasonDialog'
import { money } from '../components/merch/constants'
import { PAYMENT_TERMS, fmtDate, fmtDateTime, labelOf } from '../components/buyers/constants'

const FIELDS = [
  { name: 'buyer_po_no', label: 'Buyer PO number', required: true },
  { name: 'po_date', label: 'PO date', type: 'date' },
  { name: 'ship_date', label: 'Shipment date', type: 'date', required: true },
  { name: 'delivery_port', label: 'Port' },
  { name: 'notes', label: 'Notes', type: 'textarea', full: true },
]

function CreditPanel({ credit, currency }) {
  if (!credit) return null
  if (!credit.has_limit) return <div className="card credit-panel bad"><h2>Credit</h2><p>This buyer has no approved credit limit.</p></div>
  const limit = Number(credit.limit) || 0
  const used = credit.currency_matches ? Number(credit.exposure) : 0
  const mine = Number(credit.this_order)
  const pct = (v) => (limit ? Math.min(100, (v / limit) * 100) : 0)
  const over = !credit.within_limit
  return (
    <div className={`card credit-panel ${over ? 'bad' : 'good'}`}>
      <div className="card-head">
        <h2>Credit limit</h2>
        <span className={`badge ${over ? 'badge-oc-cancelled' : 'badge-oc-confirmed'}`}>{over ? 'Over limit' : 'Within limit'}</span>
      </div>
      {!credit.currency_matches && <p className="neg small">The limit is in {credit.currency} but this order is in {currency} — a manager must confirm it.</p>}
      <div className="credit-bar" role="img" aria-label={`Credit used ${Math.round(pct(used + mine))}%`}>
        <span className="used" style={{ width: `${pct(used)}%` }} />
        <span className="mine" style={{ width: `${Math.max(0, Math.min(100 - pct(used), pct(mine)))}%` }} />
      </div>
      <dl className="summary">
        <div><dt>Approved limit ({labelOf(PAYMENT_TERMS, credit.payment_terms)})</dt><dd>{money(credit.limit, credit.currency)}</dd></div>
        <div><dt><i className="sw used" />Other confirmed orders</dt><dd>{money(credit.exposure, currency)}</dd></div>
        <div><dt><i className="sw mine" />This order</dt><dd>{money(credit.this_order, currency)}</dd></div>
        <div className="sub"><dt>After this order</dt><dd className={over ? 'neg' : 'pos'}>{money(credit.after_order, currency)}</dd></div>
      </dl>
    </div>
  )
}

export default function OrderDetail() {
  const { id } = useParams()
  const { canManage } = useAuth()
  const [order, setOrder] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)

  const apply = (data) => { setOrder(data); setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) }) }
  const load = useCallback(() => api.get(`/order-confirmations/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])
  const sheets = useOptions(order ? '/cost-sheets/' : null, order ? { buyer: order.buyer, status: 'approved', currency: order.currency } : null)

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => order.allowed_actions.includes(a)
  const editable = can('edit')
  const set = (name, v) => { setSaved(false); setForm((f) => ({ ...f, [name]: v })) }

  const save = async (e) => {
    e?.preventDefault()
    setBusy(true); setError('')
    try {
      const { data } = await api.patch(`/order-confirmations/${id}/`, {
        buyer_po_no: form.buyer_po_no, po_date: form.po_date || null, ship_date: form.ship_date || null,
        delivery_port: form.delivery_port, notes: form.notes,
        lines: form.lines.map((l) => ({ cost_sheet: l.cost_sheet, style_no: l.style_no, description: l.description, quantity: l.quantity, unit_price: l.unit_price })),
      })
      apply(data); setSaved(true)
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }

  const act = async (action, body = {}) => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/order-confirmations/${id}/${action}/`, body)
      apply(data); setDialog(null)
    } catch (err) {
      setError(errorMessage(err)); setDialog(null)
    } finally { setBusy(false) }
  }

  const confirm = async () => {
    const data = await save()
    if (!data) return
    if (data.credit.within_limit) setDialog('confirm')
    else if (canManage) setDialog('override')
    else setError('This order is over the buyer’s credit limit. Ask a manager to confirm it.')
  }

  const dialogs = {
    confirm: { title: `Confirm order ${order.oc_no}?`, text: `Confirms PO ${form.buyer_po_no} for ${money(order.total_amount, order.currency)}. The order is then locked.`, button: 'Confirm order', tone: 'approve', run: () => act('confirm') },
    override: { title: 'Confirm over the credit limit?', text: 'This order is over the buyer’s approved credit limit. Say why it is safe to go ahead — it is recorded on the order.', label: 'Reason, e.g. LC received for full value', required: true, button: 'Confirm anyway', tone: 'danger', run: (r) => act('confirm', { override_reason: r }) },
    cancel: { title: `Cancel order ${order.oc_no}?`, label: 'Reason', required: true, button: 'Cancel order', tone: 'danger', run: (r) => act('cancel', { reason: r }) },
  }

  return (
    <>
      <div className="crumbs small"><Link to="/orders">Order confirmations</Link> / {order.oc_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{order.oc_no} <DocBadge kind="oc" status={order.status} /></h1>
          <p className="muted"><Link to={`/buyers/${order.buyer}`}>{order.buyer_name}</Link> · from <Link to={`/quotations/${order.quotation}`}>{order.quote_no}</Link> · {order.incoterm} · {labelOf(PAYMENT_TERMS, order.payment_terms)}</p>
        </div>
        <div className="actions">
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')} disabled={busy}>Cancel order</button>}
          {can('confirm') && <button className="approve" onClick={confirm} disabled={busy}>Confirm order</button>}
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {order.status === 'draft' && <div className="notice">Enter the buyer’s PO number and shipment date, check quantities against the PO, then confirm.</div>}
      {order.status === 'confirmed' && (
        <div className="notice ok">Confirmed by {order.confirmed_by_name} on {fmtDateTime(order.confirmed_at)}.{order.credit_override && <> Credit limit overridden: {order.override_reason}</>}</div>
      )}
      {order.status === 'cancelled' && <div className="notice warn"><b>Cancelled:</b>&nbsp;{order.cancel_reason}</div>}

      <div className="order-layout">
        <div>
          <form onSubmit={save}>
            <fieldset className="plain" disabled={!editable}>
              <div className="card">
                <h2>Buyer PO</h2>
                <div className="form-grid">
                  {FIELDS.map((f) => <FormField key={f.name} field={f} value={form[f.name]} onChange={set} />)}
                </div>
              </div>
              <div className="card">
                <h2>Styles</h2>
                <DocLines lines={form.lines} onChange={(lines) => set('lines', lines)} editable={editable} currency={order.currency} sheets={sheets} />
              </div>
            </fieldset>
            {editable && (
              <div className="form-actions">
                {saved && <span className="pos small">✓ Saved</span>}
                <button type="submit" className="secondary" disabled={busy}>Save draft</button>
              </div>
            )}
          </form>
          <History items={order.history} />
        </div>
        <aside>
          <CreditPanel credit={order.credit} currency={order.currency} />
          <div className="card">
            <h2>Summary</h2>
            <dl className="summary">
              <div><dt>Pieces</dt><dd>{Number(order.total_quantity).toLocaleString('en-IN')}</dd></div>
              <div><dt>Ship date</dt><dd>{fmtDate(order.ship_date)}</dd></div>
              <div className="sub"><dt>Order value</dt><dd>{money(order.total_amount, order.currency)}</dd></div>
            </dl>
          </div>
        </aside>
      </div>

      {dialog && <ReasonDialog {...dialogs[dialog]} busy={busy} onClose={() => setDialog(null)} onConfirm={dialogs[dialog].run} />}
    </>
  )
}
