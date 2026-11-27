import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { pcs } from '../components/prod/constants'
import { fmtDate } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)
const shift = (iso, n) => { const d = new Date(`${iso}T12:00:00`); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

export default function DailyOutput() {
  const [day, setDay] = useState(todayStr)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/production-orders/daily/', { params: { date: day } }).then((r) => setReport(r.data)).catch((e) => setError(errorMessage(e)))
  }, [day])

  if (error) return <div className="error">{error}</div>
  if (!report) return <div className="muted">Loading…</div>
  const target = report.lines.reduce((a, l) => a + l.target, 0)
  const sewn = report.lines.reduce((a, l) => a + l.sewn, 0)

  return (
    <>
      <div className="page-head">
        <div><h1>Daily Output</h1><p className="muted">Sewing output per line against its target, and what cutting and finishing did.</p></div>
        <div className="actions">
          <button className="secondary" onClick={() => setDay(shift(day, -1))} aria-label="Previous day">←</button>
          <input type="date" value={day} max={todayStr()} onChange={(e) => setDay(e.target.value || todayStr())} aria-label="Date" />
          <button className="secondary" onClick={() => setDay(shift(day, 1))} disabled={day >= todayStr()} aria-label="Next day">→</button>
          <Link className="button secondary" to="/production">Plan</Link>
        </div>
      </div>
      <div className="kpis">
        <div className="card kpi"><div className="muted small">Cut</div><div className="kpi-value">{pcs(report.stages.cutting.good)}</div></div>
        <div className="card kpi"><div className="muted small">Sewn · target {pcs(target)}</div><div className={`kpi-value ${target && sewn < target * 0.9 ? 'neg' : ''}`}>{pcs(sewn)}</div>
          <div className="small muted">{target ? `${Math.round((sewn / target) * 100)}% of target` : 'No line was planned'}</div></div>
        <div className="card kpi"><div className="muted small">Finished</div><div className="kpi-value">{pcs(report.stages.finishing.good)}</div></div>
        <div className="card kpi"><div className="muted small">Rejected (sewing + finishing)</div><div className="kpi-value">{pcs(report.stages.sewing.rejected + report.stages.finishing.rejected)}</div></div>
      </div>
      <div className="line-cards">
        {report.lines.map((l) => {
          const pct = l.target ? Math.min(100, (l.sewn / l.target) * 100) : 0
          const tone = l.achievement_pct == null ? '' : l.achievement_pct >= 95 ? 'good' : l.achievement_pct >= 80 ? 'ok' : 'bad'
          return (
            <div key={l.line} className={`card line-card ${tone}`}>
              <div className="card-head"><div><b>{l.line_name}</b><div className="muted small">{l.operators} operators{l.style_no && ` · ${l.style_no}`}{l.smv && ` · SMV ${Number(l.smv)}`}</div></div>
                {l.work_order && <Link className="small" to={`/production/${l.work_order}`}>{l.wo_no}</Link>}</div>
              <div className="line-figs"><span className="kpi-value">{pcs(l.sewn)}</span><span className="muted">/ {pcs(l.target)} target</span></div>
              <div className="sb-track big"><span className={`sb-fill line-${tone}`} style={{ width: `${pct}%` }} /></div>
              <div className="small muted">{l.achievement_pct != null ? `${l.achievement_pct}% of target` : 'Nothing planned'}{l.efficiency_pct != null && ` · efficiency ${l.efficiency_pct}%`}{l.rejected > 0 && ` · ${l.rejected} rejected`}</div>
            </div>
          )
        })}
        {report.lines.length === 0 && <p className="muted">No active sewing lines. <Link to="/production/lines">Add lines</Link>.</p>}
      </div>
      <p className="muted small">{fmtDate(day)}. Efficiency = pieces × SMV ÷ (operators × working minutes).</p>
    </>
  )
}
