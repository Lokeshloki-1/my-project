import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import ResourcePage from '../components/ResourcePage'
import { ENQUIRY_STATUSES, SOURCES, fmtDate, labelOf, opts } from '../components/buyers/constants'

function EnquiryActions({ form, close, reload }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!form.id) return null

  if (form.status === 'converted') {
    return (
      <div className="notice">
        <span>This enquiry was converted into a buyer.</span>
        {form.buyer_id && <Link to={`/buyers/${form.buyer_id}`}>Open buyer →</Link>}
      </div>
    )
  }
  if (form.status === 'rejected') {
    return <div className="notice warn"><span><b>Rejected:</b> {form.reject_reason}</span></div>
  }

  const convert = async () => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/buyer-enquiries/${form.id}/convert/`)
      navigate(`/buyers/${data.id}`)
    } catch (e) { setError(errorMessage(e)); setBusy(false) }
  }
  const reject = async () => {
    const reason = window.prompt('Why is this enquiry being rejected?')
    if (!reason) return
    setBusy(true); setError('')
    try {
      await api.post(`/buyer-enquiries/${form.id}/reject/`, { reason })
      close(); reload()
    } catch (e) { setError(errorMessage(e)); setBusy(false) }
  }

  return (
    <div className="next-step">
      <div>
        <b>Next step: register this buyer</b>
        <p className="muted small">Creates a buyer record with this contact as the primary contact. Save any changes first.</p>
      </div>
      <div className="actions">
        <button type="button" className="secondary" onClick={reject} disabled={busy}>Reject</button>
        <button type="button" onClick={convert} disabled={busy}>Convert to buyer →</button>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  )
}

const today = () => new Date().toISOString().slice(0, 10)

export default function BuyerEnquiries() {
  const [status, setStatus] = useState('')
  return (
    <ResourcePage
      title="Buyer Enquiries"
      subtitle="Step 1 · New buyer leads from email, trade fairs, agents and the website"
      endpoint="/buyer-enquiries/"
      params={{ status: status || undefined }}
      headerExtra={
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {ENQUIRY_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      }
      defaults={{ source: 'email', status: 'new', received_on: today() }}
      columns={[
        { key: 'enquiry_no', label: 'Enquiry' },
        { key: 'buyer_name', label: 'Buyer', render: (r) => <><b>{r.buyer_name}</b><div className="muted small">{r.contact_name}</div></> },
        { key: 'country', label: 'Country' },
        { key: 'source', label: 'Source', render: (r) => labelOf(SOURCES, r.source) },
        { key: 'expected_volume', label: 'Pcs / year', num: true, render: (r) => (r.expected_volume ? Number(r.expected_volume).toLocaleString('en-IN') : '—') },
        { key: 'received_on', label: 'Received', render: (r) => fmtDate(r.received_on) },
        { key: 'status', label: 'Status', render: (r) => <span className={`badge badge-enq-${r.status}`}>{labelOf(ENQUIRY_STATUSES, r.status)}</span> },
      ]}
      fields={[
        { name: 'company', label: 'Our company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'source', label: 'Source', type: 'select', options: opts(SOURCES), required: true },
        { name: 'buyer_name', label: 'Buyer company name', required: true },
        { name: 'country', label: 'Country', required: true },
        { name: 'contact_name', label: 'Contact person' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'received_on', label: 'Received on', type: 'date', required: true },
        { name: 'expected_volume', label: 'Expected pieces / year', type: 'number' },
        { name: 'status', label: 'Status', type: 'select', options: opts(ENQUIRY_STATUSES.slice(0, 2)), required: true },
        { name: 'product_interest', label: 'Products of interest', type: 'textarea', full: true },
        { name: 'notes', label: 'Notes', type: 'textarea', full: true },
      ]}
      renderFormExtra={(form, helpers) => <EnquiryActions form={form} {...helpers} />}
    />
  )
}
