import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import ProcBadge from '../components/proc/ProcBadge'
import { PO_STATUSES } from '../components/proc/constants'
import { money } from '../components/merch/constants'
import { fmtDate } from '../components/buyers/constants'

export default function PurchaseOrders() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Supplier POs"
      subtitle="Purchase orders to suppliers — approved by a manager, then sent"
      endpoint="/purchase-orders/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={
        <>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {PO_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button onClick={() => navigate('/purchase-orders/new')}>+ New</button>
        </>
      }
      onRowClick={(row) => navigate(`/purchase-orders/${row.id}`)}
      columns={[
        { key: 'po_no', label: 'PO' },
        { key: 'supplier_name', label: 'Supplier', render: (r) => <><b>{r.supplier_name}</b><div className="muted small">{[r.mr_no, r.rfq_no].filter(Boolean).join(' · ')}</div></> },
        { key: 'order_date', label: 'Date', render: (r) => fmtDate(r.order_date) },
        { key: 'delivery_date', label: 'Delivery', render: (r) => fmtDate(r.delivery_date) },
        { key: 'total', label: 'Value', num: true, render: (r) => <b>{money(r.total, r.currency, 0)}</b> },
        { key: 'status', label: 'Status', render: (r) => <ProcBadge kind="po" status={r.status} /> },
      ]}
      fields={[]}
    />
  )
}
