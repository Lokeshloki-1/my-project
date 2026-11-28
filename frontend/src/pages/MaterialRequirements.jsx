import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import Modal from '../components/Modal'
import ResourcePage from '../components/ResourcePage'
import useOptions from '../components/useOptions'
import ProcBadge from '../components/proc/ProcBadge'
import { MR_STATUSES } from '../components/proc/constants'
import { money } from '../components/merch/constants'
import { fmtDate } from '../components/buyers/constants'

export default function MaterialRequirements() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  const [generating, setGenerating] = useState(false)
  return (
    <>
      <ResourcePage
        title="Material Requirements"
        subtitle="What to buy for each confirmed order: order pieces × tech pack consumption + wastage"
        endpoint="/material-requirements/"
        readOnly
        params={{ status: status || undefined }}
        headerExtra={
          <>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
              <option value="">All statuses</option>
              {MR_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <button onClick={() => setGenerating(true)}>+ From order</button>
          </>
        }
        onRowClick={(row) => navigate(`/requirements/${row.id}`)}
        columns={[
          { key: 'mr_no', label: 'Requirement' },
          { key: 'title', label: 'For', render: (r) => <><b>{r.oc_no || 'Manual'}</b><div className="muted small">{r.buyer_name}</div></> },
          { key: 'needed_by', label: 'Needed by', render: (r) => fmtDate(r.needed_by) },
          { key: 'progress', label: 'Ordered', render: (r) => <Progress done={r.progress.fully_ordered} total={r.progress.lines} /> },
          { key: 'warnings', label: '', render: (r) => r.warnings.length > 0 && <span className="badge badge-po-draft" title={r.warnings.join('\n')}>⚠ {r.warnings.length}</span> },
          { key: 'status', label: 'Status', render: (r) => <ProcBadge kind="mr" status={r.status} /> },
        ]}
        fields={[]}
      />
      {generating && <GenerateDialog onClose={() => setGenerating(false)} onDone={(mr) => navigate(`/requirements/${mr.id}`)} />}
    </>
  )
}

export function Progress({ done, total }) {
  const pct = total ? Math.round((done / total) * 100) : 0
  return (
    <div className="progress" title={`${done} of ${total} materials fully ordered`}>
      <div className={pct >= 100 ? 'done' : ''} style={{ width: `${pct}%` }} />
      <span>{done}/{total}</span>
    </div>
  )
}

export function GenerateDialog({ onClose, onDone, orderId }) {
  const orders = useOptions('/order-confirmations/', { status: 'confirmed' })
  const [order, setOrder] = useState(orderId ? String(orderId) : '')
  const [wastage, setWastage] = useState('5')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const { data } = await api.post('/material-requirements/generate/', { order, wastage_pct: wastage })
      onDone(data)
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }
  return (
    <Modal title="Material requirement from an order" onClose={onClose}>
      <form onSubmit={submit}>
        <p className="muted small">Uses the latest released tech pack of each style: order pieces × BOM consumption, plus wastage. Same materials across styles are added together.</p>
        <label className="field"><span>Confirmed order *</span>
          <select value={order} onChange={(e) => setOrder(e.target.value)} required>
            <option value="">— choose —</option>
            {orders.map((o) => <option key={o.id} value={o.id}>{o.oc_no} · {o.buyer_name} · PO {o.buyer_po_no} · {money(o.total_amount, o.currency, 0)}</option>)}
          </select>
        </label>
        <label className="field"><span>Wastage %</span>
          <input type="number" min="0" max="100" step="0.5" value={wastage} onChange={(e) => setWastage(e.target.value)} />
        </label>
        {orders.length === 0 && <p className="muted small">No confirmed orders yet. <Link to="/orders">Confirm an order</Link> first.</p>}
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy || !order}>{busy ? 'Calculating…' : 'Calculate'}</button>
        </div></div>
      </form>
    </Modal>
  )
}
