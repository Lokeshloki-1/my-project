import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import StoresBadge from '../components/stores/StoresBadge'
import { GRN_STATUSES } from '../components/stores/constants'
import { fmtDate } from '../components/buyers/constants'

export default function GoodsReceipts() {
  const navigate = useNavigate()
  const [query] = useSearchParams()
  const [status, setStatus] = useState(query.get('status') || '')
  return (
    <ResourcePage
      title="Goods Receipts"
      subtitle="Materials arriving against supplier POs — inspected before they go into stock"
      endpoint="/goods-receipts/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={
        <>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {GRN_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button onClick={() => navigate('/receipts/new')}>+ Receive goods</button>
        </>
      }
      onRowClick={(row) => navigate(`/receipts/${row.id}`)}
      columns={[
        { key: 'grn_no', label: 'GRN' },
        { key: 'supplier_name', label: 'Supplier', render: (r) => <><b>{r.supplier_name}</b><div className="muted small">{r.po_no}</div></> },
        { key: 'received_on', label: 'Received', render: (r) => fmtDate(r.received_on) },
        { key: 'challan_no', label: 'Challan' },
        { key: 'warehouse_name', label: 'Store' },
        { key: 'totals', label: 'Inspection', render: (r) => r.status !== 'inspected' ? <span className="muted">—</span>
          : Number(r.totals.rejected) ? <span className="neg small">Some rejected</span> : <span className="pos small">All accepted</span> },
        { key: 'status', label: 'Status', render: (r) => <StoresBadge kind="grn" status={r.status} /> },
      ]}
      fields={[]}
    />
  )
}
