import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import DevBadge from '../components/dev/DevBadge'
import { TP_STATUSES } from '../components/dev/constants'
import { CATEGORIES, fmtDate, labelOf, opts } from '../components/buyers/constants'

export default function TechPacks() {
  const navigate = useNavigate()
  const [query] = useSearchParams()
  const buyer = query.get('buyer') || undefined
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Tech Packs"
      subtitle="Style specifications: measurements, bill of materials and construction — released before sampling"
      endpoint="/tech-packs/"
      params={{ status: status || undefined, buyer }}
      headerExtra={
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {TP_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      }
      defaults={{ category: 'knits', buyer }}
      onRowClick={(row) => navigate(`/tech-packs/${row.id}`)}
      onCreated={(tp) => navigate(`/tech-packs/${tp.id}`)}
      columns={[
        { key: 'tp_no', label: 'Tech pack', render: (r) => <>{r.tp_no}<div className="muted small">Rev {r.revision}</div></> },
        { key: 'style_no', label: 'Style', render: (r) => <><b>{r.style_no}</b><div className="muted small">{r.style_name}</div></> },
        { key: 'buyer_name', label: 'Buyer' },
        { key: 'season', label: 'Season' },
        { key: 'category', label: 'Category', render: (r) => labelOf(CATEGORIES, r.category) },
        { key: 'sample_count', label: 'Samples', num: true },
        { key: 'updated_at', label: 'Updated', render: (r) => fmtDate(r.updated_at) },
        { key: 'status', label: 'Status', render: (r) => <><DevBadge kind="tp" status={r.status} />{r.production_approved && <span className="badge badge-tp-prod" title="PP sample approved">Production ✓</span>}</> },
      ]}
      fields={[
        { name: 'buyer', label: 'Buyer', type: 'select', optionsUrl: '/buyers/', optionLabel: (b) => `${b.legal_name} (${b.country})`, required: true },
        { name: 'style_no', label: 'Style number', required: true },
        { name: 'style_name', label: 'Style name', required: true },
        { name: 'season', label: 'Season (e.g. SS27)' },
        { name: 'category', label: 'Category', type: 'select', options: opts(CATEGORIES), required: true },
      ]}
    />
  )
}
