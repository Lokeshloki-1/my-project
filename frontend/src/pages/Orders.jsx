import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import DocBadge from '../components/merch/DocBadge'
import { ORDER_STATUSES, money } from '../components/merch/constants'
import { fmtDate } from '../components/buyers/constants'

export default function Orders() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Order Confirmations"
      subtitle="Buyer POs confirmed from accepted quotations, checked against each buyer's credit limit"
      endpoint="/order-confirmations/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {ORDER_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      }
      onRowClick={(row) => navigate(`/orders/${row.id}`)}
      columns={[
        { key: 'oc_no', label: 'Order' },
        { key: 'buyer_name', label: 'Buyer' },
        { key: 'buyer_po_no', label: 'Buyer PO', render: (r) => r.buyer_po_no || <span className="muted">—</span> },
        { key: 'quote_no', label: 'Quotation' },
        { key: 'ship_date', label: 'Ship date', render: (r) => fmtDate(r.ship_date) },
        { key: 'total_quantity', label: 'Pcs', num: true, render: (r) => Number(r.total_quantity).toLocaleString('en-IN') },
        { key: 'total_amount', label: 'Value', num: true, render: (r) => <b>{money(r.total_amount, r.currency)}</b> },
        { key: 'status', label: 'Status', render: (r) => <><DocBadge kind="oc" status={r.status} />{r.credit_override && <span className="badge badge-qt-sent" title="Confirmed over the credit limit">override</span>}</> },
      ]}
      fields={[]}
    />
  )
}
