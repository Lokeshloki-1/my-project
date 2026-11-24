import { useCallback, useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Modal from '../components/Modal'
import useOptions from '../components/useOptions'
import { money } from '../utils/format'

const qty = (v) => Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })

const ACTIONS = {
  receipt: { title: 'Receive stock', help: 'Goods coming in, e.g. from a supplier.', button: 'Receive' },
  issue: { title: 'Issue stock', help: 'Goods going out that are not a sales order, e.g. internal use or samples.', button: 'Issue' },
  adjustment: { title: 'Adjust stock', help: 'Correct the count after a stock check. Use a minus number to reduce, e.g. -3.', button: 'Adjust' },
  transfer: { title: 'Transfer stock', help: 'Move goods from one warehouse to another.', button: 'Transfer' },
}

export default function Stock() {
  const { canManage } = useAuth()
  const warehouses = useOptions('/warehouses/')
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [warehouse, setWarehouse] = useState('')
  const [lowOnly, setLowOnly] = useState(false)
  const [search, setSearch] = useState('')
  const [action, setAction] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get('/stock-levels/', { params: { page, warehouse: warehouse || undefined, low_stock: lowOnly || undefined, search: search || undefined } })
      .then((res) => { setRows(res.data.results); setCount(res.data.count) })
      .catch((e) => setError(errorMessage(e)))
  }, [page, warehouse, lowOnly, search])
  useEffect(() => { load() }, [load])

  const pages = Math.max(1, Math.ceil(count / 25))
  const totalValue = rows.reduce((s, r) => s + Number(r.stock_value), 0)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Stock</h1>
          <p className="muted">Stock on hand in each warehouse. Confirmed sales orders take stock automatically.</p>
        </div>
        {canManage && (
          <div className="actions">
            {Object.entries(ACTIONS).map(([key, a]) => (
              <button key={key} className={key === 'receipt' ? '' : 'secondary'} onClick={() => setAction(key)}>{a.button}</button>
            ))}
          </div>
        )}
      </div>
      <div className="filters">
        <input className="search" placeholder="Search SKU / product…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
        <select value={warehouse} onChange={(e) => { setWarehouse(e.target.value); setPage(1) }}>
          <option value="">All warehouses</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name} ({w.company_name})</option>)}
        </select>
        <label className="check-inline"><input type="checkbox" checked={lowOnly} onChange={(e) => { setLowOnly(e.target.checked); setPage(1) }} /> Low stock only</label>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr><th>SKU</th><th>Product</th><th>Warehouse</th><th className="num">On hand</th><th className="num">Total, all warehouses</th><th className="num">Reorder at</th><th className="num">Cost</th><th className="num">Value</th><th /></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={9} className="muted center">{lowOnly ? 'Nothing is low on stock.' : 'No stock yet. Use Receive to add some.'}</td></tr>}
            {rows.map((r) => {
              return (
                <tr key={r.id}>
                  <td>{r.sku}</td><td>{r.product_name}</td><td>{r.warehouse_name}</td>
                  <td className="num"><strong>{qty(r.quantity)}</strong></td>
                  <td className="num">{qty(r.product_total)}</td>
                  <td className="num">{Number(r.reorder_level) ? qty(r.reorder_level) : '—'}</td>
                  <td className="num">{money(r.cost_price)}</td><td className="num">{money(r.stock_value)}</td>
                  <td>{r.is_low_stock && <span className="badge badge-low" title="Total stock is at or below the reorder level">Low</span>}</td>
                </tr>
              )
            })}
          </tbody>
          {rows.length > 0 && (
            <tfoot><tr><td colSpan={7} className="muted">Value of the stock shown on this page</td><td className="num"><strong>{money(totalValue)}</strong></td><td /></tr></tfoot>
          )}
        </table>
      </div>
      {pages > 1 && (
        <div className="pager">
          <button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span className="muted">Page {page} of {pages}</span>
          <button className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
      {action && <StockActionForm kind={action} warehouses={warehouses} onClose={() => setAction(null)} onDone={() => { setAction(null); load() }} />}
    </>
  )
}

function StockActionForm({ kind, warehouses, onClose, onDone }) {
  const a = ACTIONS[kind]
  const [form, setForm] = useState({ warehouse: '', to_warehouse: '', product: '', quantity: '', unit_cost: '', reference: '', note: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const fromWh = warehouses.find((w) => String(w.id) === String(form.warehouse))
  const products = useOptions('/products/', fromWh ? { company: fromWh.company, is_active: true } : null)
  const level = useOptions('/stock-levels/', form.product && form.warehouse ? { product: form.product, warehouse: form.warehouse } : null)
  const available = level[0]?.quantity ?? (form.product && form.warehouse ? '0' : null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (kind === 'transfer') {
        await api.post('/stock-movements/transfer/', { product: form.product, from_warehouse: form.warehouse, to_warehouse: form.to_warehouse, quantity: form.quantity, reference: form.reference, note: form.note })
      } else {
        await api.post('/stock-movements/', { movement_type: kind, product: form.product, warehouse: form.warehouse, quantity: form.quantity, unit_cost: form.unit_cost || null, reference: form.reference, note: form.note })
      }
      onDone()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <Modal title={a.title} onClose={onClose}>
      <p className="muted small" style={{ marginTop: -6 }}>{a.help}</p>
      <form onSubmit={submit}>
        <label className="field"><span>{kind === 'transfer' ? 'From warehouse *' : 'Warehouse *'}</span>
          <select required value={form.warehouse} onChange={(e) => setForm((f) => ({ ...f, warehouse: e.target.value, product: '', to_warehouse: '' }))}>
            <option value="">— select —</option>
            {warehouses.filter((w) => w.is_active).map((w) => <option key={w.id} value={w.id}>{w.name} ({w.company_name})</option>)}
          </select></label>
        {kind === 'transfer' && (
          <label className="field"><span>To warehouse *</span>
            <select required value={form.to_warehouse} onChange={(e) => set('to_warehouse', e.target.value)}>
              <option value="">— select —</option>
              {warehouses.filter((w) => w.is_active && fromWh && w.company === fromWh.company && w.id !== fromWh.id).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select></label>
        )}
        <label className="field"><span>Product *</span>
          <select required value={form.product} onChange={(e) => set('product', e.target.value)} disabled={!fromWh}>
            <option value="">{fromWh ? '— select —' : 'Choose a warehouse first'}</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.sku} · {p.name}</option>)}
          </select>
          {available !== null && <small className="muted">In stock here: {qty(available)}</small>}
        </label>
        <label className="field"><span>Quantity *</span>
          <input type="number" step="0.01" min={kind === 'adjustment' ? undefined : '0.01'} required value={form.quantity} onChange={(e) => set('quantity', e.target.value)} /></label>
        {kind === 'receipt' && (
          <label className="field"><span>Unit cost (optional)</span>
            <input type="number" step="0.01" min="0" value={form.unit_cost} onChange={(e) => set('unit_cost', e.target.value)} /></label>
        )}
        <label className="field"><span>Reference {kind === 'receipt' ? '(GRN / supplier bill no.)' : ''}</span>
          <input value={form.reference} onChange={(e) => set('reference', e.target.value)} /></label>
        <label className="field"><span>{kind === 'adjustment' ? 'Reason *' : 'Note'}</span>
          <textarea rows={2} required={kind === 'adjustment'} value={form.note} onChange={(e) => set('note', e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <div className="modal-foot">
          <span />
          <div>
            <button type="button" className="secondary" onClick={onClose}>Cancel</button>
            <button type="submit" disabled={busy}>{busy ? 'Saving…' : a.button}</button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
