import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { downloadFile, errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Modal from '../components/Modal'
import ResourcePage from '../components/ResourcePage'
import useOptions from '../components/useOptions'
import History from '../components/merch/History'
import ReasonDialog from '../components/merch/ReasonDialog'
import { money } from '../components/merch/constants'
import { pcs } from '../components/prod/constants'
import { fmtDate } from '../components/buyers/constants'

const STEPS = [['planned', 'Planned'], ['booked', 'Booked'], ['shipped', 'Shipped'], ['delivered', 'Delivered']]
const DOC_STATUSES = [['pending', 'Pending'], ['ready', 'Ready'], ['sent', 'Sent'], ['not_needed', 'Not needed']]
const todayStr = () => new Date().toISOString().slice(0, 10)

export default function ExportShipments() {
  const { id } = useParams()
  return id ? <ShipmentDetail id={id === 'new' ? null : id} /> : <ShipmentList />
}

function ShipmentList() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Export Shipments"
      subtitle="Booking, container, vessel and export documents for each shipment"
      endpoint="/export-shipments/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={<>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All</option>{[...STEPS, ['cancelled', 'Cancelled']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <button onClick={() => navigate('/shipments/new')}>+ New shipment</button>
      </>}
      onRowClick={(r) => navigate(`/shipments/${r.id}`)}
      columns={[
        { key: 'shipment_no', label: 'Shipment', render: (r) => <>{r.shipment_no}<div className="muted small">{r.invoice_no}</div></> },
        { key: 'oc_no', label: 'Order', render: (r) => <><b>{r.oc_no}</b><div className="muted small">{r.buyer_name} · {r.buyer_country}</div></> },
        { key: 'mode', label: 'Mode / to', render: (r) => <><span className="cap">{r.mode}</span><div className="muted small">{r.port_of_discharge || '—'}</div></> },
        { key: 'vessel', label: 'Vessel / flight' },
        { key: 'etd', label: 'ETD / on board', render: (r) => <>{fmtDate(r.etd)}{r.on_board_date && <div className="pos small">on board {fmtDate(r.on_board_date)}</div>}</> },
        { key: 'totals', label: 'Cartons / pcs', num: true, render: (r) => <>{r.totals.cartons}<div className="muted small">{pcs(r.totals.pcs)} pcs</div></> },
        { key: 'status', label: 'Status', render: (r) => <span className={`badge badge-sh-${r.status}`}>{r.status_label}</span> },
      ]}
      fields={[]}
    />
  )
}

function ShipmentDetail({ id }) {
  const { canFinance } = useAuth()
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [s, setS] = useState(null)
  const [form, setForm] = useState(() => (id ? null : { order: query.get('order') || '', mode: 'sea', port_of_loading: '', port_of_discharge: '', final_destination: '', forwarder: '', carrier: '', vessel: '', voyage: '', container_type: '', container_no: '', seal_no: '', etd: '', eta: '', bl_no: '', shipping_bill_no: '', shipping_bill_date: '', hs_codes: {}, notes: '', packing_list_ids: query.get('pl') ? [Number(query.get('pl'))] : [] }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)
  const [saved, setSaved] = useState(false)
  const orders = useOptions(id ? null : '/order-confirmations/', id ? null : { status: 'confirmed' })
  const orderId = form?.order
  const lists = useOptions(orderId ? '/packing-lists/' : null, orderId ? { order: orderId, status: 'finalized' } : null)

  const apply = (data) => { setS(data); setForm({ ...data, packing_list_ids: data.packing_lists.map((p) => p.id), hs_codes: { ...data.hs_codes } }) }
  const load = useCallback(() => { if (id) api.get(`/export-shipments/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))) }, [id])
  useEffect(() => { load() }, [load])

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => (!s ? a === 'edit' : s.allowed_actions.includes(a))
  const editable = can('edit')
  const set = (n, v) => { setSaved(false); setForm((f) => ({ ...f, [n]: v })) }
  const available = lists.filter((p) => !p.shipment || p.shipment === s?.id)
  const styles = s ? s.invoice.lines.map((l) => l.style_no) : []
  const stepIdx = STEPS.findIndex(([k]) => k === s?.status)

  const fieldsBody = () => {
    const keys = ['mode', 'port_of_loading', 'port_of_discharge', 'final_destination', 'forwarder', 'carrier', 'vessel', 'voyage', 'container_type', 'container_no', 'seal_no', 'etd', 'eta', 'bl_no', 'shipping_bill_no', 'shipping_bill_date', 'notes', 'hs_codes']
    const body = Object.fromEntries(keys.map((k) => [k, ['etd', 'eta', 'shipping_bill_date'].includes(k) ? form[k] || null : form[k]]))
    if (!form.port_of_loading) delete body.port_of_loading
    if (!form.final_destination) delete body.final_destination
    return body
  }
  const save = async () => {
    setBusy(true); setError('')
    try {
      const body = editable ? { ...fieldsBody(), packing_list_ids: form.packing_list_ids } : { notes: form.notes, hs_codes: form.hs_codes, eta: form.eta || null, shipping_bill_date: form.shipping_bill_date || null }
      const { data } = s ? await api.patch(`/export-shipments/${s.id}/`, body) : await api.post('/export-shipments/', { order: form.order, ...body })
      if (!s) navigate(`/shipments/${data.id}`, { replace: true })
      else { apply(data); setSaved(true) }
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }
  const act = async (action, body = {}) => {
    setBusy(true); setError('')
    try {
      if (editable && action !== 'cancel') { const ok = await save(); if (!ok) return }
      apply((await api.post(`/export-shipments/${s.id}/${action}/`, body)).data); setDialog(null)
    } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const updateDoc = async (doc, patch) => {
    try { await api.patch(`/export-documents/${doc.id}/`, patch); load() } catch (err) { setError(errorMessage(err)) }
  }
  const F = (name, label, extra = {}) => (
    <label className="field"><span>{label}</span><input value={form[name] ?? ''} onChange={(e) => set(name, e.target.value)} {...extra} /></label>
  )

  return (
    <>
      <div className="crumbs small"><Link to="/shipments">Export shipments</Link> / {s ? s.shipment_no : 'New'}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{s ? s.shipment_no : 'New export shipment'} {s && <span className={`badge badge-sh-${s.status}`}>{s.status_label}</span>}</h1>
          {s && <p className="muted"><Link to={`/orders/${s.order}`}>{s.oc_no}</Link> · {s.buyer_name} · PO {s.buyer_po_no} · {s.incoterm} · agreed ship date {fmtDate(s.ship_date)}</p>}
        </div>
        <div className="actions">
          {s && s.packing_lists.length > 0 && <button className="secondary" onClick={() => downloadFile(`/export-shipments/${s.id}/commercial-invoice/`, `${s.invoice_no}.pdf`)}>Commercial invoice PDF</button>}
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')} disabled={busy}>Cancel</button>}
          {(editable || can('edit_docs')) && <button className="secondary" onClick={save} disabled={busy}>{s ? 'Save' : 'Create shipment'}</button>}
          {can('book') && <button onClick={() => act('book')} disabled={busy}>Book</button>}
          {can('ship') && <button className="approve" onClick={() => setDialog('ship')} disabled={busy}>Mark shipped</button>}
          {can('deliver') && <button onClick={() => act('deliver')} disabled={busy}>Mark delivered</button>}
          {s && ['shipped', 'delivered'].includes(s.status) && (s.sales_invoice_id
            ? <Link className="button secondary" to={`/finance/invoices/${s.sales_invoice_id}`}>Sales invoice →</Link>
            : canFinance && <button className="approve" onClick={() => setDialog('invoice')}>Create sales invoice</button>)}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {saved && <div className="notice ok">Saved.</div>}
      {s && s.status !== 'cancelled' && (
        <ol className="stepper card stepper-card ship-steps">
          {STEPS.map(([k, l], i) => (
            <li key={k} className={`step ${i < stepIdx || (i === stepIdx && k === 'delivered') ? 'done' : i === stepIdx ? 'current' : 'todo'}`}>
              <span className="step-btn"><span className="dot">{i < stepIdx || (i === stepIdx && k === 'delivered') ? '✓' : i + 1}</span><span className="step-label">{l}
                {k === 'shipped' && s.on_board_date && <small><br />{fmtDate(s.on_board_date)}</small>}</span></span>
            </li>
          ))}
        </ol>
      )}
      {s?.status === 'cancelled' && <div className="notice warn"><b>Cancelled:</b>&nbsp;{s.cancel_reason}</div>}
      {s?.warnings.length > 0 && <div className="notice warn block"><ul>{s.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>}

      <div className="order-layout">
        <div>
          <fieldset className="plain" disabled={!editable}>
            <div className="card">
              <h2>Routing</h2>
              <div className="form-grid">
                {!s && <label className="field"><span>Confirmed order *</span>
                  <select value={form.order} onChange={(e) => setForm((f) => ({ ...f, order: e.target.value, packing_list_ids: [] }))} required>
                    <option value="">— choose —</option>{orders.map((o) => <option key={o.id} value={o.id}>{o.oc_no} · {o.buyer_name} · PO {o.buyer_po_no}</option>)}</select></label>}
                <label className="field"><span>Mode</span><select value={form.mode} onChange={(e) => set('mode', e.target.value)}>{['sea', 'air', 'road', 'courier'].map((m) => <option key={m} value={m}>{m[0].toUpperCase() + m.slice(1)}</option>)}</select></label>
                {F('port_of_loading', 'Port of loading', { placeholder: 'Chennai, India' })}
                {F('port_of_discharge', 'Port of discharge *')}
                {F('final_destination', 'Final destination')}
                {F('forwarder', 'Forwarder *')}
                {F('carrier', 'Shipping line / airline')}
                <label className="field"><span>ETD *</span><input type="date" value={form.etd || ''} onChange={(e) => set('etd', e.target.value)} /></label>
              </div>
            </div>
            <div className="card">
              <h2>Vessel, container & customs</h2>
              <div className="form-grid">
                {F('vessel', form.mode === 'air' ? 'Flight' : 'Vessel')}
                {F('voyage', 'Voyage no.')}
                {form.mode === 'sea' && <label className="field"><span>Container type</span><select value={form.container_type} onChange={(e) => set('container_type', e.target.value)}><option value="">—</option>{['20GP', '40GP', '40HC', 'LCL'].map((c) => <option key={c}>{c}</option>)}</select></label>}
                {form.mode === 'sea' && F('container_no', 'Container no.')}
                {form.mode === 'sea' && F('seal_no', 'Seal no.')}
                {F('bl_no', form.mode === 'air' ? 'AWB no.' : 'B/L no.')}
                {F('shipping_bill_no', 'Shipping bill no.')}
              </div>
              <p className="muted small">Needed before marking shipped: {form.mode === 'air' ? 'flight' : 'vessel'}, {form.mode === 'air' ? 'AWB' : 'B/L'} number, shipping bill number{form.mode === 'sea' && ', container type'}.</p>
            </div>
          </fieldset>
          <div className="card">
            <h2>Dates, HS codes & notes</h2>
            <div className="form-grid">
              <label className="field"><span>ETA</span><input type="date" value={form.eta || ''} onChange={(e) => set('eta', e.target.value)} disabled={!editable && !can('edit_docs')} /></label>
              <label className="field"><span>Shipping bill date</span><input type="date" value={form.shipping_bill_date || ''} onChange={(e) => set('shipping_bill_date', e.target.value)} disabled={!editable && !can('edit_docs')} /></label>
              {styles.map((st) => (
                <label key={st} className="field"><span>HS code · {st}</span><input value={form.hs_codes[st] || ''} onChange={(e) => set('hs_codes', { ...form.hs_codes, [st]: e.target.value })} placeholder="e.g. 61091000" disabled={!editable && !can('edit_docs')} /></label>
              ))}
              <label className="field full"><span>Notes</span><textarea rows={2} value={form.notes} onChange={(e) => set('notes', e.target.value)} disabled={!editable && !can('edit_docs')} /></label>
            </div>
          </div>

          <div className="card">
            <h2>Packing lists</h2>
            {!form.order ? <p className="muted small">Choose the order.</p> : available.length === 0 ? <p className="muted small">No finalized packing lists for this order. <Link to={`/packing/new?order=${form.order}`}>Make one</Link>.</p> : (
              <div className="pl-pick">
                {available.map((p) => {
                  const on = form.packing_list_ids.includes(p.id)
                  return (
                    <label key={p.id} className={`pl-chip ${on ? 'on' : ''}`}>
                      <input type="checkbox" checked={on} disabled={!editable} onChange={() => set('packing_list_ids', on ? form.packing_list_ids.filter((x) => x !== p.id) : [...form.packing_list_ids, p.id])} />
                      <span><b>{p.pl_no}</b><small>{p.total_cartons} ctns · {pcs(p.total_pcs)} pcs · {Number(p.gross_weight).toLocaleString('en-IN')} kg · {p.cbm} m³</small></span>
                      {s && <button type="button" className="link small" onClick={(e) => { e.preventDefault(); downloadFile(`/packing-lists/${p.id}/pdf/`, `${p.pl_no}.pdf`) }}>PDF</button>}
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          {s && (
            <div className="card">
              <h2>Commercial invoice {s.invoice_no}</h2>
              <div className="table-wrap">
                <table className="cost-lines">
                  <thead><tr><th>Style</th><th>HS code</th><th className="num">Cartons</th><th className="num">Pcs</th><th className="num">Price</th><th className="num">Amount</th></tr></thead>
                  <tbody>
                    {s.invoice.lines.length === 0 && <tr><td colSpan={6} className="muted center">Add packing lists.</td></tr>}
                    {s.invoice.lines.map((l) => (
                      <tr key={l.style_no}><td><b>{l.style_no}</b><div className="muted small">{l.description}</div></td><td>{l.hs_code || <span className="neg small">missing</span>}</td>
                        <td className="num">{l.cartons}</td><td className="num">{pcs(l.pcs)}</td><td className="num">{Number(l.unit_price).toFixed(2)}</td><td className="num">{money(l.amount, s.currency)}</td></tr>
                    ))}
                  </tbody>
                  <tfoot><tr><td colSpan={5}><b>Total</b></td><td className="num"><b>{money(s.invoice.total, s.currency)}</b></td></tr></tfoot>
                </table>
              </div>
            </div>
          )}
          {s && <History items={s.history} />}
        </div>
        <aside>
          {s && (
            <div className="card">
              <h2>Shipment</h2>
              <dl className="summary">
                <div><dt>Cartons</dt><dd>{s.totals.cartons}</dd></div>
                <div><dt>Pieces</dt><dd>{pcs(s.totals.pcs)}</dd></div>
                <div><dt>Net weight</dt><dd>{Number(s.totals.net_weight).toLocaleString('en-IN')} kg</dd></div>
                <div><dt>Gross weight</dt><dd>{Number(s.totals.gross_weight).toLocaleString('en-IN')} kg</dd></div>
                <div className="sub"><dt>Volume</dt><dd>{Number(s.totals.cbm).toFixed(3)} m³</dd></div>
              </dl>
              {form.mode === 'sea' && <p className="muted small">A 20GP holds about 28 m³ of cartons, a 40HC about 68 m³.</p>}
            </div>
          )}
          {s && (
            <div className="card">
              <h2>Export documents</h2>
              <div className="doc-list">
                {s.documents.map((d) => (
                  <div key={d.id} className={`doc-row doc-${d.status}`}>
                    <div><b>{d.label}</b>{d.generated && <small className="muted"> · from the ERP</small>}
                      <div className="small muted">{d.number || 'No number'}{d.date && ` · ${fmtDate(d.date)}`}</div></div>
                    <select value={d.status} onChange={(e) => updateDoc(d, { status: e.target.value })} disabled={s.status === 'cancelled'} aria-label={`${d.label} status`}>
                      {DOC_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                    {!d.generated && s.status !== 'cancelled' && <button className="link small" onClick={() => setDialog({ doc: d })}>Edit</button>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>

      {dialog === 'cancel' && <ReasonDialog title={`Cancel ${s.shipment_no}?`} text="The packing lists become free for another shipment." label="Reason" required button="Cancel shipment" tone="danger" busy={busy} onClose={() => setDialog(null)} onConfirm={(r) => act('cancel', { reason: r })} />}
      {dialog === 'invoice' && <InvoiceDialog shipment={s} onClose={() => setDialog(null)} onDone={(inv) => navigate(`/finance/invoices/${inv.id}`)} />}
      {dialog === 'ship' && <ShipDialog busy={busy} onClose={() => setDialog(null)} onShip={(d) => act('ship', { on_board_date: d })} />}
      {dialog?.doc && <DocDialog doc={dialog.doc} onClose={() => setDialog(null)} onSave={(patch) => { updateDoc(dialog.doc, patch); setDialog(null) }} />}
    </>
  )
}

function InvoiceDialog({ shipment, onClose, onDone }) {
  const [rate, setRate] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try { onDone((await api.post('/export-invoices/create-from-shipment/', { shipment: shipment.id, exchange_rate: rate })).data) } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }
  const total = Number(shipment.invoice.total)
  return (
    <Modal title={`Sales invoice ${shipment.invoice_no}`} onClose={onClose}>
      <form onSubmit={submit}>
        <p className="muted small">Raises the receivable for {money(total, shipment.currency)}. Use the exchange rate on the shipping bill (customs notified rate).</p>
        <label className="field"><span>Exchange rate (₹ per {shipment.currency}) *</span><input type="number" min="0.0001" step="0.0001" value={rate} onChange={(e) => setRate(e.target.value)} required autoFocus /></label>
        {Number(rate) > 0 && <p className="small">= ₹{(total * Number(rate)).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p>}
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="submit" className="approve" disabled={busy}>Create invoice</button></div></div>
      </form>
    </Modal>
  )
}

function ShipDialog({ busy, onClose, onShip }) {
  const [d, setD] = useState(todayStr)
  return (
    <Modal title="Goods on board?" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onShip(d) }}>
        <p className="muted small">Saves the details, then records the on-board date. The invoice date is set to it, and the B/L and shipping bill are marked ready.</p>
        <label className="field"><span>On-board date</span><input type="date" value={d} max={todayStr()} onChange={(e) => setD(e.target.value)} required /></label>
        <div className="modal-foot"><span /><div><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="submit" className="approve" disabled={busy}>Mark shipped</button></div></div>
      </form>
    </Modal>
  )
}

function DocDialog({ doc, onClose, onSave }) {
  const [f, setF] = useState({ number: doc.number, date: doc.date || '', status: doc.status === 'pending' ? 'ready' : doc.status, note: doc.note })
  return (
    <Modal title={doc.label} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ ...f, date: f.date || null }) }}>
        <div className="form-grid">
          <label className="field"><span>Number</span><input value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} /></label>
          <label className="field"><span>Date</span><input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
          <label className="field"><span>Status</span><select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>{DOC_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label className="field full"><span>Note</span><input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
        </div>
        <div className="modal-foot"><span /><div><button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="submit">Save</button></div></div>
      </form>
    </Modal>
  )
}
