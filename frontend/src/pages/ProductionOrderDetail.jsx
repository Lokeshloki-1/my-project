import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import useOptions from '../components/useOptions'
import History from '../components/merch/History'
import ReasonDialog from '../components/merch/ReasonDialog'
import StageBars from '../components/prod/StageBars'
import WOBadge from '../components/prod/WOBadge'
import { STAGES, pcs } from '../components/prod/constants'
import { qty } from '../components/proc/constants'
import { fmtDate, labelOf } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)

export default function ProductionOrderDetail() {
  const { id } = useParams()
  return id ? <WorkOrder id={id} /> : <PlanForm />
}

// ---------------------------------------------------------------- planning form

function splitEvenly(total, sizes) {
  if (!sizes.length) return {}
  const base = Math.floor(total / sizes.length)
  const out = Object.fromEntries(sizes.map((s) => [s, base]))
  let left = total - base * sizes.length
  for (const s of sizes.slice(Math.floor((sizes.length - left) / 2))) { if (left-- <= 0) break; out[s] += 1 }
  return out
}

function PlanForm() {
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(query.get('order') || '')
  const [info, setInfo] = useState(null)
  const [form, setForm] = useState(() => ({ order_line: '', quantity: '', sizes: {}, line: '', smv: '12', planned_start: todayStr(), planned_end: '', colourway: '', notes: '' }))
  const [cap, setCap] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const orders = useOptions('/order-confirmations/', { status: 'confirmed' })
  const lines = useOptions(info ? '/production-lines/' : null, info ? { company: info.company, is_active: true } : null)

  useEffect(() => {
    if (!order) return
    api.get('/production-orders/order-lines/', { params: { order } }).then((r) => setInfo(r.data)).catch((e) => setError(errorMessage(e)))
  }, [order])
  useEffect(() => {
    if (!form.line || !(Number(form.smv) > 0) || !(Number(form.quantity) > 0)) return
    api.get('/production-orders/capacity/', { params: { line: form.line, smv: form.smv, quantity: form.quantity, start: form.planned_start } })
      .then((r) => setCap(r.data)).catch(() => setCap(null))
  }, [form.line, form.smv, form.quantity, form.planned_start])

  const style = info?.lines.find((l) => String(l.order_line) === String(form.order_line))
  const sizeList = style?.sizes?.length ? style.sizes : Object.keys(form.sizes)
  const sizeSum = Object.values(form.sizes).reduce((a, v) => a + (Number(v) || 0), 0)
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const pickStyle = (lid) => {
    const s = info.lines.find((l) => String(l.order_line) === String(lid))
    const remaining = Math.max(s.quantity - s.planned, 0)
    setForm((f) => ({ ...f, order_line: lid, quantity: remaining, sizes: splitEvenly(remaining, s.sizes || []), colourway: s.colourways?.[0] || '' }))
  }

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const { data } = await api.post('/production-orders/', {
        order, order_line: form.order_line, quantity: form.quantity, line: form.line, smv: form.smv, colourway: form.colourway,
        planned_start: form.planned_start, planned_end: form.planned_end || undefined, notes: form.notes,
        sizes: Object.fromEntries(Object.entries(form.sizes).filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v)])),
      })
      navigate(`/production/${data.id}`, { replace: true })
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }

  return (
    <>
      <div className="crumbs small"><Link to="/production">Production plan</Link> / New</div>
      <div className="page-head"><h1>Plan production</h1></div>
      {error && <div className="error">{error}</div>}
      <form onSubmit={submit} className="order-layout">
        <div>
          <div className="card">
            <h2>Order & style</h2>
            <div className="form-grid">
              <label className="field"><span>Confirmed order *</span>
                <select value={order} onChange={(e) => { setOrder(e.target.value); setInfo(null); set('order_line', '') }} required>
                  <option value="">— choose —</option>
                  {orders.map((o) => <option key={o.id} value={o.id}>{o.oc_no} · {o.buyer_name} · ships {fmtDate(o.ship_date)}</option>)}
                </select></label>
              {info && <label className="field"><span>Style *</span>
                <select value={form.order_line} onChange={(e) => pickStyle(e.target.value)} required>
                  <option value="">— choose —</option>
                  {info.lines.map((l) => <option key={l.order_line} value={l.order_line}>{l.style_no} · {pcs(l.quantity)} pcs ({pcs(l.planned)} planned)</option>)}
                </select></label>}
              {style?.colourways?.length > 0 && <label className="field"><span>Colourway</span>
                <select value={form.colourway} onChange={(e) => set('colourway', e.target.value)}>{style.colourways.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>}
            </div>
            {style && !style.production_approved && <p className="small warn-text">PP sample for {style.style_no} is not approved yet.</p>}
            {style && !style.tech_pack && <p className="small warn-text">No released tech pack for {style.style_no} — enter sizes by hand.</p>}
          </div>
          {style && (
            <div className="card">
              <div className="card-head"><h2>Quantity by size</h2>
                <button type="button" className="secondary small-btn" onClick={() => set('sizes', splitEvenly(Number(form.quantity) || 0, sizeList))}>Split evenly</button></div>
              <div className="form-grid">
                <label className="field"><span>Pieces to make *</span><input type="number" min="1" value={form.quantity} onChange={(e) => set('quantity', e.target.value)} required /></label>
              </div>
              <div className="size-grid">
                {sizeList.map((s) => (
                  <label key={s} className="field"><span>{s}</span>
                    <input className="num" type="number" min="0" value={form.sizes[s] ?? ''} onChange={(e) => set('sizes', { ...form.sizes, [s]: e.target.value })} /></label>
                ))}
                {!style.tech_pack && <button type="button" className="secondary small-btn" onClick={() => { const s = window.prompt('Size name'); if (s) set('sizes', { ...form.sizes, [s]: 0 }) }}>+ Size</button>}
              </div>
              <p className={`small ${sizeSum === Number(form.quantity) ? 'pos' : 'neg'}`}>Sizes add up to {pcs(sizeSum)}{sizeSum !== Number(form.quantity) && ` — must be ${pcs(form.quantity)}`}.</p>
            </div>
          )}
        </div>
        <aside>
          <div className="card">
            <h2>Line & dates</h2>
            <label className="field"><span>Sewing line *</span>
              <select value={form.line} onChange={(e) => set('line', e.target.value)} required>
                <option value="">— choose —</option>
                {lines.map((l) => <option key={l.id} value={l.id}>{l.name} · {l.operators} ops · {Number(l.efficiency_pct)}%</option>)}
              </select></label>
            <label className="field"><span>SMV — minutes per garment *</span><input type="number" min="0.5" step="0.1" value={form.smv} onChange={(e) => set('smv', e.target.value)} required /></label>
            <label className="field"><span>Start *</span><input type="date" value={form.planned_start} onChange={(e) => set('planned_start', e.target.value)} required /></label>
            <label className="field"><span>End (leave empty to use the suggestion)</span><input type="date" value={form.planned_end} onChange={(e) => set('planned_end', e.target.value)} /></label>
            {cap?.daily_target > 0 && (
              <dl className="summary">
                <div><dt>Line target</dt><dd>{pcs(cap.daily_target)} pcs/day</dd></div>
                {cap.working_days && <div><dt>Working days</dt><dd>{cap.working_days}</dd></div>}
                {cap.suggested_end && <div className="sub"><dt>Suggested end</dt><dd className={info?.ship_date && cap.suggested_end > info.ship_date ? 'neg' : ''}>{fmtDate(cap.suggested_end)}</dd></div>}
                {info?.ship_date && <div><dt>Ships</dt><dd>{fmtDate(info.ship_date)}</dd></div>}
              </dl>
            )}
            <div className="form-actions"><button type="submit" disabled={busy || !style || sizeSum !== Number(form.quantity)}>{busy ? 'Planning…' : 'Create work order'}</button></div>
          </div>
        </aside>
      </form>
    </>
  )
}

// ---------------------------------------------------------------- work order

function WorkOrder({ id }) {
  const { canManage } = useAuth()
  const [wo, setWo] = useState(null)
  const [stage, setStage] = useState('cutting')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)

  const load = useCallback(() => api.get(`/production-orders/${id}/`).then((r) => {
    setWo(r.data)
    const p = r.data.progress
    setStage(p.cut < r.data.quantity ? 'cutting' : p.wip_sewing > 0 ? 'sewing' : 'finishing')
  }).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])

  if (!wo) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => wo.allowed_actions.includes(a)
  const p = wo.progress
  const act = async (action, body = {}) => {
    setBusy(true); setError('')
    try { const { data } = await api.post(`/production-orders/${id}/${action}/`, body); setWo(data); setDialog(null) } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const removeEntry = async (entry) => {
    if (!window.confirm(`Delete the ${entry.stage_label.toLowerCase()} entry of ${fmtDate(entry.date)} (${pcs(entry.quantity)} pcs)?`)) return
    try { await api.delete(`/production-entries/${entry.id}/`); load() } catch (err) { setError(errorMessage(err)) }
  }

  return (
    <>
      <div className="crumbs small"><Link to="/production">Production plan</Link> / {wo.wo_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{wo.style_no} · {pcs(wo.quantity)} pcs <WOBadge status={wo.status} /></h1>
          <p className="muted">{wo.wo_no} · {wo.style_name}{wo.colourway && ` · ${wo.colourway}`} · <Link to={`/orders/${wo.order}`}>{wo.oc_no}</Link> {wo.buyer_name} · {wo.line_name} · SMV {Number(wo.smv)}
            {wo.tech_pack && <> · <Link to={`/tech-packs/${wo.tech_pack}`}>{wo.tp_no}</Link></>}</p>
        </div>
        <div className="actions">
          {wo.status === 'in_progress' && <Link className="button secondary" to={`/quality/inline?wo=${wo.id}`}>Inline QC check</Link>}
          {['in_progress', 'completed'].includes(wo.status) && p.finished >= 2 && <Link className="button secondary" to={`/quality/final/new?wo=${wo.id}`}>Final inspection</Link>}
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')} disabled={busy}>Cancel</button>}
          {can('complete') && <button className="secondary" onClick={() => setDialog('complete')} disabled={busy}>Close work order</button>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {wo.warnings.length > 0 && <div className="notice warn block"><ul>{wo.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>}
      {wo.status === 'completed' && <div className="notice ok">Completed{wo.close_reason && `: ${wo.close_reason}`}. {pcs(p.finished)} pcs finished.</div>}

      <div className="wo-kpis">
        <div className="card kpi"><div className="muted small">Finished</div><div className="kpi-value">{p.percent_done}%</div><div className="small muted">{pcs(p.finished)} of {pcs(wo.quantity)}</div></div>
        <div className="card kpi"><div className="muted small">Waiting for sewing</div><div className="kpi-value">{pcs(p.wip_sewing)}</div><div className="small muted">cut, not sewn</div></div>
        <div className="card kpi"><div className="muted small">Waiting for finishing</div><div className="kpi-value">{pcs(p.wip_finishing)}</div><div className="small muted">sewn, not finished</div></div>
        <div className="card kpi"><div className="muted small">Rejects</div><div className={`kpi-value ${p.sewing_rejected + p.finishing_rejected ? 'neg' : ''}`}>{pcs(p.sewing_rejected + p.finishing_rejected)}</div>
          <div className="small muted">{wo.progress.sewn ? `${((p.sewing_rejected / (p.sewn + p.sewing_rejected)) * 100).toFixed(1)}% at sewing` : '—'}</div></div>
      </div>

      <div className="order-layout">
        <div>
          <div className="card">
            <h2>Progress</h2>
            <StageBars quantity={wo.quantity} progress={p} />
            <p className="muted small">Plan: {fmtDate(wo.planned_start)} – {fmtDate(wo.planned_end)} · line target {pcs(wo.capacity.daily_target)} pcs/day · ships {fmtDate(wo.ship_date)}</p>
          </div>
          <div className="card">
            <h2>Sizes</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Size</th>{wo.size_order.map((s) => <th key={s} className="num">{s}</th>)}<th className="num">Total</th></tr></thead>
                <tbody>
                  <tr><td>Planned</td>{wo.size_order.map((s) => <td key={s} className="num">{pcs(wo.sizes[s])}</td>)}<td className="num"><b>{pcs(wo.quantity)}</b></td></tr>
                  <tr><td>Cut</td>{wo.size_order.map((s) => {
                    const c = p.cut_sizes[s] || 0
                    return <td key={s} className={`num ${c >= wo.sizes[s] ? 'pos' : ''}`}>{pcs(c)}</td>
                  })}<td className="num"><b>{pcs(p.cut)}</b></td></tr>
                </tbody>
              </table>
            </div>
          </div>
          {can('record') && <RecordOutput wo={wo} stage={stage} setStage={setStage} onSaved={setWo} />}
          <div className="card">
            <h2>Output log</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Date</th><th>Stage</th><th className="num">Good</th><th className="num">Rejected</th><th>Details</th><th>By</th>{canManage && <th />}</tr></thead>
                <tbody>
                  {wo.entries.length === 0 && <tr><td colSpan={7} className="muted center">No output yet. Start with cutting.</td></tr>}
                  {wo.entries.map((e) => (
                    <tr key={e.id}>
                      <td>{fmtDate(e.date)}</td>
                      <td><span className={`badge badge-st-${e.stage}`}>{e.stage_label}</span></td>
                      <td className="num">{pcs(e.quantity)}</td>
                      <td className={`num ${e.rejected ? 'neg' : 'muted'}`}>{e.rejected || '—'}</td>
                      <td className="small wrap">{e.stage === 'cutting' ? Object.entries(e.sizes).map(([s, v]) => `${s}: ${v}`).join(' · ') : e.line_name}
                        {e.lay_no && ` · ${e.lay_no}`}{e.fabric_used && ` · ${e.fabric_used} fabric`}{e.remarks && <div className="muted">{e.remarks}</div>}</td>
                      <td className="small">{e.entered_by_name}</td>
                      {canManage && <td>{['planned', 'in_progress'].includes(wo.status) && <button className="link" onClick={() => removeEntry(e)} aria-label="Delete entry">✕</button>}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <History items={wo.history.filter((h) => !h.action.endsWith('_recorded'))} />
        </div>
        <aside>
          <div className="card">
            <h2>Materials</h2>
            {!wo.materials.requirement ? <p className="muted small">No material requirement for this order yet.</p> : (
              <>
                <p className="small"><Link to={`/allocation/${wo.materials.requirement}`}>{wo.materials.mr_no}</Link> — issued to production:</p>
                <dl className="summary">
                  {wo.materials.lines.map((m) => (
                    <div key={m.description}><dt>{m.description}</dt>
                      <dd className={Number(m.issued_qty) >= Number(m.required_qty) ? 'pos' : Number(m.issued_qty) > 0 ? 'warn-text' : 'muted'}>{qty(m.issued_qty)} / {qty(m.required_qty, m.unit)}</dd></div>
                  ))}
                </dl>
              </>
            )}
          </div>
        </aside>
      </div>

      {dialog === 'cancel' && <ReasonDialog title={`Cancel ${wo.wo_no}?`} label="Reason" button="Cancel work order" tone="danger" busy={busy} onClose={() => setDialog(null)} onConfirm={(r) => act('cancel', { reason: r })} />}
      {dialog === 'complete' && <ReasonDialog title={`Close ${wo.wo_no}?`} text={p.finished < wo.quantity ? `Only ${pcs(p.finished)} of ${pcs(wo.quantity)} pcs are finished.` : 'All pieces are finished.'}
        label="Reason" required={p.finished < wo.quantity} button="Close work order" busy={busy} onClose={() => setDialog(null)} onConfirm={(r) => act('complete', { reason: r })} />}
    </>
  )
}

function RecordOutput({ wo, stage, setStage, onSaved }) {
  const lines = useOptions('/production-lines/', { company: wo.company, is_active: true })
  const [form, setForm] = useState(() => ({ date: todayStr(), sizes: {}, quantity: '', rejected: '', line: wo.line, lay_no: '', fabric_used: '', remarks: '' }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const p = wo.progress
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const available = stage === 'sewing' ? p.wip_sewing : stage === 'finishing' ? p.wip_finishing : null
  const limit = (s) => Math.floor(wo.sizes[s] * (1 + Number(wo.cut_allowance_pct) / 100)) - (p.cut_sizes[s] || 0)
  const cutTotal = Object.values(form.sizes).reduce((a, v) => a + (Number(v) || 0), 0)

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    const body = { stage, date: form.date, remarks: form.remarks, rejected: Number(form.rejected) || 0 }
    if (stage === 'cutting') Object.assign(body, { sizes: Object.fromEntries(Object.entries(form.sizes).filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v)])), lay_no: form.lay_no, fabric_used: form.fabric_used || null })
    else Object.assign(body, { quantity: Number(form.quantity) || 0, line: stage === 'sewing' ? form.line : null })
    try {
      const { data } = await api.post(`/production-orders/${wo.id}/entries/`, body)
      onSaved(data)
      setForm((f) => ({ ...f, sizes: {}, quantity: '', rejected: '', lay_no: '', fabric_used: '', remarks: '' }))
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <form className="card record-card" onSubmit={submit}>
      <div className="card-head">
        <h2>Record output</h2>
        <div className="seg" role="tablist">
          {STAGES.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={stage === k} className={stage === k ? 'on' : ''} onClick={() => setStage(k)}>{l}</button>)}
        </div>
      </div>
      <div className="form-grid">
        <label className="field"><span>Date</span><input type="date" value={form.date} max={todayStr()} onChange={(e) => set('date', e.target.value)} required /></label>
        {stage === 'cutting' && <>
          <label className="field"><span>Lay / bundle no.</span><input value={form.lay_no} onChange={(e) => set('lay_no', e.target.value)} /></label>
          <label className="field"><span>Fabric used</span><input type="number" min="0" step="0.01" value={form.fabric_used} onChange={(e) => set('fabric_used', e.target.value)} /></label>
        </>}
        {stage !== 'cutting' && <>
          <label className="field"><span>Good pieces</span><input type="number" min="0" value={form.quantity} onChange={(e) => set('quantity', e.target.value)} /></label>
          <label className="field"><span>Rejected</span><input type="number" min="0" value={form.rejected} onChange={(e) => set('rejected', e.target.value)} /></label>
          {stage === 'sewing' && <label className="field"><span>Line</span><select value={form.line} onChange={(e) => set('line', Number(e.target.value))}>{lines.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>}
        </>}
      </div>
      {stage === 'cutting' && (
        <div className="size-grid">
          {wo.size_order.map((s) => (
            <label key={s} className="field"><span>{s} <small className="muted">(≤ {pcs(Math.max(limit(s), 0))})</small></span>
              <input className="num" type="number" min="0" max={Math.max(limit(s), 0)} value={form.sizes[s] ?? ''} onChange={(e) => set('sizes', { ...form.sizes, [s]: e.target.value })} aria-label={`Cut ${s}`} /></label>
          ))}
        </div>
      )}
      <label className="field"><span>Remarks</span><input value={form.remarks} onChange={(e) => set('remarks', e.target.value)} placeholder={stage === 'sewing' ? 'e.g. 2 operators absent' : ''} /></label>
      {error && <div className="error">{error}</div>}
      <div className="form-actions">
        <span className="muted small">{stage === 'cutting' ? `${pcs(cutTotal)} pcs in this lay` : `${pcs(available)} pcs waiting for ${stage}`}</span>
        <button type="submit" disabled={busy}>Save {labelOf(STAGES, stage).toLowerCase()} output</button>
      </div>
    </form>
  )
}
