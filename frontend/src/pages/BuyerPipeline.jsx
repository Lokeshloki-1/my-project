import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { BUYER_TYPES, labelOf } from '../components/buyers/constants'

// Board columns in onboarding order. Rejected is shown last and dimmed.
const COLUMNS = [
  { status: 'registered', hint: 'Fill profile, contacts & requirements' },
  { status: 'pending_credit', hint: 'Waiting for accounts' },
  { status: 'credit_failed', hint: 'Fix and resubmit' },
  { status: 'pending_approval', hint: 'Waiting for a manager' },
  { status: 'approved', hint: 'Ready for quotations' },
  { status: 'rejected', hint: '' },
]

export default function BuyerPipeline() {
  const [pipeline, setPipeline] = useState(null)
  const [buyers, setBuyers] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.get('/buyers/pipeline/'), api.get('/buyers/', { params: { page_size: 500, ordering: '-updated_at' } })])
      .then(([p, b]) => { setPipeline(p.data); setBuyers(b.data.results) })
      .catch((e) => setError(errorMessage(e)))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!pipeline) return <div className="muted">Loading…</div>

  const stage = Object.fromEntries(pipeline.stages.map((s) => [s.status, s]))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Buyer Pipeline</h1>
          <p className="muted">{pipeline.total} buyers in onboarding · <Link to="/buyer-enquiries">{pipeline.open_enquiries} open enquiries</Link></p>
        </div>
        <div className="actions">
          <Link className="button secondary" to="/buyer-enquiries">Enquiries</Link>
          <Link className="button" to="/buyers">All buyers</Link>
        </div>
      </div>

      <div className="board">
        {COLUMNS.map((col) => {
          const items = buyers.filter((b) => b.status === col.status)
          return (
            <section key={col.status} className={`board-col col-${col.status}`}>
              <header>
                <div><b>{stage[col.status]?.label}</b><div className="muted small">{col.hint}</div></div>
                <span className="count">{stage[col.status]?.count ?? 0}</span>
              </header>
              <div className="board-cards">
                {items.length === 0 && <div className="muted small empty">Nothing here</div>}
                {items.map((b) => (
                  <Link key={b.id} to={`/buyers/${b.id}`} className="board-card">
                    <div className="muted small">{b.buyer_code}</div>
                    <b>{b.legal_name}</b>
                    <div className="small">{[b.city, b.country].filter(Boolean).join(', ')} · {labelOf(BUYER_TYPES, b.buyer_type)}</div>
                    {b.primary_contact && <div className="muted small">{b.primary_contact.name}</div>}
                  </Link>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </>
  )
}
