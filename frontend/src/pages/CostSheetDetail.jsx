import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import DocBadge from '../components/merch/DocBadge'
import History from '../components/merch/History'
import { COST_CATEGORIES, costSummary, money, num } from '../components/merch/constants'
import { CATEGORIES, opts } from '../components/buyers/constants'

const HEADER = [
  { name: 'style_no', label: 'Style number', required: true },
  { name: 'style_name', label: 'Style name', required: true },
  { name: 'category', label: 'Category', type: 'select', options: opts(CATEGORIES), required: true },
  { name: 'fabric_composition', label: 'Fabric / composition' },
  { name: 'gsm', label: 'GSM', type: 'number' },
  { name: 'size_range', label: 'Size range' },
  { name: 'quantity', label: 'Costing quantity (pcs)', type: 'number' },
  { name: 'currency', label: 'Currency', required: true },
]
const PERCENTS = [
  { name: 'overhead_pct', label: 'Overhead %', type: 'number' },
  { name: 'margin_pct', label: 'Margin %', type: 'number' },
  { name: 'commission_pct', label: 'Agent commission %', type: 'number' },
]
const NEW_LINE = { category: 'fabric', description: '', unit: 'pc', consumption: '', rate: '', wastage_pct: '0' }

export default function CostSheetDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [sheet, setSheet] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  const apply = (data) => { setSheet(data); setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) }) }
  const load = useCallback(() => api.get(`/cost-sheets/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => sheet.allowed_actions.includes(a)
  const editable = can('edit')
  const sum = costSummary(form)
  const set = (name, v) => { setSaved(false); setForm((f) => ({ ...f, [name]: v })) }
  const setLine = (i, name, v) => { setSaved(false); setForm((f) => ({ ...f, lines: f.lines.map((l, j) => (j === i ? { ...l, [name]: v } : l)) })) }
  const addLine = () => set('lines', [...form.lines, { ...NEW_LINE }])
  const removeLine = (i) => set('lines', form.lines.filter((_, j) => j !== i))

  const save = async (e) => {
    e?.preventDefault()
    setBusy(true); setError('')
    try {
      const body = { ...form, gsm: form.gsm || null, quantity: form.quantity || 0,
        lines: form.lines.map((l) => ({ ...l, wastage_pct: l.wastage_pct || 0 })) }
      const { data } = await api.put(`/cost-sheets/${id}/`, body)
      apply(data); setSaved(true)
      return true
    } catch (err) { setError(errorMessage(err)); return false } finally { setBusy(false) }
  }

  const act = async (action) => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/cost-sheets/${id}/${action}/`)
      if (action === 'copy') navigate(`/costing/${data.id}`)
      else apply(data)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const approve = async () => { if (await save()) act('approve') }

  return (
    <>
      <div className="crumbs small"><Link to="/costing">Cost sheets</Link> / {sheet.cost_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{sheet.style_no} · {sheet.style_name} <DocBadge kind="cs" status={sheet.status} /></h1>
          <p className="muted">{sheet.cost_no} · <Link to={`/buyers/${sheet.buyer}`}>{sheet.buyer_name}</Link>
            {sheet.approved_by_name && <> · approved by {sheet.approved_by_name}</>}</p>
        </div>
        <div className="actions">
          {can('copy') && <button className="secondary" onClick={() => act('copy')} disabled={busy}>Copy</button>}
          {can('reopen') && <button className="secondary" onClick={() => act('reopen')} disabled={busy}>Reopen for changes</button>}
          {can('approve') && <button className="approve" onClick={approve} disabled={busy}>Save & approve</button>}
          {can('quote') && <Link className="button" to={`/quotations/new?buyer=${sheet.buyer}&cost_sheet=${sheet.id}`}>Create quotation →</Link>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {sheet.status === 'approved' && <div className="notice ok">Approved — this cost sheet can now be used on quotations. Copy it to make a revised costing.</div>}

      <form onSubmit={save} className="cost-layout">
        <div>
          <fieldset className="plain" disabled={!editable}>
            <div className="card">
              <h2>Style</h2>
              <div className="form-grid">
                {HEADER.map((f) => <FormField key={f.name} field={f} value={form[f.name]} onChange={set} />)}
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <div><h2>Cost per piece</h2><p className="muted small">Amount = consumption × rate × (1 + wastage %)</p></div>
                {editable && <button type="button" className="secondary" onClick={addLine}>+ Add line</button>}
              </div>
              <div className="table-wrap">
                <table className="cost-lines">
                  <thead><tr><th>Type</th><th>Description</th><th>Unit</th><th className="num">Consumption</th><th className="num">Rate</th><th className="num">Wastage %</th><th className="num">Amount</th><th /></tr></thead>
                  <tbody>
                    {form.lines.length === 0 && <tr><td colSpan={8} className="muted center">No cost lines yet. Start with the fabric.</td></tr>}
                    {form.lines.map((l, i) => (
                      <tr key={l.id ?? `n${i}`}>
                        <td><select value={l.category} onChange={(e) => setLine(i, 'category', e.target.value)} aria-label="Type">
                          {COST_CATEGORIES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></td>
                        <td><input value={l.description} onChange={(e) => setLine(i, 'description', e.target.value)} required aria-label="Description" /></td>
                        <td><input className="w-sm" value={l.unit} onChange={(e) => setLine(i, 'unit', e.target.value)} aria-label="Unit" /></td>
                        <td><input className="num" type="number" step="0.0001" min="0" value={l.consumption} onChange={(e) => setLine(i, 'consumption', e.target.value)} required aria-label="Consumption" /></td>
                        <td><input className="num" type="number" step="0.0001" min="0" value={l.rate} onChange={(e) => setLine(i, 'rate', e.target.value)} required aria-label="Rate" /></td>
                        <td><input className="num w-sm" type="number" step="0.01" min="0" max="100" value={l.wastage_pct} onChange={(e) => setLine(i, 'wastage_pct', e.target.value)} aria-label="Wastage %" /></td>
                        <td className="num">{num(sum.lines[i], 4)}</td>
                        <td>{editable && <button type="button" className="link" onClick={() => removeLine(i)} aria-label="Remove line">✕</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </fieldset>
          <History items={sheet.history} />
        </div>

        <aside className="card cost-summary">
          <h2>Price build-up</h2>
          <fieldset className="plain" disabled={!editable}>
            <div className="form-grid tight">
              {PERCENTS.map((f) => <FormField key={f.name} field={f} value={form[f.name]} onChange={set} />)}
            </div>
          </fieldset>
          <dl className="summary">
            <div><dt>Direct cost</dt><dd>{num(sum.direct, 4)}</dd></div>
            <div><dt>Overhead ({num(form.overhead_pct, 0)}%)</dt><dd>{num(sum.overhead, 4)}</dd></div>
            <div className="sub"><dt>Total cost</dt><dd>{num(sum.total, 4)}</dd></div>
            <div><dt>Margin ({num(form.margin_pct, 0)}%)</dt><dd>{num(sum.margin, 4)}</dd></div>
            <div><dt>Commission ({num(form.commission_pct, 1)}%)</dt><dd>{num(sum.commission, 4)}</dd></div>
          </dl>
          <div className="fob">
            <span>FOB price / piece</span>
            <strong>{money(sum.fob, form.currency)}</strong>
            {Number(form.quantity) > 0 && <small className="muted">× {Number(form.quantity).toLocaleString('en-IN')} pcs = {money(sum.fob * form.quantity, form.currency, 0)}</small>}
          </div>
          {editable && (
            <div className="form-actions">
              {saved && <span className="pos small">✓ Saved</span>}
              <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
            </div>
          )}
        </aside>
      </form>
    </>
  )
}
