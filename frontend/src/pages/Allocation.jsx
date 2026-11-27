import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import Modal from '../components/Modal'
import useOptions from '../components/useOptions'
import StoresBadge from '../components/stores/StoresBadge'
import { qty } from '../components/proc/constants'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { fmtDate, labelOf } from '../components/buyers/constants'
import { Progress } from './MaterialRequirements'

// /allocation — pick an order's material requirement; /allocation/:id — allocate stock to it.
export default function Allocation() {
  const { id } = useParams()
  return id ? <AllocationPlan id={id} /> : <AllocationIndex />
}

function AllocationIndex() {
  const navigate = useNavigate()
  const requirements = useOptions('/material-requirements/', { status: 'approved' })
  const allocations = useOptions('/material-allocations/', { status: 'active' })
  return (
    <>
      <div className="page-head"><div><h1>Stock Allocation</h1><p className="muted">Reserve material in the stores for confirmed orders, then issue it to production.</p></div></div>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Requirement</th><th>Order</th><th>Needed by</th><th>Purchased</th><th className="num">Active allocations</th></tr></thead>
          <tbody>
            {requirements.filter((r) => r.order).length === 0 && <tr><td colSpan={5} className="muted center">No approved material requirements for orders.</td></tr>}
            {requirements.filter((r) => r.order).map((r) => (
              <tr key={r.id} className="clickable" onClick={() => navigate(`/allocation/${r.id}`)}>
                <td><Link to={`/allocation/${r.id}`}>{r.mr_no}</Link></td>
                <td><b>{r.oc_no}</b><div className="muted small">{r.buyer_name}</div></td>
                <td>{fmtDate(r.needed_by)}</td>
                <td><Progress done={r.progress.fully_ordered} total={r.progress.lines} /></td>
                <td className="num">{allocations.filter((a) => a.order === r.order).length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function AllocationPlan({ id }) {
  const [plan, setPlan] = useState(null)
  const [allocs, setAllocs] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)

  const load = useCallback(() => api.get('/material-allocations/plan/', { params: { requirement: id } }).then(async (r) => {
    setPlan(r.data)
    if (r.data.order) setAllocs((await api.get('/material-allocations/', { params: { order: r.data.order, page_size: 500 } })).data.results)
  }).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])

  if (!plan) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const run = async (fn) => {
    setBusy(true); setError('')
    try { await fn(); setDialog(null); await load() } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const anyFree = plan.lines.some((l) => Number(l.still_needed) > 0 && l.stock.some((s) => Number(s.available) > 0))
  const covered = plan.lines.filter((l) => Number(l.still_needed) === 0).length

  return (
    <>
      <div className="crumbs small"><Link to="/allocation">Stock allocation</Link> / {plan.mr_no}</div>
      <div className="page-head">
        <div><h1>Allocate stock · {plan.oc_no}</h1><p className="muted"><Link to={`/requirements/${plan.requirement}`}>{plan.mr_no}</Link> · <Link to={`/orders/${plan.order}`}>{plan.oc_no}</Link> · {covered} of {plan.lines.length} materials covered</p></div>
        <div className="actions">
          <button onClick={() => run(() => api.post('/material-allocations/auto/', { requirement: plan.requirement }))} disabled={busy || !anyFree}>Allocate all free stock</button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <h2>Materials for this order</h2>
        <div className="table-wrap">
          <table className="cost-lines">
            <thead><tr><th>Material</th><th className="num">Required</th><th className="num">Allocated</th><th className="num">Issued</th><th className="num">Still needed</th><th>Free in stores</th><th /></tr></thead>
            <tbody>
              {plan.lines.map((l) => {
                const free = l.stock.reduce((a, s) => a + Number(s.available), 0)
                const pct = Math.min(100, ((Number(l.allocated_qty) + Number(l.issued_qty)) / Number(l.required_qty || 1)) * 100)
                return (
                  <tr key={l.requirement_line}>
                    <td><b>{l.description}</b><div className="muted small">{labelOf(BOM_CATEGORIES, l.category)}{l.colour && ` · ${l.colour}`}{l.material_code && ` · ${l.material_code}`}</div>
                      <div className="mini-bar" title={`${Math.round(pct)}% covered`}><span style={{ width: `${pct}%` }} /></div></td>
                    <td className="num">{qty(l.required_qty, l.unit)}</td>
                    <td className="num">{Number(l.allocated_qty) ? qty(l.allocated_qty) : '—'}</td>
                    <td className="num">{Number(l.issued_qty) ? qty(l.issued_qty) : '—'}</td>
                    <td className={`num ${Number(l.still_needed) ? 'warn-text' : 'pos'}`}>{Number(l.still_needed) ? qty(l.still_needed) : '✓'}</td>
                    <td className="small">{!l.material ? <span className="muted">Never received</span> : l.stock.length === 0 ? <span className="muted">None in stock</span>
                      : l.stock.map((s) => <div key={s.warehouse}>{s.warehouse_name}: <b>{qty(s.available)}</b> free</div>)}</td>
                    <td>{Number(l.still_needed) > 0 && free > 0 && <button className="secondary small-btn" onClick={() => setDialog({ kind: 'allocate', line: l })}>Allocate</button>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Allocations</h2>
        <div className="table-wrap">
          <table className="cost-lines">
            <thead><tr><th>Material</th><th>Store</th><th className="num">Allocated</th><th className="num">Issued</th><th className="num">Released</th><th className="num">Remaining</th><th>Status</th><th /></tr></thead>
            <tbody>
              {allocs.length === 0 && <tr><td colSpan={8} className="muted center">Nothing allocated yet.</td></tr>}
              {allocs.map((a) => (
                <tr key={a.id}>
                  <td>{a.material_name}<div className="muted small">{fmtDate(a.created_at)} · {a.created_by_name}{a.note && ` · ${a.note}`}</div></td>
                  <td>{a.warehouse_name}</td>
                  <td className="num">{qty(a.quantity, a.unit)}</td>
                  <td className="num">{Number(a.issued_qty) ? qty(a.issued_qty) : '—'}</td>
                  <td className="num">{Number(a.released_qty) ? qty(a.released_qty) : '—'}</td>
                  <td className="num"><b>{qty(a.remaining)}</b></td>
                  <td><StoresBadge kind="alloc" status={a.status} /></td>
                  <td className="nowrap">{a.status === 'active' && <>
                    <button className="small-btn" onClick={() => setDialog({ kind: 'issue', alloc: a })}>Issue</button>{' '}
                    <button className="secondary small-btn" onClick={() => setDialog({ kind: 'release', alloc: a })}>Release</button></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {dialog?.kind === 'allocate' && <AllocateDialog line={dialog.line} order={plan.order} busy={busy} onClose={() => setDialog(null)}
        onSubmit={(body) => run(() => api.post('/material-allocations/', body))} />}
      {(dialog?.kind === 'issue' || dialog?.kind === 'release') && <QtyDialog dialog={dialog} busy={busy} onClose={() => setDialog(null)}
        onSubmit={(quantity) => run(() => api.post(`/material-allocations/${dialog.alloc.id}/${dialog.kind}/`, { quantity }))} />}
    </>
  )
}

function AllocateDialog({ line, order, busy, onClose, onSubmit }) {
  const options = line.stock.filter((s) => Number(s.available) > 0)
  const [warehouse, setWarehouse] = useState(options[0]?.warehouse)
  const free = Number(options.find((s) => s.warehouse === Number(warehouse))?.available || 0)
  const [quantity, setQuantity] = useState(String(Math.min(free, Number(line.still_needed))))
  return (
    <Modal title={`Allocate ${line.description}`} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit({ order, material: line.material, warehouse, quantity, requirement_line: line.requirement_line }) }}>
        <p className="muted small">Still needed: {qty(line.still_needed, line.unit)}.</p>
        <label className="field"><span>From store</span>
          <select value={warehouse} onChange={(e) => setWarehouse(Number(e.target.value))}>
            {options.map((s) => <option key={s.warehouse} value={s.warehouse}>{s.warehouse_name} — {qty(s.available)} free</option>)}
          </select></label>
        <label className="field"><span>Quantity ({line.unit})</span>
          <input type="number" min="0.01" max={free} step="0.01" value={quantity} onChange={(e) => setQuantity(e.target.value)} required /></label>
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy || !(Number(quantity) > 0) || Number(quantity) > free}>Allocate</button>
        </div></div>
      </form>
    </Modal>
  )
}

function QtyDialog({ dialog, busy, onClose, onSubmit }) {
  const a = dialog.alloc
  const [quantity, setQuantity] = useState(a.remaining)
  const issue = dialog.kind === 'issue'
  return (
    <Modal title={`${issue ? 'Issue to production' : 'Release back to free stock'} · ${a.material_name}`} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit(quantity) }}>
        <p className="muted small">{issue ? 'Issued material leaves the store and is booked to the order.' : 'Released material becomes free for other orders.'} Remaining on this allocation: {qty(a.remaining, a.unit)}.</p>
        <label className="field"><span>Quantity ({a.unit})</span><input type="number" min="0.01" max={a.remaining} step="0.01" value={quantity} onChange={(e) => setQuantity(e.target.value)} required /></label>
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className={issue ? '' : 'secondary'} disabled={busy}>{issue ? 'Issue' : 'Release'}</button>
        </div></div>
      </form>
    </Modal>
  )
}
