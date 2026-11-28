import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import ProcBadge from '../components/proc/ProcBadge'
import { RFQ_STATUSES } from '../components/proc/constants'
import { fmtDate } from '../components/buyers/constants'

export default function RFQs() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="RFQs"
      subtitle="Requests for quotation: ask several suppliers, compare prices, award the best"
      endpoint="/rfqs/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={
        <>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {RFQ_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button onClick={() => navigate('/rfqs/new')}>+ New</button>
        </>
      }
      onRowClick={(row) => navigate(`/rfqs/${row.id}`)}
      columns={[
        { key: 'rfq_no', label: 'RFQ' },
        { key: 'title', label: 'Title', render: (r) => <><b>{r.title}</b>{r.mr_no && <div className="muted small">{r.mr_no}</div>}</> },
        { key: 'supplier_names', label: 'Suppliers', render: (r) => r.supplier_names.join(', ') || '—' },
        { key: 'quote_count', label: 'Quotes', num: true, render: (r) => `${r.quote_count}/${r.supplier_names.length}` },
        { key: 'reply_by', label: 'Reply by', render: (r) => fmtDate(r.reply_by) },
        { key: 'status', label: 'Status', render: (r) => <><ProcBadge kind="rfq" status={r.status} />{r.awarded_supplier_name && <div className="muted small">{r.awarded_supplier_name}</div>}</> },
      ]}
      fields={[]}
    />
  )
}
