import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api, { downloadFile, errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Modal from '../components/Modal'
import StatusBadge from '../components/StatusBadge'
import { money } from '../utils/format'

const STATUSES = ['unpaid', 'partially_paid', 'paid', 'cancelled']
const METHODS = [
  ['bank_transfer', 'Bank transfer (NEFT/RTGS)'], ['upi', 'UPI'], ['cheque', 'Cheque'], ['cash', 'Cash'], ['card', 'Card'],
]
const today = () => new Date().toISOString().slice(0, 10)

export default function Invoices() {
  const [params, setParams] = useSearchParams()
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const openId = params.get('open')

  const load = useCallback(() => {
    api.get('/invoices/', { params: { page, status: status || undefined, search: search || undefined } })
      .then((res) => { setRows(res.data.results); setCount(res.data.count) })
      .catch((e) => setError(errorMessage(e)))
  }, [page, status, search])
  useEffect(() => { load() }, [load])

  const pages = Math.max(1, Math.ceil(count / 25))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Invoices</h1>
          <p className="muted">Create invoices from confirmed orders on the Sales Orders page.</p>
        </div>
        <div className="actions">
          <input className="search" placeholder="Search invoice / customer…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Invoice #</th><th>Date</th><th>Due</th><th>Customer</th><th>Status</th>
              <th className="num">Total</th><th className="num">Paid</th><th className="num">Balance</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="muted center">No invoices.</td></tr>}
            {rows.map((inv) => (
              <tr key={inv.id} className="clickable" onClick={() => setParams({ open: inv.id })}>
                <td>{inv.invoice_no}</td><td>{inv.invoice_date}</td>
                <td className={inv.is_overdue ? 'neg' : ''}>{inv.due_date}{inv.is_overdue && ' · overdue'}</td>
                <td>{inv.customer_name}</td><td><StatusBadge value={inv.status} /></td>
                <td className="num">{money(inv.total)}</td><td className="num">{money(inv.amount_paid)}</td>
                <td className="num"><strong>{money(inv.balance)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="pager">
          <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span className="muted">Page {page} of {pages} · {count} invoices</span>
          <button className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
      {openId && <InvoiceDetail id={openId} onClose={() => setParams({})} onChanged={load} />}
    </>
  )
}

function InvoiceDetail({ id, onClose, onChanged }) {
  const { canFinance, canManage } = useAuth()
  const [inv, setInv] = useState(null)
  const [error, setError] = useState('')
  const [pay, setPay] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.get(`/invoices/${id}/`).then((res) => setInv(res.data)).catch((e) => setError(errorMessage(e)))
  }, [id])
  useEffect(() => { load() }, [load])

  const run = async (fn) => {
    setBusy(true)
    setError('')
    try { await fn(); load(); onChanged() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  const recordPayment = (e) => {
    e.preventDefault()
    run(async () => { await api.post('/payments/', { ...pay, invoice: inv.id }); setPay(null) })
  }
  const deletePayment = (p) => {
    if (window.confirm(`Delete payment of ${money(p.amount)}? The balance will go back up.`)) run(() => api.delete(`/payments/${p.id}/`))
  }
  const cancelInvoice = () => {
    if (window.confirm('Cancel this invoice? Its sales order will be cancelled too. This cannot be undone.')) run(() => api.post(`/invoices/${inv.id}/cancel/`))
  }

  if (!inv) return <Modal title="Invoice" onClose={onClose}>{error ? <div className="error">{error}</div> : <p className="muted">Loading…</p>}</Modal>
  const open = inv.status === 'unpaid' || inv.status === 'partially_paid'

  return (
    <Modal title={`Invoice ${inv.invoice_no}`} onClose={onClose} wide>
      <div className="inv-summary">
        <div><span>Customer</span><strong>{inv.customer_name}</strong><small className="muted">{inv.company_name}</small></div>
        <div><span>Order</span><strong>{inv.order_no}</strong></div>
        <div><span>Invoice date</span><strong>{inv.invoice_date}</strong></div>
        <div><span>Due date</span><strong className={inv.is_overdue ? 'neg' : ''}>{inv.due_date}</strong>{inv.is_overdue && <small className="neg">Overdue</small>}</div>
        <div><span>Status</span><StatusBadge value={inv.status} /></div>
      </div>

      <table className="lines">
        <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">GST %</th><th className="num">Amount</th></tr></thead>
        <tbody>
          {inv.items.map((it) => (
            <tr key={it.id}>
              <td>{it.product_name}</td><td className="num">{Number(it.quantity)}</td>
              <td className="num">{money(it.unit_price)}</td><td className="num">{Number(it.tax_rate)}</td>
              <td className="num">{money(it.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="totals">
        <div><span>Subtotal</span><span>{money(inv.subtotal)}</span></div>
        <div><span>GST</span><span>{money(inv.tax_amount)}</span></div>
        <div className="strong"><span>Total</span><span>{money(inv.total)}</span></div>
        <div><span>Paid</span><span>{money(inv.amount_paid)}</span></div>
        <div className="strong"><span>Balance due</span><span>{money(inv.balance)}</span></div>
      </div>

      <h3>Payments</h3>
      {inv.payments.length === 0 && <p className="muted small">No payments yet.</p>}
      {inv.payments.length > 0 && (
        <table className="lines">
          <thead><tr><th>Date</th><th>Method</th><th>Reference</th><th className="num">Amount</th>{canManage && <th />}</tr></thead>
          <tbody>
            {inv.payments.map((p) => (
              <tr key={p.id}>
                <td>{p.payment_date}</td><td>{METHODS.find((m) => m[0] === p.method)?.[1] ?? p.method}</td>
                <td>{p.reference || '—'}</td><td className="num">{money(p.amount)}</td>
                {canManage && <td className="num">{inv.status !== 'cancelled' && <button type="button" className="link" title="Delete payment" onClick={() => deletePayment(p)}>✕</button>}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {pay && (
        <form className="pay-form" onSubmit={recordPayment}>
          <div className="form-grid">
            <label className="field"><span>Amount *</span>
              <input type="number" step="0.01" min="0.01" max={inv.balance} required value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} /></label>
            <label className="field"><span>Payment date *</span>
              <input type="date" required min={inv.invoice_date} value={pay.payment_date} onChange={(e) => setPay({ ...pay, payment_date: e.target.value })} /></label>
            <label className="field"><span>Method</span>
              <select value={pay.method} onChange={(e) => setPay({ ...pay, method: e.target.value })}>
                {METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></label>
            <label className="field"><span>Reference (UTR / cheque no.)</span>
              <input value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} /></label>
          </div>
          <div className="modal-foot">
            <span />
            <div>
              <button type="button" className="secondary" onClick={() => setPay(null)}>Cancel</button>
              <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save payment'}</button>
            </div>
          </div>
        </form>
      )}

      {error && <div className="error">{error}</div>}
      {!pay && (
        <div className="modal-foot">
          <div>
            {canFinance && inv.status === 'unpaid' && <button type="button" className="danger" disabled={busy} onClick={cancelInvoice}>Cancel invoice</button>}
          </div>
          <div>
            <button type="button" className="secondary" onClick={() => run(() => downloadFile(`/invoices/${inv.id}/pdf/`, `${inv.invoice_no}.pdf`))}>Download PDF</button>
            {canFinance && open && (
              <button type="button" onClick={() => setPay({ amount: inv.balance, payment_date: today(), method: 'bank_transfer', reference: '' })}>Record payment</button>
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}
