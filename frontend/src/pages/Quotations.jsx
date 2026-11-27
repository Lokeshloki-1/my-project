import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import DocBadge from '../components/merch/DocBadge'
import { QUOTE_STATUSES, money } from '../components/merch/constants'
import { fmtDate } from '../components/buyers/constants'

export default function Quotations() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Quotations"
      subtitle="Price offers to approved buyers, built from approved cost sheets"
      endpoint="/quotations/"
      readOnly
      params={{ status: status || undefined }}
      headerExtra={
        <>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {QUOTE_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <Link className="button" to="/quotations/new">+ New</Link>
        </>
      }
      onRowClick={(row) => navigate(`/quotations/${row.id}`)}
      columns={[
        { key: 'quote_no', label: 'Quotation' },
        { key: 'buyer_name', label: 'Buyer', render: (r) => <><b>{r.buyer_name}</b><div className="muted small">{r.buyer_country}</div></> },
        { key: 'quote_date', label: 'Date', render: (r) => fmtDate(r.quote_date) },
        { key: 'valid_until', label: 'Valid until', render: (r) => <span className={r.is_expired ? 'neg' : ''}>{fmtDate(r.valid_until)}{r.is_expired && ' · expired'}</span> },
        { key: 'incoterm', label: 'Terms' },
        { key: 'total_quantity', label: 'Pcs', num: true, render: (r) => Number(r.total_quantity).toLocaleString('en-IN') },
        { key: 'total_amount', label: 'Value', num: true, render: (r) => <b>{money(r.total_amount, r.currency)}</b> },
        { key: 'status', label: 'Status', render: (r) => <DocBadge kind="qt" status={r.status} /> },
      ]}
      fields={[]}
    />
  )
}
