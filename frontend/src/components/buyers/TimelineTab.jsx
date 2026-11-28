import { useEffect, useState } from 'react'
import api, { errorMessage } from '../../api/client'
import BuyerStatusBadge from './BuyerStatusBadge'
import { fmtDateTime } from './constants'

export default function TimelineTab({ buyer }) {
  const [logs, setLogs] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get(`/buyers/${buyer.id}/timeline/`)
      .then((res) => setLogs(res.data))
      .catch((e) => setError(errorMessage(e)))
  }, [buyer.id, buyer.status])

  if (error) return <div className="error">{error}</div>
  if (!logs) return <div className="muted">Loading…</div>

  return (
    <>
      <h2>Timeline</h2>
      <ol className="timeline">
        {[...logs].reverse().map((log) => (
          <li key={log.id}>
            <div className="tl-head">
              <BuyerStatusBadge status={log.to_status} />
              <span className="muted small">{fmtDateTime(log.created_at)} · {log.user_name || 'System'}</span>
            </div>
            {log.note && <div className="tl-note">{log.note}</div>}
          </li>
        ))}
      </ol>
    </>
  )
}
