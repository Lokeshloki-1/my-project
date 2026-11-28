import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { SAMPLE_TYPES } from '../components/dev/constants'
import { fmtDate, labelOf } from '../components/buyers/constants'

// Board columns; the two "approved" statuses share a column.
const COLUMNS = [
  { key: 'requested', label: 'Requested', statuses: ['requested'], hint: 'Waiting for the sampling room' },
  { key: 'in_progress', label: 'In progress', statuses: ['in_progress'], hint: 'Being made' },
  { key: 'ready', label: 'Ready', statuses: ['ready'], hint: 'Measure and send' },
  { key: 'sent', label: 'Sent to buyer', statuses: ['sent'], hint: 'Waiting for comments' },
  { key: 'approved', label: 'Approved', statuses: ['approved', 'approved_with_comments'], hint: '' },
  { key: 'rejected', label: 'Rejected', statuses: ['rejected'], hint: 'Make the next round' },
]

export default function Samples() {
  const [samples, setSamples] = useState(null)
  const [type, setType] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/samples/', { params: { page_size: 500, sample_type: type || undefined, search: search || undefined } })
      .then((r) => setSamples(r.data.results))
      .catch((e) => setError(errorMessage(e)))
  }, [type, search])

  if (error) return <div className="error">{error}</div>
  const late = (samples || []).filter((s) => s.is_late).length

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Samples</h1>
          <p className="muted">Proto → fit → size set → PP → TOP. An approved PP sample approves the style for production.
            {late > 0 && <span className="neg"> · {late} overdue</span>}</p>
        </div>
        <div className="actions">
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Sample type">
            <option value="">All types</option>
            {SAMPLE_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input className="search" placeholder="Search style, buyer, tracking…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <Link className="button secondary" to="/tech-packs">Tech packs</Link>
        </div>
      </div>
      {!samples ? <div className="muted">Loading…</div> : (
        <div className="board">
          {COLUMNS.map((col) => {
            const items = samples.filter((s) => col.statuses.includes(s.status))
            return (
              <section key={col.key} className={`board-col scol-${col.key}`}>
                <header>
                  <div><b>{col.label}</b>{col.hint && <div className="muted small">{col.hint}</div>}</div>
                  <span className="count">{items.length}</span>
                </header>
                <div className="board-cards">
                  {items.length === 0 && <div className="muted small empty">Nothing here</div>}
                  {items.map((s) => (
                    <Link key={s.id} to={`/samples/${s.id}`} className={`board-card ${s.is_late ? 'late' : ''}`}>
                      <div className="muted small">{s.sample_no} · round {s.round}</div>
                      <b>{s.style_no} · {labelOf(SAMPLE_TYPES, s.sample_type)}</b>
                      <div className="small">{s.style_name}</div>
                      <div className="muted small">{s.buyer_name} · {[s.colourway, s.size].filter(Boolean).join(' · ')}</div>
                      {s.status === 'approved_with_comments' && <div className="small warn-text">With comments</div>}
                      {s.due_date && !['sent', 'approved', 'approved_with_comments', 'rejected'].includes(s.status) && (
                        <div className={`small ${s.is_late ? 'neg' : 'muted'}`}>{s.is_late ? 'Overdue · ' : 'Due '}{fmtDate(s.due_date)}</div>
                      )}
                    </Link>
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </>
  )
}
