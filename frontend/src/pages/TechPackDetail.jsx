import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import Modal from '../components/Modal'
import useOptions from '../components/useOptions'
import ChipInput from '../components/dev/ChipInput'
import DevBadge from '../components/dev/DevBadge'
import { BOM_CATEGORIES, SAMPLE_TYPES, SIZE_PRESETS } from '../components/dev/constants'
import History from '../components/merch/History'
import { CATEGORIES, fmtDate, fmtDateTime, labelOf, opts } from '../components/buyers/constants'

const SPEC = [
  { name: 'style_no', label: 'Style number', required: true },
  { name: 'style_name', label: 'Style name', required: true },
  { name: 'season', label: 'Season' },
  { name: 'category', label: 'Category', type: 'select', options: opts(CATEGORIES), required: true },
  { name: 'fabric_composition', label: 'Fabric / composition' },
  { name: 'gsm', label: 'GSM', type: 'number' },
  { name: 'description', label: 'Description', type: 'textarea', full: true },
  { name: 'construction', label: 'Construction details', type: 'textarea', full: true },
  { name: 'wash_care', label: 'Wash & care', type: 'textarea', full: true },
  { name: 'packing', label: 'Packing', type: 'textarea', full: true },
]
const TABS = [['spec', 'Spec'], ['measurements', 'Measurements'], ['bom', 'Bill of materials'], ['samples', 'Samples'], ['history', 'History']]

export default function TechPackDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tp, setTp] = useState(null)
  const [form, setForm] = useState(null)
  const [tab, setTab] = useState('spec')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [requesting, setRequesting] = useState(false)

  const apply = (data) => {
    setTp(data)
    setForm({ ...data, measurements: data.measurements.map((m) => ({ ...m, values: { ...m.values } })), bom: data.bom.map((b) => ({ ...b })) })
  }
  const load = useCallback(() => api.get(`/tech-packs/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])
  const sheets = useOptions(tp ? '/cost-sheets/' : null, tp ? { buyer: tp.buyer } : null)

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => tp.allowed_actions.includes(a)
  const editable = can('edit')
  const set = (name, v) => { setSaved(false); setForm((f) => ({ ...f, [name]: v })) }

  const save = async (e) => {
    e?.preventDefault()
    setBusy(true); setError('')
    try {
      const { data } = await api.put(`/tech-packs/${id}/`, {
        ...form, gsm: form.gsm || null, cost_sheet: form.cost_sheet || null,
        bom: form.bom.map((b) => ({ ...b, consumption: b.consumption === '' ? null : b.consumption })),
      })
      apply(data); setSaved(true)
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }
  const act = async (action) => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/tech-packs/${id}/${action}/`)
      if (action === 'revise') navigate(`/tech-packs/${data.id}`)
      else apply(data)
    } catch (err) {
      const missing = err.response?.data?.missing
      setError(missing ? `Complete these first:\n• ${missing.join('\n• ')}` : errorMessage(err))
    } finally { setBusy(false) }
  }
  const release = async () => { if (await save()) act('release') }

  return (
    <>
      <div className="crumbs small"><Link to="/tech-packs">Tech packs</Link> / {tp.tp_no} rev {tp.revision}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{tp.style_no} · {tp.style_name} <DevBadge kind="tp" status={tp.status} />
            {tp.production_approved && <span className="badge badge-tp-prod">Approved for production</span>}</h1>
          <p className="muted">{tp.tp_no} · revision {tp.revision} · <Link to={`/buyers/${tp.buyer}`}>{tp.buyer_name}</Link>{tp.season && <> · {tp.season}</>}</p>
        </div>
        <div className="actions">
          {can('revise') && <button className="secondary" onClick={() => act('revise')} disabled={busy}>New revision</button>}
          {can('release') && <button className="approve" onClick={release} disabled={busy}>Save & release</button>}
          {can('request_sample') && <button onClick={() => setRequesting(true)}>Request sample</button>}
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {tp.status === 'draft' && tp.missing_for_release.length > 0 && (
        <div className="step-missing"><b>Before release:</b> {tp.missing_for_release.join(' · ')}</div>
      )}
      {tp.status === 'released' && <div className="notice ok">Released by {tp.released_by_name} on {fmtDateTime(tp.released_at)}. Samples can be requested. To change it, make a new revision.</div>}
      {tp.status === 'superseded' && <div className="notice warn">This revision was replaced.&nbsp;{tp.next_revision_id && <Link to={`/tech-packs/${tp.next_revision_id}`}>Open the latest revision →</Link>}</div>}

      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>
            {label}
            {key === 'measurements' && <span className="tab-count">{form.measurements.length}</span>}
            {key === 'bom' && <span className="tab-count">{form.bom.length}</span>}
            {key === 'samples' && <span className="tab-count">{tp.sample_count}</span>}
          </button>
        ))}
      </div>

      <form className="card tab-panel" onSubmit={save}>
        <fieldset className="plain" disabled={!editable}>
          {tab === 'spec' && (
            <>
              <div className="form-grid">
                {SPEC.slice(0, 6).map((f) => <FormField key={f.name} field={f} value={form[f.name]} onChange={set} />)}
                <FormField field={{ name: 'cost_sheet', label: 'Cost sheet', type: 'select', options: sheets.map((s) => ({ value: s.id, label: `${s.cost_no} · ${s.style_no}` })) }}
                  value={form.cost_sheet} onChange={set} />
              </div>
              <ChipInput label="Colourways" value={form.colourways} onChange={(v) => set('colourways', v)} disabled={!editable} placeholder="Type a colour and press Enter" />
              <div className="form-grid">{SPEC.slice(6).map((f) => <FormField key={f.name} field={f} value={form[f.name]} onChange={set} />)}</div>
            </>
          )}
          {tab === 'measurements' && <MeasurementChart form={form} set={set} editable={editable} />}
          {tab === 'bom' && <BomTable bom={form.bom} set={(v) => set('bom', v)} editable={editable} />}
        </fieldset>
        {tab === 'samples' && <TechPackSamples tp={tp} onRequest={can('request_sample') ? () => setRequesting(true) : null} />}
        {tab === 'history' && <History items={tp.history} />}
        {editable && ['spec', 'measurements', 'bom'].includes(tab) && (
          <div className="form-actions">
            {saved && <span className="pos small">✓ Saved</span>}
            <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save tech pack'}</button>
          </div>
        )}
        {!editable && ['spec', 'measurements', 'bom'].includes(tab) && <p className="muted small">This tech pack is {tp.status_label.toLowerCase()} and can’t be edited.</p>}
      </form>

      {requesting && <RequestSample tp={tp} onClose={() => setRequesting(false)} onCreated={(s) => navigate(`/samples/${s.id}`)} />}
    </>
  )
}

function MeasurementChart({ form, set, editable }) {
  const sizes = form.sizes
  const rows = form.measurements
  const setRow = (i, patch) => set('measurements', rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const setValue = (i, size, v) => setRow(i, { values: { ...rows[i].values, [size]: v } })
  const setSizes = (next) => {
    set('sizes', next)
    if (form.base_size && !next.includes(form.base_size)) set('base_size', '')
  }
  return (
    <>
      <div className="size-row">
        <ChipInput label="Sizes (columns)" value={sizes} onChange={setSizes} disabled={!editable} placeholder="e.g. S, M, L" />
        {editable && (
          <div className="presets">
            <span className="muted small">Presets:</span>
            {Object.entries(SIZE_PRESETS).map(([name, list]) => <button key={name} type="button" className="chip" onClick={() => setSizes(list)}>{name}</button>)}
          </div>
        )}
        <label className="field base-size">
          <span>Base (sample) size</span>
          <select value={form.base_size || ''} onChange={(e) => set('base_size', e.target.value)}>
            <option value="">—</option>
            {sizes.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>
      <p className="muted small">Measurements in cm. Tolerance is ± and is used to check sample measurements.</p>
      <div className="table-wrap">
        <table className="cost-lines spec-chart">
          <thead>
            <tr><th>Code</th><th>Point of measure</th><th className="num">Tol ±</th>
              {sizes.map((s) => <th key={s} className={`num ${s === form.base_size ? 'base' : ''}`}>{s}</th>)}<th /></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={sizes.length + 4} className="muted center">No points of measure yet.</td></tr>}
            {rows.map((r, i) => (
              <tr key={r.id ?? `n${i}`}>
                <td><input className="w-xs" value={r.code} onChange={(e) => setRow(i, { code: e.target.value })} aria-label="Code" /></td>
                <td><input className="pom" value={r.point} onChange={(e) => setRow(i, { point: e.target.value })} required aria-label="Point of measure" /></td>
                <td><input className="num w-xs" type="number" step="0.1" min="0" value={r.tolerance} onChange={(e) => setRow(i, { tolerance: e.target.value })} aria-label="Tolerance" /></td>
                {sizes.map((s) => (
                  <td key={s} className={s === form.base_size ? 'base' : ''}>
                    <input className="num w-sm" type="number" step="0.1" min="0" value={r.values[s] ?? ''} onChange={(e) => setValue(i, s, e.target.value)} aria-label={`${r.point} ${s}`} />
                  </td>
                ))}
                <td>{editable && <button type="button" className="link" onClick={() => set('measurements', rows.filter((_, j) => j !== i))} aria-label="Remove">✕</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editable && <button type="button" className="secondary" style={{ marginTop: 10 }}
        onClick={() => set('measurements', [...rows, { code: String.fromCharCode(65 + rows.length), point: '', tolerance: '1', values: {} }])}>+ Add point of measure</button>}
    </>
  )
}

function BomTable({ bom, set, editable }) {
  const setRow = (i, patch) => set(bom.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const input = (r, i, key, extra = {}) => <input value={r[key] ?? ''} onChange={(e) => setRow(i, { [key]: e.target.value })} aria-label={key} {...extra} />
  return (
    <>
      <div className="table-wrap">
        <table className="cost-lines">
          <thead><tr><th>Type</th><th>Description</th><th>Supplier</th><th>Colour</th><th>Placement</th><th className="num">Consumption</th><th>Unit</th><th /></tr></thead>
          <tbody>
            {bom.length === 0 && <tr><td colSpan={8} className="muted center">No materials yet. Start with the main fabric.</td></tr>}
            {bom.map((r, i) => (
              <tr key={r.id ?? `n${i}`}>
                <td><select value={r.category} onChange={(e) => setRow(i, { category: e.target.value })} aria-label="Type">
                  {BOM_CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
                <td>{input(r, i, 'description', { required: true, className: 'pom' })}</td>
                <td>{input(r, i, 'supplier')}</td>
                <td>{input(r, i, 'colour', { className: 'w-md' })}</td>
                <td>{input(r, i, 'placement')}</td>
                <td>{input(r, i, 'consumption', { type: 'number', step: '0.0001', min: '0', className: 'num w-md' })}</td>
                <td>{input(r, i, 'unit', { className: 'w-xs' })}</td>
                <td>{editable && <button type="button" className="link" onClick={() => set(bom.filter((_, j) => j !== i))} aria-label="Remove">✕</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editable && <button type="button" className="secondary" style={{ marginTop: 10 }}
        onClick={() => set([...bom, { category: bom.length ? 'trim' : 'fabric', description: '', supplier: '', colour: '', placement: '', consumption: '', unit: '' }])}>+ Add material</button>}
    </>
  )
}

function TechPackSamples({ tp, onRequest }) {
  const navigate = useNavigate()
  const samples = useOptions('/samples/', { tech_pack: tp.id })
  return (
    <>
      <div className="card-head">
        <h2>Samples from this revision</h2>
        {onRequest && <button type="button" onClick={onRequest}>Request sample</button>}
      </div>
      {samples.length === 0 ? <div className="empty-state">No samples yet.{tp.status === 'draft' && ' Release the tech pack first.'}</div> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Sample</th><th>Type</th><th>Round</th><th>Colour / size</th><th>Due</th><th>Status</th></tr></thead>
            <tbody>
              {samples.map((s) => (
                <tr key={s.id} className="clickable" onClick={() => navigate(`/samples/${s.id}`)}>
                  <td><Link to={`/samples/${s.id}`}>{s.sample_no}</Link></td>
                  <td>{s.type_label}</td><td>{s.round}</td><td>{s.colourway} · {s.size}</td>
                  <td className={s.is_late ? 'neg' : ''}>{fmtDate(s.due_date)}</td>
                  <td><DevBadge kind="smp" status={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function RequestSample({ tp, onClose, onCreated }) {
  const [form, setForm] = useState(() => ({
    sample_type: 'proto', colourway: tp.colourways[0] || '', size: tp.base_size || '', quantity: 1,
    requested_on: new Date().toISOString().slice(0, 10), due_date: '', instructions: '',
  }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (name, v) => setForm((f) => ({ ...f, [name]: v }))
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const { data } = await api.post('/samples/', { ...form, tech_pack: tp.id, due_date: form.due_date || null })
      onCreated(data)
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }
  return (
    <Modal title={`Request sample · ${tp.style_no}`} onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="form-grid">
          <FormField field={{ name: 'sample_type', label: 'Sample type', type: 'select', options: opts(SAMPLE_TYPES), required: true }} value={form.sample_type} onChange={set} />
          <FormField field={{ name: 'colourway', label: 'Colourway', type: 'select', options: tp.colourways.map((c) => ({ value: c, label: c })) }} value={form.colourway} onChange={set} />
          <FormField field={{ name: 'size', label: 'Size', type: 'select', options: tp.sizes.map((s) => ({ value: s, label: s })) }} value={form.size} onChange={set} />
          <FormField field={{ name: 'quantity', label: 'Pieces', type: 'number', required: true }} value={form.quantity} onChange={set} />
          <FormField field={{ name: 'requested_on', label: 'Requested on', type: 'date', required: true }} value={form.requested_on} onChange={set} />
          <FormField field={{ name: 'due_date', label: 'Due date', type: 'date' }} value={form.due_date} onChange={set} />
          <FormField field={{ name: 'instructions', label: 'Instructions for the sampling room', type: 'textarea', full: true }} value={form.instructions} onChange={set} />
        </div>
        <p className="muted small">Type: {labelOf(SAMPLE_TYPES, form.sample_type)}. An approved PP sample approves the style for production.</p>
        {error && <div className="error">{error}</div>}
        <div className="modal-foot"><span /><div>
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy}>{busy ? 'Requesting…' : 'Request sample'}</button>
        </div></div>
      </form>
    </Modal>
  )
}
