import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import Modal from '../components/Modal'
import useOptions from '../components/useOptions'
import { DEFECT_CATEGORIES, RESULTS, dhuResult } from '../components/qa/constants'
import { fmtDate, labelOf } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)

export default function InlineQC() {
  const [query] = useSearchParams()
  const [rows, setRows] = useState(null)
  const [line, setLine] = useState('')
  const [result, setResult] = useState('')
  const [adding, setAdding] = useState(Boolean(query.get('wo')))
  const [reload, setReload] = useState(0)
  const [error, setError] = useState('')
  const lines = useOptions('/production-lines/', { is_active: true })

  useEffect(() => {
    api.get('/inline-inspections/', { params: { page_size: 200, line: line || undefined, result: result || undefined } })
      .then((r) => setRows(r.data.results)).catch((e) => setError(errorMessage(e)))
  }, [line, result, reload])

  if (error) return <div className="error">{error}</div>

  return (
    <>
      <div className="page-head">
        <div><h1>Inline QC</h1><p className="muted">Random checks on the sewing lines. DHU = defects ÷ pieces checked × 100 — green ≤ 2.5, amber ≤ 5, red above (opens a corrective action).</p></div>
        <div className="actions">
          <select value={line} onChange={(e) => setLine(e.target.value)} aria-label="Line"><option value="">All lines</option>{lines.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select>
          <select value={result} onChange={(e) => setResult(e.target.value)} aria-label="Result"><option value="">All results</option>{RESULTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <button onClick={() => setAdding(true)}>+ New check</button>
        </div>
      </div>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Date</th><th>Line</th><th>Style</th><th>Operation / operator</th><th className="num">Checked</th><th className="num">Defects</th><th className="num">DHU</th><th>Result</th><th>Defects found</th></tr></thead>
          <tbody>
            {!rows ? <tr><td colSpan={9} className="muted center">Loading…</td></tr> : rows.length === 0 ? <tr><td colSpan={9} className="muted center">No inline checks yet.</td></tr> : rows.map((r) => (
              <tr key={r.id}>
                <td>{fmtDate(r.date)}</td>
                <td>{r.line_name}</td>
                <td><Link to={`/production/${r.production_order}`}>{r.style_no}</Link><div className="muted small">{r.wo_no}</div></td>
                <td>{r.operation || '—'}<div className="muted small">{r.operator}</div></td>
                <td className="num">{r.pieces_checked}</td>
                <td className="num">{r.total_defects}<div className="muted small">{r.defective_pieces} pcs</div></td>
                <td className="num"><b>{Number(r.dhu).toFixed(1)}%</b></td>
                <td><span className={`light light-${r.result}`}>{labelOf(RESULTS, r.result)}</span>{r.capa_id && <div className="small"><Link to="/quality">action #{r.capa_id}</Link></div>}</td>
                <td className="small wrap">{r.defects.map((d) => `${d.name} ×${d.count}`).join(', ') || <span className="muted">None</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {adding && <NewCheck woId={query.get('wo')} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setReload((n) => n + 1) }} />}
    </>
  )
}

function NewCheck({ woId, onClose, onSaved }) {
  const orders = useOptions('/production-orders/', { status: 'in_progress' })
  const types = useOptions('/defect-types/', { is_active: true })
  const [form, setForm] = useState(() => ({ production_order: woId || '', date: todayStr(), operation: '', operator: '', pieces_checked: '20', defective_pieces: '0', action_taken: '' }))
  const [counts, setCounts] = useState({})
  const [cat, setCat] = useState('sewing')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const bump = (id, d) => setCounts((c) => ({ ...c, [id]: Math.max(0, (c[id] || 0) + d) }))
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const pieces = Number(form.pieces_checked) || 0
  const dhu = pieces ? (total / pieces) * 100 : 0
  const res = dhuResult(dhu)

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await api.post('/inline-inspections/', { ...form, defects: Object.entries(counts).filter(([, n]) => n > 0).map(([id, n]) => ({ defect_type: Number(id), count: n })) })
      onSaved()
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }

  return (
    <Modal title="Inline QC check" onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label className="field"><span>Work order (in production) *</span>
            <select value={form.production_order} onChange={(e) => set('production_order', e.target.value)} required>
              <option value="">— choose —</option>
              {orders.map((o) => <option key={o.id} value={o.id}>{o.style_no} · {o.line_name} · {o.wo_no}</option>)}
            </select></label>
          <label className="field"><span>Date</span><input type="date" value={form.date} max={todayStr()} onChange={(e) => set('date', e.target.value)} /></label>
          <label className="field"><span>Operation</span><input value={form.operation} onChange={(e) => set('operation', e.target.value)} placeholder="e.g. Side seam" /></label>
          <label className="field"><span>Operator</span><input value={form.operator} onChange={(e) => set('operator', e.target.value)} placeholder="Name or number" /></label>
          <label className="field"><span>Pieces checked *</span><input type="number" min="1" value={form.pieces_checked} onChange={(e) => set('pieces_checked', e.target.value)} required /></label>
          <label className="field"><span>Pieces with defects *</span><input type="number" min="0" max={pieces} value={form.defective_pieces} onChange={(e) => set('defective_pieces', e.target.value)} required /></label>
        </div>
        <div className="card-head" style={{ marginTop: 12 }}>
          <h3 style={{ margin: 0 }}>Defects found</h3>
          <div className="seg">{DEFECT_CATEGORIES.slice(0, 5).map(([v, l]) => <button key={v} type="button" className={cat === v ? 'on' : ''} onClick={() => setCat(v)}>{l.split(' ')[0]}</button>)}</div>
        </div>
        <div className="defect-grid">
          {types.filter((t) => t.category === cat).map((t) => (
            <div key={t.id} className={`defect-counter ${counts[t.id] ? 'on' : ''}`}>
              <span><b>{t.name}</b><small className="muted">{t.code}</small></span>
              <span className="counter">
                <button type="button" className="secondary" onClick={() => bump(t.id, -1)} aria-label={`Less ${t.name}`}>−</button>
                <b>{counts[t.id] || 0}</b>
                <button type="button" onClick={() => bump(t.id, 1)} aria-label={`More ${t.name}`}>+</button>
              </span>
            </div>
          ))}
        </div>
        <div className={`dhu-live light-box-${res}`}>
          <span>{total} defects in {pieces} pieces</span>
          <b>DHU {dhu.toFixed(1)}%</b>
          <span className={`light light-${res}`}>{labelOf(RESULTS, res)}</span>
        </div>
        {res === 'red' && <label className="field"><span>Action taken on the line (a corrective action will be opened)</span>
          <textarea rows={2} value={form.action_taken} onChange={(e) => set('action_taken', e.target.value)} placeholder="e.g. Machine stopped, needle changed, operator re-trained" /></label>}
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy}>Save check</button>
        </div></div>
      </form>
    </Modal>
  )
}
