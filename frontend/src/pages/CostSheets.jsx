import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import DocBadge from '../components/merch/DocBadge'
import { COST_STATUSES, money } from '../components/merch/constants'
import { CATEGORIES, labelOf, opts } from '../components/buyers/constants'

export default function CostSheets() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  const [query] = useSearchParams()
  const buyer = query.get('buyer') || undefined
  return (
    <ResourcePage
      title="Cost Sheets"
      subtitle="Garment costing per style: materials, CMT, overheads and margin → FOB price per piece"
      endpoint="/cost-sheets/"
      params={{ status: status || undefined, buyer }}
      headerExtra={
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {COST_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      }
      defaults={{ category: 'knits', buyer }}
      onRowClick={(row) => navigate(`/costing/${row.id}`)}
      onCreated={(sheet) => navigate(`/costing/${sheet.id}`)}
      columns={[
        { key: 'cost_no', label: 'Cost sheet' },
        { key: 'style_no', label: 'Style', render: (r) => <><b>{r.style_no}</b><div className="muted small">{r.style_name}</div></> },
        { key: 'buyer_name', label: 'Buyer' },
        { key: 'category', label: 'Category', render: (r) => labelOf(CATEGORIES, r.category) },
        { key: 'total_cost', label: 'Cost / pc', num: true, render: (r) => money(r.total_cost, r.currency, 2) },
        { key: 'fob_price', label: 'FOB / pc', num: true, render: (r) => <b>{money(r.fob_price, r.currency)}</b> },
        { key: 'status', label: 'Status', render: (r) => <DocBadge kind="cs" status={r.status} /> },
      ]}
      fields={[
        { name: 'buyer', label: 'Buyer', type: 'select', optionsUrl: '/buyers/', optionLabel: (b) => `${b.legal_name} (${b.country})`, required: true },
        { name: 'style_no', label: 'Style number', required: true },
        { name: 'style_name', label: 'Style name', required: true },
        { name: 'category', label: 'Category', type: 'select', options: opts(CATEGORIES), required: true },
      ]}
    />
  )
}
