import { useCallback, useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client'
import Modal from '../components/Modal'
import StatusBadge from '../components/StatusBadge'
import useOptions from '../components/useOptions'
import { money } from '../utils/format'

const STATUSES = ['draft', 'confirmed', 'invoiced', 'paid', 'cancelled']
const today = () => new Date().toISOString().slice(0, 10)
const emptyOrder = () => ({ company: '', customer: '', salesperson: '', order_date: today(), status: 'draft', notes: '', items: [{ product: '', quantity: 1 }] })

export default function SalesOrders() {
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get('/sales-orders/', { params: { status: status || undefined, search: search || undefined } })
      .then((res) => setRows(res.data.results))
      .catch((e) => setError(errorMessage(e)))
  }, [status, search])
  useEffect(() => { load() }, [load])

  return (
    <>
      <div className="page-head">
        <h1>Sales Orders</h1>
        <div className="actions">
          <input className="search" placeholder="Search order / customer…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={() => { setError(''); setForm(emptyOrder()) }}>+ New order</button>
        </div>
      </div>
      {error && !form && <div className="error">{error}</div>}
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Order #</th><th>Date</th><th>Customer</th><th>Salesperson</th><th>Status</th><th className="num">Total</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="muted center">No orders.</td></tr>}
            {rows.map((o) => (
              <tr key={o.id} className="clickable" onClick={() => { setError(''); setForm({ ...o, salesperson: o.salesperson ?? '' }) }}>
                <td>{o.order_no}</td><td>{o.order_date}</td><td>{o.customer_name}</td>
                <td>{o.salesperson_name || '—'}</td><td><StatusBadge value={o.status} /></td>
                <td className="num">{money(o.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {form && <OrderForm form={form} setForm={setForm} onSaved={() => { setForm(null); load() }} error={error} setError={setError} />}
    </>
  )
}

function OrderForm({ form, setForm, onSaved, error, setError }) {
  const companies = useOptions('/companies/')
  const scope = form.company ? { company: form.company } : null
  const customers = useOptions('/customers/', scope)
  const employees = useOptions('/employees/', scope)
  const products = useOptions('/products/', scope && { ...scope, is_active: true })
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const setItem = (i, k, v) => setForm((f) => ({ ...f, items: f.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) }))

  // Live preview only — the server recalculates the real totals.
  const productById = Object.fromEntries(products.map((p) => [String(p.id), p]))
  const preview = form.items.reduce((sum, it) => {
    const p = productById[String(it.product)]
    if (!p) return sum
    const price = Number(it.unit_price ?? p.unit_price)
    const sub = price * Number(it.quantity || 0)
    return sum + sub + (sub * Number(it.tax_rate ?? p.tax_rate)) / 100
  }, 0)

  const save = async (e) => {
    e.preventDefault()
    setError('')
    const body = {
      ...form,
      salesperson: form.salesperson || null,
      items: form.items.map(({ product, quantity, unit_price, tax_rate }) => ({ product, quantity, ...(unit_price != null && { unit_price }), ...(tax_rate != null && { tax_rate }) })),
    }
    try {
      if (form.id) await api.put(`/sales-orders/${form.id}/`, body)
      else await api.post('/sales-orders/', body)
      onSaved()
    } catch (err) { setError(errorMessage(err)) }
  }

  const remove = async () => {
    if (!window.confirm('Delete this draft order?')) return
    try { await api.delete(`/sales-orders/${form.id}/`); onSaved() } catch (err) { setError(errorMessage(err)) }
  }

  return (
    <Modal title={form.id ? `Order ${form.order_no}` : 'New sales order'} onClose={() => setForm(null)} wide>
      <form onSubmit={save}>
        <div className="form-grid">
          <label className="field"><span>Company *</span>
            <select value={form.company} required onChange={(e) => setForm((f) => ({ ...f, company: e.target.value, customer: '', salesperson: '', items: [{ product: '', quantity: 1 }] }))}>
              <option value="">— select —</option>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Customer *</span>
            <select value={form.customer} required onChange={(e) => set('customer', e.target.value)}>
              <option value="">— select —</option>
              {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Salesperson</span>
            <select value={form.salesperson} onChange={(e) => set('salesperson', e.target.value)}>
              <option value="">— none —</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </select>
          </label>
          <label className="field"><span>Order date *</span>
            <input type="date" value={form.order_date} required onChange={(e) => set('order_date', e.target.value)} />
          </label>
          <label className="field"><span>Status</span>
            <select value={form.status} onChange={(e) => set('status', e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="field full"><span>Notes</span>
            <textarea rows={2} value={form.notes} onChange={(e) => set('notes', e.target.value)} />
          </label>
        </div>

        <h3>Items</h3>
        <table className="items">
          <thead><tr><th>Product</th><th className="num">Qty</th><th className="num">Unit price</th><th className="num">GST %</th><th /></tr></thead>
          <tbody>
            {form.items.map((it, i) => {
              const p = productById[String(it.product)]
              return (
                <tr key={i}>
                  <td>
                    <select value={it.product} required onChange={(e) => { setItem(i, 'product', e.target.value); setItem(i, 'unit_price', undefined); setItem(i, 'tax_rate', undefined) }}>
                      <option value="">— product —</option>
                      {products.map((pr) => <option key={pr.id} value={pr.id}>{pr.sku} · {pr.name}</option>)}
                    </select>
                  </td>
                  <td><input type="number" min="0.01" step="0.01" value={it.quantity} required onChange={(e) => setItem(i, 'quantity', e.target.value)} /></td>
                  <td><input type="number" min="0" step="0.01" value={it.unit_price ?? p?.unit_price ?? ''} onChange={(e) => setItem(i, 'unit_price', e.target.value)} /></td>
                  <td><input type="number" min="0" max="100" step="0.01" value={it.tax_rate ?? p?.tax_rate ?? ''} onChange={(e) => setItem(i, 'tax_rate', e.target.value)} /></td>
                  <td>{form.items.length > 1 && <button type="button" className="link" onClick={() => set('items', form.items.filter((_, j) => j !== i))}>✕</button>}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="items-foot">
          <button type="button" className="secondary" onClick={() => set('items', [...form.items, { product: '', quantity: 1 }])}>+ Add item</button>
          <div className="total">Estimated total: <strong>{money(preview)}</strong></div>
        </div>

        {error && <div className="error">{error}</div>}
        <div className="modal-foot">
          {form.id && form.status === 'draft' ? <button type="button" className="danger" onClick={remove}>Delete</button> : <span />}
          <div>
            <button type="button" className="secondary" onClick={() => setForm(null)}>Cancel</button>
            <button type="submit">Save order</button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
