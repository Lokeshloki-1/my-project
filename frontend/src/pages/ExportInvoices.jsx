import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { downloadFile, errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Modal from '../components/Modal'
import ResourcePage from '../components/ResourcePage'
import ReasonDialog from '../components/merch/ReasonDialog'
import { money, num } from '../components/merch/constants'
import { pcs } from '../components/prod/constants'
import { fmtDate } from '../components/buyers/constants'
import { INV_STATUSES, inr } from '../components/fin/constants'

const METHODS = [['tt', 'Telegraphic transfer (TT)'], ['lc', 'Letter of credit'], ['da_dp', 'Collection (DA / DP)'], ['advance', 'Advance']]
const todayStr = () => new Date().toISOString().slice(0, 10)

export default function ExportInvoices() {
  const { id } = useParams()
  return id ? <InvoiceDetail id={id} /> : <InvoiceList />
}

function InvoiceList() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Export Sales Invoices"
      subtitle="One invoice per shipped export shipment, in the buyer's currency with the INR value at the invoice rate"
      endpoint="/export-invoices/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={<select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All</option>{INV_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}
      onRowClick={(r) => navigate(`/finance/invoices/${r.id}`)}
      columns={[
        { key: 'invoice_no', label: 'Invoice', render: (r) => <>{r.invoice_no}<div className="muted small">{r.shipment_no}</div></> },
        { key: 'buyer_name', label: 'Buyer', render: (r) => <><b>{r.buyer_name}</b><div className="muted small">{r.oc_no}</div></> },
        { key: 'invoice_date', label: 'Date', render: (r) => fmtDate(r.invoice_date) },
        { key: 'amount', label: 'Amount', num: true, render: (r) => <><b>{money(r.amount, r.currency)}</b><div className="muted small">{inr(r.amount_inr)}</div></> },
        { key: 'balance', label: 'Balance', num: true, render: (r) => Number(r.balance) ? money(r.balance, r.currency) : <span className="pos">—</span> },
        { key: 'due_date', label: 'Due', render: (r) => <span className={r.days_overdue ? 'neg' : ''}>{fmtDate(r.due_date)}{r.days_overdue > 0 && <div className="small">{r.days_overdue} days overdue</div>}</span> },
        { key: 'status', label: 'Status', render: (r) => <span className={`badge badge-inv-${r.status}`}>{r.status_label}</span> },
      ]}
      fields={[]}
    />
  )
}

function InvoiceDetail({ id }) {
  const { canManage } = useAuth()
  const [inv, setInv] = useState(null)
  const [error, setError] = useState('')
  const [dialog, setDialog] = useState(null)
  const [due, setDue] = useState('')

  const load = useCallback(() => api.get(`/export-invoices/${id}/`).then((r) => { setInv(r.data); setDue(r.data.due_date) }).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])
  if (!inv) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => inv.allowed_actions.includes(a)
  const paidPct = Number(inv.amount) ? Math.min(100, ((Number(inv.amount_received) + Number(inv.bank_charges)) / Number(inv.amount)) * 100) : 0
  const saveDue = async () => { try { setInv((await api.patch(`/export-invoices/${id}/`, { due_date: due })).data) } catch (e) { setError(errorMessage(e)) } }
  const removeReceipt = async (r) => {
    if (!window.confirm(`Delete the receipt of ${money(r.amount, inv.currency)} on ${fmtDate(r.received_on)}?`)) return
    try { await api.delete(`/export-receipts/${r.id}/`); load() } catch (e) { setError(errorMessage(e)) }
  }
  const cancel = async (reason) => { try { setInv((await api.post(`/export-invoices/${id}/cancel/`, { reason })).data); setDialog(null) } catch (e) { setError(errorMessage(e)); setDialog(null) } }

  return (
    <>
      <div className="crumbs small"><Link to="/finance/invoices">Export invoices</Link> / {inv.invoice_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{inv.invoice_no} <span className={`badge badge-inv-${inv.status}`}>{inv.status_label}</span></h1>
          <p className="muted">{inv.buyer_name} · <Link to={`/orders/${inv.order}`}>{inv.oc_no}</Link> · PO {inv.buyer_po_no} · <Link to={`/shipments/${inv.shipment}`}>{inv.shipment_no}</Link> · {inv.payment_terms_label}</p>
        </div>
        <div className="actions">
          <button className="secondary" onClick={() => downloadFile(`/export-invoices/${id}/pdf/`, `${inv.invoice_no}.pdf`)}>Invoice PDF</button>
          <Link className="button secondary" to={`/finance/profit/${inv.order}`}>Order profit</Link>
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')}>Cancel invoice</button>}
          {can('record_receipt') && <button className="approve" onClick={() => setDialog('pay')}>Record payment</button>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {inv.days_overdue > 0 && <div className="notice warn">{inv.days_overdue} days overdue — {money(inv.balance, inv.currency)} was due on {fmtDate(inv.due_date)}.</div>}
      {inv.status === 'cancelled' && <div className="notice warn"><b>Cancelled:</b>&nbsp;{inv.cancel_reason}</div>}

      <div className="wo-kpis">
        <div className="card kpi"><div className="muted small">Invoice value</div><div className="kpi-value">{money(inv.amount, inv.currency)}</div><div className="small muted">{inr(inv.amount_inr)} at {Number(inv.exchange_rate)}</div></div>
        <div className="card kpi"><div className="muted small">Received</div><div className="kpi-value pos">{money(inv.amount_received, inv.currency)}</div><div className="small muted">bank charges {money(inv.bank_charges, inv.currency)}</div></div>
        <div className="card kpi"><div className="muted small">Balance</div><div className={`kpi-value ${Number(inv.balance) ? 'neg' : 'pos'}`}>{money(inv.balance, inv.currency)}</div><div className="small muted">{inr(inv.balance_inr)}</div></div>
        <div className="card kpi"><div className="muted small">Exchange gain / loss</div><div className={`kpi-value ${Number(inv.gain_loss_inr) < 0 ? 'neg' : 'pos'}`}>{inr(inv.gain_loss_inr)}</div><div className="small muted">vs invoice rate</div></div>
      </div>
      <div className="card"><div className="sb-track big"><span className="sb-fill sb-finished" style={{ width: `${paidPct}%` }} /></div><span className="small muted">{Math.round(paidPct)}% settled</span></div>

      <div className="order-layout">
        <div>
          <div className="card">
            <h2>Payments received</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Date</th><th>Method / ref.</th><th className="num">Amount</th><th className="num">Bank charges</th><th className="num">Rate</th><th className="num">INR</th><th className="num">Gain / loss</th>{canManage && <th />}</tr></thead>
                <tbody>
                  {inv.receipts.length === 0 && <tr><td colSpan={8} className="muted center">No payments yet.</td></tr>}
                  {inv.receipts.map((r) => (
                    <tr key={r.id}>
                      <td>{fmtDate(r.received_on)}</td>
                      <td>{r.method_label}<div className="muted small">{r.bank_reference}{r.note && ` · ${r.note}`}</div></td>
                      <td className="num">{money(r.amount, inv.currency)}</td>
                      <td className="num">{Number(r.bank_charges) ? money(r.bank_charges, inv.currency) : '—'}</td>
                      <td className="num">{Number(r.exchange_rate)}</td>
                      <td className="num">{inr(r.amount_inr)}</td>
                      <td className={`num ${Number(r.exchange_gain_loss_inr) < 0 ? 'neg' : 'pos'}`}>{inr(r.exchange_gain_loss_inr)}</td>
                      {canManage && <td><button className="link" onClick={() => removeReceipt(r)} aria-label="Delete receipt">✕</button></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h2>Invoice lines</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Style</th><th>HS code</th><th className="num">Cartons</th><th className="num">Pcs</th><th className="num">Price</th><th className="num">Amount</th></tr></thead>
                <tbody>{inv.lines.map((l) => (
                  <tr key={l.style_no}><td><b>{l.style_no}</b><div className="muted small">{l.description}</div></td><td>{l.hs_code || '—'}</td><td className="num">{l.cartons}</td><td className="num">{pcs(l.pcs)}</td><td className="num">{num(l.unit_price)}</td><td className="num">{money(l.amount, inv.currency)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        </div>
        <aside>
          <div className="card">
            <h2>Terms</h2>
            <dl className="summary">
              <div><dt>Invoice date</dt><dd>{fmtDate(inv.invoice_date)}</dd></div>
              <div><dt>Payment terms</dt><dd>{inv.payment_terms_label}</dd></div>
              <div><dt>Exchange rate</dt><dd>₹{Number(inv.exchange_rate)} / {inv.currency}</dd></div>
            </dl>
            <label className="field" style={{ marginTop: 10 }}><span>Due date</span>
              <span className="range"><input type="date" value={due} min={inv.invoice_date} onChange={(e) => setDue(e.target.value)} disabled={inv.status === 'cancelled'} />
                {due !== inv.due_date && <button className="small-btn" onClick={saveDue}>Save</button>}</span></label>
          </div>
        </aside>
      </div>
      {dialog === 'pay' && <PaymentDialog inv={inv} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); load() }} />}
      {dialog === 'cancel' && <ReasonDialog title={`Cancel ${inv.invoice_no}?`} label="Reason" required button="Cancel invoice" tone="danger" onClose={() => setDialog(null)} onConfirm={cancel} />}
    </>
  )
}

function PaymentDialog({ inv, onClose, onSaved }) {
  const [f, setF] = useState(() => ({ received_on: todayStr(), amount: inv.balance, bank_charges: '0', exchange_rate: inv.exchange_rate, method: inv.payment_terms.startsWith('lc') ? 'lc' : inv.payment_terms === 'advance' ? 'advance' : ['da', 'dp'].includes(inv.payment_terms) ? 'da_dp' : 'tt', bank_reference: '', note: '' }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (n, v) => setF((x) => ({ ...x, [n]: v }))
  const amount = Number(f.amount) || 0, charges = Number(f.bank_charges) || 0, rate = Number(f.exchange_rate) || 0
  const gain = (amount + charges) * (rate - Number(inv.exchange_rate))
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try { await api.post('/export-receipts/', { invoice: inv.id, ...f, bank_charges: f.bank_charges || 0 }); onSaved() } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }
  return (
    <Modal title={`Payment for ${inv.invoice_no}`} onClose={onClose} wide>
      <form onSubmit={submit}>
        <p className="muted small">Balance {money(inv.balance, inv.currency)}. Enter what the bank credited and what it deducted as charges; together they settle the invoice.</p>
        <div className="form-grid">
          <label className="field"><span>Received on</span><input type="date" value={f.received_on} max={todayStr()} onChange={(e) => set('received_on', e.target.value)} required /></label>
          <label className="field"><span>Amount credited ({inv.currency})</span><input type="number" min="0.01" step="0.01" value={f.amount} onChange={(e) => set('amount', e.target.value)} required /></label>
          <label className="field"><span>Bank charges ({inv.currency})</span><input type="number" min="0" step="0.01" value={f.bank_charges} onChange={(e) => set('bank_charges', e.target.value)} /></label>
          <label className="field"><span>Realised rate (₹ per {inv.currency})</span><input type="number" min="0.0001" step="0.0001" value={f.exchange_rate} onChange={(e) => set('exchange_rate', e.target.value)} required /></label>
          <label className="field"><span>Method</span><select value={f.method} onChange={(e) => set('method', e.target.value)}>{METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label className="field"><span>FIRC / BRC / bank ref.</span><input value={f.bank_reference} onChange={(e) => set('bank_reference', e.target.value)} /></label>
          <label className="field full"><span>Note</span><input value={f.note} onChange={(e) => set('note', e.target.value)} /></label>
        </div>
        <div className="pay-preview">
          <div><span>Credited in INR</span><b>{inr(amount * rate)}</b></div>
          <div><span>Settles</span><b>{money(amount + charges, inv.currency)}</b></div>
          <div><span>Exchange {gain < 0 ? 'loss' : 'gain'}</span><b className={gain < 0 ? 'neg' : 'pos'}>{inr(gain)}</b></div>
          <div><span>Balance after</span><b>{money(Math.max(Number(inv.balance) - amount - charges, 0), inv.currency)}</b></div>
        </div>
        {amount + charges > Number(inv.balance) + 0.001 && <p className="neg small">More than the balance.</p>}
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div><button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="approve" disabled={busy || amount + charges > Number(inv.balance) + 0.001}>Save payment</button></div></div>
      </form>
    </Modal>
  )
}
