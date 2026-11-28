import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Modal from '../components/Modal'
import useOptions from '../components/useOptions'
import { money, num } from '../components/merch/constants'
import { qty } from '../components/proc/constants'
import { MOVEMENT_TYPES } from '../components/stores/constants'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { fmtDateTime, labelOf } from '../components/buyers/constants'

export default function MaterialStock() {
  const { canManage } = useAuth()
  const [tab, setTab] = useState('stock')
  const [rows, setRows] = useState(null)
  const [moves, setMoves] = useState(null)
  const [summary, setSummary] = useState(null)
  const [warehouse, setWarehouse] = useState('')
  const [category, setCategory] = useState('')
  const [type, setType] = useState('')
  const [search, setSearch] = useState('')
  const [adjusting, setAdjusting] = useState(null)
  const [error, setError] = useState('')
  const warehouses = useOptions('/warehouses/')

  const load = useCallback(() => {
    const params = { page_size: 500, warehouse: warehouse || undefined, search: search || undefined }
    Promise.all([
      api.get('/material-stock/', { params: { ...params, material__category: category || undefined } }),
      api.get('/material-movements/', { params: { ...params, movement_type: type || undefined, page_size: 100 } }),
      api.get('/material-stock/summary/'),
    ]).then(([s, m, sum]) => { setRows(s.data.results); setMoves(m.data.results); setSummary(sum.data) })
      .catch((e) => setError(errorMessage(e)))
  }, [warehouse, category, type, search])
  useEffect(() => { load() }, [load])

  if (error) return <div className="error">{error}</div>
  if (!rows) return <div className="muted">Loading…</div>
  const totals = rows.reduce((a, r) => ({ value: a.value + Number(r.value) }), { value: 0 })

  return (
    <>
      <div className="page-head">
        <div><h1>Material Stock</h1><p className="muted">Fabric, trims, labels and packing in the stores. Allocated stock is reserved for orders.</p></div>
        <div className="actions">
          <Link className="button secondary" to="/receipts">Goods receipts</Link>
          <Link className="button" to="/allocation">Stock allocation</Link>
        </div>
      </div>
      <div className="kpis">
        <div className="card kpi"><div className="muted small">Material stock value</div><div className="kpi-value">{money(summary.stock_value, 'INR', 0)}</div></div>
        <div className="card kpi"><div className="muted small">Receipts awaiting inspection</div><div className="kpi-value">{summary.awaiting_inspection}</div>
          {summary.awaiting_inspection > 0 && <Link className="small" to="/receipts?status=received">Inspect →</Link>}</div>
        <div className="card kpi"><div className="muted small">Active allocations</div><div className="kpi-value">{summary.allocations_active}</div></div>
        <div className="card kpi"><div className="muted small">Below reorder level</div><div className={`kpi-value ${summary.low_stock ? 'neg' : ''}`}>{summary.low_stock}</div></div>
      </div>

      <div className="tabs" role="tablist">
        {[['stock', 'Stock'], ['movements', 'Movements']].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'tab active' : 'tab'} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <div className="card tab-panel">
        <div className="filters">
          <select value={warehouse} onChange={(e) => setWarehouse(e.target.value)} aria-label="Warehouse">
            <option value="">All stores</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          {tab === 'stock'
            ? <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Type"><option value="">All types</option>{BOM_CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            : <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Movement"><option value="">All movements</option>{MOVEMENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}
          <input className="search" placeholder="Search material…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {tab === 'stock' ? (
          <div className="table-wrap">
            <table className="cost-lines">
              <thead><tr><th>Code</th><th>Material</th><th>Store</th><th className="num">On hand</th><th className="num">Allocated</th><th className="num">Free</th><th className="num">Avg cost</th><th className="num">Value</th>{canManage && <th />}</tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={9} className="muted center">No material in stock yet. It arrives through goods receipts.</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="muted">{r.code}</td>
                    <td><b>{r.description}</b><div className="muted small">{labelOf(BOM_CATEGORIES, r.category)}{r.colour && ` · ${r.colour}`}</div></td>
                    <td>{r.warehouse_name}</td>
                    <td className="num">{qty(r.on_hand, r.unit)}</td>
                    <td className="num">{Number(r.allocated) ? qty(r.allocated) : '—'}</td>
                    <td className={`num ${Number(r.available) ? 'pos' : 'muted'}`}><b>{qty(r.available)}</b></td>
                    <td className="num">{num(r.average_cost)}</td>
                    <td className="num">{num(r.value, 0)}</td>
                    {canManage && <td><button className="link small" onClick={() => setAdjusting(r)}>Adjust</button></td>}
                  </tr>
                ))}
              </tbody>
              {rows.length > 0 && <tfoot><tr><td colSpan={7}><b>Total</b></td><td className="num"><b>{num(totals.value, 0)}</b></td>{canManage && <td />}</tr></tfoot>}
            </table>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="cost-lines">
              <thead><tr><th>When</th><th>Material</th><th>Store</th><th>Movement</th><th className="num">Qty</th><th className="num">Balance</th><th>Reference</th><th>By</th></tr></thead>
              <tbody>
                {moves.length === 0 && <tr><td colSpan={8} className="muted center">No movements.</td></tr>}
                {moves.map((m) => (
                  <tr key={m.id}>
                    <td className="small">{fmtDateTime(m.created_at)}</td>
                    <td>{m.material_name}</td><td>{m.warehouse_name}</td>
                    <td><span className={`badge badge-mv-${m.movement_type}`}>{m.type_label}</span></td>
                    <td className={`num ${Number(m.quantity) > 0 ? 'pos' : 'neg'}`}>{Number(m.quantity) > 0 ? '+' : ''}{num(m.quantity)}</td>
                    <td className="num">{num(m.balance_after)}</td>
                    <td className="small">{m.reference}<div className="muted">{m.note}</div></td>
                    <td className="small">{m.user_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {adjusting && <AdjustDialog row={adjusting} onClose={() => setAdjusting(null)} onDone={() => { setAdjusting(null); load() }} />}
    </>
  )
}

function AdjustDialog({ row, onClose, onDone }) {
  const [counted, setCounted] = useState(row.on_hand)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const diff = Number(counted) - Number(row.on_hand)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try { await api.post('/material-stock/adjust/', { material: row.material, warehouse: row.warehouse, new_quantity: counted, reason }); onDone() } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }
  return (
    <Modal title={`Stock count · ${row.description}`} onClose={onClose}>
      <form onSubmit={submit}>
        <p className="muted small">{row.warehouse_name}: system shows {qty(row.on_hand, row.unit)} ({qty(row.allocated)} allocated). Enter what was counted.</p>
        <label className="field"><span>Counted quantity ({row.unit}) *</span><input type="number" min="0" step="0.01" value={counted} onChange={(e) => setCounted(e.target.value)} required /></label>
        {diff !== 0 && <p className={`small ${diff > 0 ? 'pos' : 'neg'}`}>{diff > 0 ? '+' : ''}{diff.toLocaleString('en-IN')} {row.unit} will be recorded.</p>}
        <label className="field"><span>Reason *</span><input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Monthly stock count" required /></label>
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy || diff === 0 || !reason.trim()}>Record adjustment</button>
        </div></div>
      </form>
    </Modal>
  )
}
