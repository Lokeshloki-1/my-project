import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Modal from '../components/Modal'
import { dhuResult } from '../components/qa/constants'
import { fmtDate } from '../components/buyers/constants'

const iso = (d) => d.toISOString().slice(0, 10)

export default function DefectControl() {
  const { canManage } = useAuth()
  const [range, setRange] = useState(() => ({ from: iso(new Date(Date.now() - 29 * 864e5)), to: iso(new Date()) }))
  const [data, setData] = useState(null)
  const [capas, setCapas] = useState([])
  const [capaStatus, setCapaStatus] = useState('open')
  const [closing, setClosing] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([
      api.get('/quality-summary/', { params: range }),
      api.get('/corrective-actions/', { params: { status: capaStatus || undefined, page_size: 200 } }),
    ]).then(([s, c]) => { setData(s.data); setCapas(c.data.results) }).catch((e) => setError(errorMessage(e)))
  }, [range, capaStatus])
  useEffect(() => { load() }, [load])

  if (error) return <div className="error">{error}</div>
  if (!data) return <div className="muted">Loading…</div>
  const top = data.pareto.slice(0, 10)

  return (
    <>
      <div className="page-head">
        <div><h1>Defect Control</h1><p className="muted">Where defects come from, how lines and styles perform, and the corrective actions that are still open.</p></div>
        <div className="actions">
          <input type="date" value={range.from} onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} aria-label="From" />
          <input type="date" value={range.to} onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} aria-label="To" />
          <Link className="button secondary" to="/quality/inline">Inline QC</Link>
          <Link className="button secondary" to="/quality/final">Final inspections</Link>
        </div>
      </div>
      <div className="kpis">
        <div className="card kpi"><div className="muted small">Inline DHU</div><div className={`kpi-value dhu-${data.inline.dhu == null ? '' : dhuResult(data.inline.dhu)}`}>{data.inline.dhu == null ? '—' : `${data.inline.dhu}%`}</div>
          <div className="small muted">{data.inline.defects} defects in {data.inline.pieces} pcs · {data.inline.checks} checks</div></div>
        <div className="card kpi"><div className="muted small">Red inline checks</div><div className={`kpi-value ${data.inline.red ? 'neg' : ''}`}>{data.inline.red}</div></div>
        <div className="card kpi"><div className="muted small">Final inspection pass rate</div><div className="kpi-value">{data.final.pass_rate == null ? '—' : `${data.final.pass_rate}%`}</div>
          <div className="small muted">{data.final.passed} passed · {data.final.failed} failed</div></div>
        <div className="card kpi"><div className="muted small">Open corrective actions</div><div className={`kpi-value ${data.capa.open ? 'neg' : ''}`}>{data.capa.open}</div>
          <div className="small muted">{data.capa.overdue} overdue</div></div>
      </div>

      <div className="card">
        <h2>Top defects (Pareto)</h2>
        {top.length === 0 ? <p className="muted">No defects recorded in this period.</p> : (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={top} margin={{ top: 8, right: 8, bottom: 40, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="name" tickLine={false} axisLine={false} angle={-25} textAnchor="end" interval={0} height={60} tick={{ fontSize: 11 }} />
              <YAxis yAxisId="n" tickLine={false} axisLine={false} width={36} allowDecimals={false} />
              <YAxis yAxisId="p" orientation="right" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={44} />
              <Tooltip formatter={(v, n) => (n === 'Cumulative' ? `${v}%` : v)} cursor={{ fill: 'var(--hover)' }} />
              <Bar yAxisId="n" dataKey="inline" stackId="a" name="Inline" fill="#3b82f6" />
              <Bar yAxisId="n" dataKey="final" stackId="a" name="Final" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              <Line yAxisId="p" dataKey="cumulative_percent" name="Cumulative" stroke="var(--neg)" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        <p className="muted small">Fix the defects on the left first: they make up most of the problem. Blue = inline QC, amber = final inspection.</p>
      </div>

      <div className="grid-2">
        <DhuTable title="DHU by line" rows={data.by_line} />
        <DhuTable title="DHU by style" rows={data.by_style} />
      </div>

      <div className="card">
        <div className="card-head"><h2>Corrective actions</h2>
          <select value={capaStatus} onChange={(e) => setCapaStatus(e.target.value)} aria-label="Status"><option value="open">Open</option><option value="closed">Closed</option><option value="">All</option></select></div>
        <div className="table-wrap">
          <table className="cost-lines">
            <thead><tr><th>#</th><th>Source</th><th>Problem</th><th>Owner / due</th><th>Root cause & action</th><th /></tr></thead>
            <tbody>
              {capas.length === 0 && <tr><td colSpan={6} className="muted center">Nothing here.</td></tr>}
              {capas.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td><span className={`badge badge-src-${c.source}`}>{c.source_label}</span>{c.production_order && <div className="small"><Link to={`/production/${c.production_order}`}>{c.style_no}</Link></div>}</td>
                  <td className="wrap">{c.problem}<div className="muted small">{fmtDate(c.created_at)}</div></td>
                  <td>{c.owner || '—'}<div className={`small ${c.is_overdue ? 'neg' : 'muted'}`}>{c.due_date ? `${c.is_overdue ? 'Overdue · ' : 'Due '}${fmtDate(c.due_date)}` : 'No due date'}</div></td>
                  <td className="wrap small">{c.root_cause ? <><b>Cause:</b> {c.root_cause}<br /></> : null}{c.action ? <><b>Action:</b> {c.action}</> : <span className="muted">—</span>}
                    {c.status === 'closed' && <div className="pos">Closed by {c.closed_by_name} · {fmtDate(c.closed_at)}</div>}</td>
                  <td>{c.status === 'open' && canManage && <button className="small-btn" onClick={() => setClosing(c)}>Close</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {closing && <CloseCapa capa={closing} onClose={() => setClosing(null)} onDone={() => { setClosing(null); load() }} />}
    </>
  )
}

function DhuTable({ title, rows }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {rows.length === 0 ? <p className="muted small">No inline checks.</p> : (
        <table className="compact">
          <thead><tr><th>{title.split(' ').pop() === 'line' ? 'Line' : 'Style'}</th><th className="num">Checks</th><th className="num">Pieces</th><th className="num">Defects</th><th className="num">DHU</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id}><td>{r.name}</td><td className="num">{r.checks}</td><td className="num">{r.pieces}</td><td className="num">{r.defects}</td>
              <td className="num"><span className={`light light-${dhuResult(r.dhu || 0)}`}>{r.dhu}%</span></td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  )
}

function CloseCapa({ capa, onClose, onDone }) {
  const [rootCause, setRootCause] = useState(capa.root_cause)
  const [action, setAction] = useState(capa.action)
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault(); setError('')
    try { await api.post(`/corrective-actions/${capa.id}/close/`, { root_cause: rootCause, action }); onDone() } catch (err) { setError(errorMessage(err)) }
  }
  return (
    <Modal title={`Close corrective action #${capa.id}`} onClose={onClose}>
      <form onSubmit={submit}>
        <p className="muted small">{capa.problem}</p>
        <label className="field"><span>Root cause *</span><textarea rows={2} value={rootCause} onChange={(e) => setRootCause(e.target.value)} required /></label>
        <label className="field"><span>Action taken so it doesn’t happen again *</span><textarea rows={3} value={action} onChange={(e) => setAction(e.target.value)} required /></label>
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="approve">Close action</button>
        </div></div>
      </form>
    </Modal>
  )
}
