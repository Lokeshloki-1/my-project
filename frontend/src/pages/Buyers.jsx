import { useNavigate, useSearchParams } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import BuyerStatusBadge from '../components/buyers/BuyerStatusBadge'
import { BUYER_STATUSES, BUYER_TYPES, labelOf, opts } from '../components/buyers/constants'

export default function Buyers() {
  const navigate = useNavigate()
  const [query, setQuery] = useSearchParams()
  const status = query.get('status') || ''

  return (
    <ResourcePage
      title="Buyers"
      subtitle="Registered buyers and where each one is in onboarding"
      endpoint="/buyers/"
      params={{ status: status || undefined }}
      headerExtra={
        <select value={status} onChange={(e) => setQuery(e.target.value ? { status: e.target.value } : {})} aria-label="Filter by status">
          <option value="">All statuses</option>
          {BUYER_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      }
      defaults={{ buyer_type: 'brand', preferred_currency: 'USD', default_incoterm: 'FOB' }}
      onRowClick={(row) => navigate(`/buyers/${row.id}`)}
      onCreated={(buyer) => navigate(`/buyers/${buyer.id}`)}
      columns={[
        { key: 'buyer_code', label: 'Code' },
        { key: 'legal_name', label: 'Buyer', render: (r) => <><b>{r.legal_name}</b>{r.trade_name && <div className="muted small">{r.trade_name}</div>}</> },
        { key: 'buyer_type', label: 'Type', render: (r) => labelOf(BUYER_TYPES, r.buyer_type) },
        { key: 'country', label: 'Country', render: (r) => [r.city, r.country].filter(Boolean).join(', ') },
        { key: 'primary_contact', label: 'Primary contact', render: (r) => r.primary_contact ? <>{r.primary_contact.name}<div className="muted small">{r.primary_contact.email}</div></> : <span className="muted">—</span> },
        { key: 'status', label: 'Status', render: (r) => <BuyerStatusBadge status={r.status} /> },
      ]}
      fields={[
        { name: 'company', label: 'Our company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'legal_name', label: 'Legal name', required: true },
        { name: 'trade_name', label: 'Trade / brand name' },
        { name: 'buyer_type', label: 'Buyer type', type: 'select', options: opts(BUYER_TYPES), required: true },
        { name: 'country', label: 'Country', required: true },
        { name: 'city', label: 'City' },
      ]}
    />
  )
}
