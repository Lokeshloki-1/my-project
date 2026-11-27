import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import StageBars from '../components/prod/StageBars'
import WOBadge from '../components/prod/WOBadge'
import { WO_STATUSES, isoDay, pcs } from '../components/prod/constants'
import { fmtDate } from '../components/buyers/constants'

const DAY = 864e5
const WEEKS = 6

function mondayOf(d) {
  const x = new Date(d); x.setHours(0, 0, 0, 0)
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7))
  return x
}

export default function ProductionPlan() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState(null)
  const [lines, setLines] = useState([])
  const [status, setStatus] = useState('planned,in_progress')
  const [offset, setOffset] = useState(-1)
  const [error, setError] = useState('')
  const [now] = useState(() => Date.now())

  useEffect(() => {
    Promise.all([
      api.get('/production-orders/', { params: { page_size: 500, status__in: status || undefined } }),
      api.get('/production-lines/', { params: { is_active: true, page_size: 100 } }),
    ]).then(([o, l]) => { setOrders(o.data.results); setLines(l.data.results) }).catch((e) => setError(errorMessage(e)))
  }, [status])

  const [start, days] = useMemo(() => {
    const s = mondayOf(now + offset * 7 * DAY)
    return [s, Array.from({ length: WEEKS * 7 }, (_, i) => new Date(s.getTime() + i * DAY))]
  }, [offset, now])

  if (error) return <div className="error">{error}</div>
  if (!orders) return <div className="muted">Loading…</div>

  const todayIdx = Math.floor((now - start.getTime()) / DAY)
  const col = (iso) => Math.round((new Date(`${iso}T00:00:00`).getTime() - start.getTime()) / DAY)

  return (
    <>
      <div className="page-head">
        <div><h1>Production Plan</h1><p className="muted">Work orders per sewing line. Bars show the planned dates; the fill shows finished pieces.</p></div>
        <div className="actions">
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="planned,in_progress">Open work orders</option>
            <option value="">All</option>
            {WO_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <Link className="button secondary" to="/production/daily">Daily output</Link>
          <button onClick={() => navigate('/production/new')}>+ Plan production</button>
        </div>
      </div>

      <div className="card gantt-card">
        <div className="gantt-nav">
          <button className="secondary small-btn" onClick={() => setOffset(offset - 2)}>← Earlier</button>
          <span className="muted small">{fmtDate(isoDay(start))} – {fmtDate(isoDay(days[days.length - 1]))}</span>
          <button className="secondary small-btn" onClick={() => setOffset(-1)}>Today</button>
          <button className="secondary small-btn" onClick={() => setOffset(offset + 2)}>Later →</button>
        </div>
        <div className="gantt-scroll">
          <div className="gantt" style={{ gridTemplateColumns: `140px repeat(${days.length}, minmax(26px, 1fr))` }}>
            <div className="g-corner" />
            {days.map((d, i) => (
              <div key={i} className={`g-day ${d.getDay() === 0 ? 'sun' : ''} ${i === todayIdx ? 'today' : ''}`}>
                <small className="g-month">{d.getDate() === 1 || i === 0 ? d.toLocaleDateString('en-IN', { month: 'short' }) : ''}</small>
                {d.getDay() === 1 ? <b>{d.getDate()}</b> : d.getDate()}
              </div>
            ))}
            {lines.map((line, r) => {
              const mine = orders.filter((o) => o.line === line.id)
              return [
                <div key={`l${line.id}`} className="g-line" style={{ gridRow: r + 2 }}><b>{line.name}</b><small>{line.operators} ops · {Number(line.efficiency_pct)}%</small></div>,
                ...days.map((d, i) => <div key={`c${line.id}-${i}`} className={`g-cell ${d.getDay() === 0 ? 'sun' : ''} ${i === todayIdx ? 'today' : ''}`} style={{ gridRow: r + 2, gridColumn: i + 2 }} />),
                ...mine.map((o) => {
                  const a = Math.max(col(o.planned_start), 0), b = Math.min(col(o.planned_end), days.length - 1)
                  if (b < 0 || a > days.length - 1) return null
                  const pct = Math.min(100, (o.progress.finished / o.quantity) * 100)
                  const late = o.status === 'in_progress' && col(o.planned_end) < todayIdx && pct < 100
                  return (
                    <Link key={o.id} to={`/production/${o.id}`} className={`g-bar g-${o.status} ${late ? 'late' : ''}`} style={{ gridRow: r + 2, gridColumn: `${a + 2} / ${b + 3}` }}
                      title={`${o.wo_no} · ${o.style_no} · ${pcs(o.quantity)} pcs · ${fmtDate(o.planned_start)}–${fmtDate(o.planned_end)}`}>
                      <span className="g-fill" style={{ width: `${pct}%` }} />
                      <span className="g-text">{o.style_no} · {pcs(o.quantity)}</span>
                    </Link>
                  )
                }),
              ]
            })}
          </div>
        </div>
        {lines.length === 0 && <p className="muted small">No sewing lines yet. <Link to="/production/lines">Add lines</Link> first.</p>}
      </div>

      <div className="card table-wrap">
        <table>
          <thead><tr><th>Work order</th><th>Style</th><th>Order</th><th>Line</th><th>Dates</th><th className="num">Pcs</th><th>Progress</th><th>Status</th></tr></thead>
          <tbody>
            {orders.length === 0 && <tr><td colSpan={8} className="muted center">No work orders.</td></tr>}
            {orders.map((o) => (
              <tr key={o.id} className="clickable" onClick={() => navigate(`/production/${o.id}`)}>
                <td>{o.wo_no}</td>
                <td><b>{o.style_no}</b><div className="muted small">{o.style_name}{o.colourway && ` · ${o.colourway}`}</div></td>
                <td>{o.oc_no}<div className="muted small">{o.buyer_name} · ships {fmtDate(o.ship_date)}</div></td>
                <td>{o.line_name}</td>
                <td className="small">{fmtDate(o.planned_start)} – {fmtDate(o.planned_end)}</td>
                <td className="num">{pcs(o.quantity)}</td>
                <td style={{ minWidth: 200 }}><StageBars quantity={o.quantity} progress={o.progress} compact /></td>
                <td><WOBadge status={o.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
