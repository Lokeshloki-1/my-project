import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import Modal from '../components/Modal'
import DevBadge from '../components/dev/DevBadge'
import History from '../components/merch/History'
import { fmtDate } from '../components/buyers/constants'

const STEPS = [['requested', 'Requested'], ['in_progress', 'In progress'], ['ready', 'Ready'], ['sent', 'Sent'], ['decision', 'Buyer decision']]
const ORDER = { requested: 0, in_progress: 1, ready: 2, sent: 3, approved: 4, approved_with_comments: 4, rejected: 4 }

export default function SampleDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [sample, setSample] = useState(null)
  const [tp, setTp] = useState(null)
  const [form, setForm] = useState(null)
  const [readings, setReadings] = useState({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)

  const apply = useCallback((data) => {
    setSample(data)
    setForm({ colourway: data.colourway, size: data.size, quantity: data.quantity, due_date: data.due_date || '', instructions: data.instructions })
    setReadings(Object.fromEntries(data.measurements.map((m) => [m.measurement, m.actual])))
  }, [])
  const load = useCallback(() => api.get(`/samples/${id}/`).then((r) => {
    apply(r.data)
    return api.get(`/tech-packs/${r.data.tech_pack}/`).then((t) => setTp(t.data))
  }).catch((e) => setError(errorMessage(e))), [id, apply])
  useEffect(() => { load() }, [load])

  if (!sample || !tp) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => sample.allowed_actions.includes(a)
  const editable = can('edit')
  const step = ORDER[sample.status]
  const decided = step === 4

  const run = async (fn, okText) => {
    setBusy(true); setError(''); setNotice('')
    try {
      const { data } = await fn()
      if (data.id !== sample.id) { navigate(`/samples/${data.id}`); return }
      apply(data); setDialog(null)
      if (okText) setNotice(okText)
    } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const act = (action, body = {}) => run(() => api.post(`/samples/${id}/${action}/`, body))
  const saveDetails = (e) => {
    e.preventDefault()
    run(() => api.patch(`/samples/${id}/`, { ...form, due_date: form.due_date || null }), 'Details saved')
  }
  const saveReadings = () => run(() => api.put(`/samples/${id}/measurements/`, {
    readings: Object.entries(readings).map(([measurement, actual]) => ({ measurement: Number(measurement), actual })),
  }), 'Measurements saved')

  // Live check while typing, same rule as the server: |actual − spec| ≤ tolerance.
  const specFor = (m) => m.values?.[sample.size]
  const check = (m) => {
    const actual = readings[m.id]
    const spec = specFor(m)
    if (actual === undefined || actual === '' || spec === undefined || spec === '') return null
    const dev = Number(actual) - Number(spec)
    return { dev, ok: Math.abs(dev) <= Number(m.tolerance) }
  }
  const checks = tp.measurements.map(check).filter(Boolean)
  const outCount = checks.filter((c) => !c.ok).length

  return (
    <>
      <div className="crumbs small"><Link to="/samples">Samples</Link> / {sample.sample_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{sample.style_no} · {sample.type_label} · round {sample.round} <DevBadge kind="smp" status={sample.status} /></h1>
          <p className="muted">{sample.sample_no} · <Link to={`/tech-packs/${sample.tech_pack}`}>{sample.tp_no} rev {sample.tp_revision}</Link> · {sample.buyer_name}
            {sample.previous_no && <> · after <Link to={`/samples/${sample.previous}`}>{sample.previous_no}</Link></>}</p>
        </div>
        <div className="actions">
          {can('start') && <button onClick={() => act('start')} disabled={busy}>Start making</button>}
          {can('mark_ready') && <button onClick={() => act('mark-ready')} disabled={busy}>Mark ready</button>}
          {can('send') && <button onClick={() => setDialog('send')} disabled={busy}>Send to buyer</button>}
          {can('decide') && <button className="approve" onClick={() => setDialog('decide')} disabled={busy}>Record buyer decision</button>}
          {can('resubmit') && <button onClick={() => act('resubmit')} disabled={busy}>Make next round →</button>}
          {sample.resubmission_id && <Link className="button secondary" to={`/samples/${sample.resubmission_id}`}>Next round →</Link>}
        </div>
      </div>

      <ol className="stepper card stepper-card sample-steps">
        {STEPS.map(([key, label], i) => {
          const state = i < step || (decided && i === 4) ? 'done' : i === step ? 'current' : 'todo'
          return (
            <li key={key} className={`step ${state} ${i === 4 && sample.status === 'rejected' ? 'failed' : ''}`}>
              <span className="step-btn"><span className="dot">{state === 'done' ? (sample.status === 'rejected' && i === 4 ? '✕' : '✓') : i + 1}</span>
                <span className="step-label">{i === 4 && decided ? sample.status_label : label}</span></span>
            </li>
          )
        })}
      </ol>

      {error && <div className="error">{error}</div>}
      {notice && <div className="notice ok">{notice}</div>}
      {sample.is_late && <div className="notice warn">Overdue — it was due on {fmtDate(sample.due_date)}.</div>}
      {sample.status === 'sent' && <div className="notice">Sent on {fmtDate(sample.sent_on)} by {sample.courier}{sample.tracking_no && <> · tracking {sample.tracking_no}</>}. Record the buyer’s comments when they arrive.</div>}
      {decided && (
        <div className={`notice ${sample.status === 'rejected' ? 'warn' : 'ok'}`}>
          <span><b>{sample.status_label}</b> on {fmtDate(sample.decided_on)}{sample.buyer_comments && <>: {sample.buyer_comments}</>}
            {sample.sample_type === 'pp' && sample.status !== 'rejected' && <> — the style is approved for production.</>}</span>
        </div>
      )}

      <div className="order-layout">
        <div>
          <div className="card">
            <div className="card-head">
              <div>
                <h2>Measurement check · size {sample.size || '—'}</h2>
                <p className="muted small">Measure the sample and enter the actual values. Out of tolerance shows in red.</p>
              </div>
              {checks.length > 0 && <span className={`badge ${outCount ? 'badge-smp-rejected' : 'badge-smp-approved'}`}>{outCount ? `${outCount} out of tolerance` : 'All within tolerance'}</span>}
            </div>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Code</th><th>Point of measure</th><th className="num">Spec</th><th className="num">Tol ±</th><th className="num">Actual</th><th className="num">Deviation</th><th>Result</th></tr></thead>
                <tbody>
                  {tp.measurements.map((m) => {
                    const c = check(m)
                    return (
                      <tr key={m.id} className={c && !c.ok ? 'row-bad' : ''}>
                        <td>{m.code}</td><td>{m.point}</td>
                        <td className="num">{specFor(m) ?? '—'}</td><td className="num">{m.tolerance}</td>
                        <td className="num">{can('measure')
                          ? <input className="num w-sm" type="number" step="0.1" value={readings[m.id] ?? ''} onChange={(e) => setReadings((r) => ({ ...r, [m.id]: e.target.value }))} aria-label={`Actual ${m.point}`} />
                          : readings[m.id] ?? '—'}</td>
                        <td className="num">{c ? `${c.dev > 0 ? '+' : ''}${c.dev.toFixed(1)}` : ''}</td>
                        <td>{c ? (c.ok ? <span className="pos">✓ OK</span> : <span className="neg">✕ Out</span>) : <span className="muted">—</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {can('measure') && <div className="form-actions"><button type="button" className="secondary" onClick={saveReadings} disabled={busy}>Save measurements</button></div>}
          </div>
          <History items={sample.history} />
        </div>

        <aside>
          <form className="card" onSubmit={saveDetails}>
            <h2>Details</h2>
            <fieldset className="plain" disabled={!editable}>
              <FormField field={{ name: 'colourway', label: 'Colourway', type: 'select', options: tp.colourways.map((c) => ({ value: c, label: c })) }} value={form.colourway} onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} />
              <FormField field={{ name: 'size', label: 'Size', type: 'select', options: tp.sizes.map((s) => ({ value: s, label: s })) }} value={form.size} onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} />
              <FormField field={{ name: 'quantity', label: 'Pieces', type: 'number' }} value={form.quantity} onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} />
              <FormField field={{ name: 'due_date', label: 'Due date', type: 'date' }} value={form.due_date} onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} />
              <FormField field={{ name: 'instructions', label: 'Instructions', type: 'textarea' }} value={form.instructions} onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} />
            </fieldset>
            {editable && <div className="form-actions"><button type="submit" className="secondary" disabled={busy}>Save details</button></div>}
            <dl className="summary">
              <div><dt>Requested</dt><dd>{fmtDate(sample.requested_on)}</dd></div>
              {sample.sent_on && <div><dt>Sent</dt><dd>{fmtDate(sample.sent_on)}</dd></div>}
              {sample.decided_on && <div><dt>Decision</dt><dd>{fmtDate(sample.decided_on)}</dd></div>}
            </dl>
          </form>
        </aside>
      </div>

      {dialog === 'send' && <SendDialog busy={busy} onClose={() => setDialog(null)} onSend={(body) => act('send', body)} warn={outCount > 0 ? `${outCount} measurement(s) are out of tolerance.` : ''} />}
      {dialog === 'decide' && <DecideDialog busy={busy} sample={sample} onClose={() => setDialog(null)} onDecide={(body) => act('decide', body)} />}
    </>
  )
}

function SendDialog({ busy, onClose, onSend, warn }) {
  const [form, setForm] = useState(() => ({ courier: 'DHL', tracking_no: '', sent_on: new Date().toISOString().slice(0, 10) }))
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  return (
    <Modal title="Send sample to buyer" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSend(form) }}>
        {warn && <div className="notice warn">{warn} Send anyway only if the buyer agreed.</div>}
        <div className="form-grid">
          <FormField field={{ name: 'courier', label: 'Courier', required: true }} value={form.courier} onChange={set} />
          <FormField field={{ name: 'tracking_no', label: 'Tracking number' }} value={form.tracking_no} onChange={set} />
          <FormField field={{ name: 'sent_on', label: 'Sent on', type: 'date' }} value={form.sent_on} onChange={set} />
        </div>
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy || !form.courier.trim()}>Mark as sent</button>
        </div></div>
      </form>
    </Modal>
  )
}

function DecideDialog({ busy, sample, onClose, onDecide }) {
  const [decision, setDecision] = useState('approved')
  const [comments, setComments] = useState('')
  const needsComments = decision !== 'approved'
  const options = [
    ['approved', 'Approved', 'The buyer accepted the sample as it is.'],
    ['approved_with_comments', 'Approved with comments', 'Accepted, with small changes to make in the next stage.'],
    ['rejected', 'Rejected', 'Another round is needed.'],
  ]
  return (
    <Modal title={`Buyer decision · ${sample.sample_no}`} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onDecide({ decision, comments: comments.trim() }) }}>
        <div className="choice-list" role="radiogroup">
          {options.map(([v, label, text]) => (
            <label key={v} className={`choice ${decision === v ? 'on' : ''} choice-${v}`}>
              <input type="radio" name="decision" value={v} checked={decision === v} onChange={() => setDecision(v)} />
              <span><b>{label}</b><small>{text}</small></span>
            </label>
          ))}
        </div>
        <label className="field" style={{ marginTop: 12 }}>
          <span>Buyer’s comments{needsComments ? ' *' : ''}</span>
          <textarea rows={4} value={comments} onChange={(e) => setComments(e.target.value)} required={needsComments} />
        </label>
        {sample.sample_type === 'pp' && decision !== 'rejected' && <p className="small pos">Approving this PP sample approves the style for production.</p>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className={decision === 'rejected' ? 'danger' : 'approve'} disabled={busy || (needsComments && !comments.trim())}>Save decision</button>
        </div></div>
      </form>
    </Modal>
  )
}
