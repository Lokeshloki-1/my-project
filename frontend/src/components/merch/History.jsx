import { fmtDateTime } from '../buyers/constants'

export default function History({ items }) {
  if (!items?.length) return null
  return (
    <div className="card">
      <h2>History</h2>
      <ol className="timeline">
        {[...items].reverse().map((h) => (
          <li key={h.id}>
            <div className="tl-head"><b className="cap">{h.action}</b><span className="muted small">{fmtDateTime(h.created_at)} · {h.user_name || 'System'}</span></div>
            {h.note && <div className="tl-note">{h.note}</div>}
          </li>
        ))}
      </ol>
    </div>
  )
}
