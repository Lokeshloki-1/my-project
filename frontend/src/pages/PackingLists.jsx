import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { downloadFile, errorMessage } from '../api/client'
import ResourcePage from '../components/ResourcePage'
import useOptions from '../components/useOptions'
import History from '../components/merch/History'
import { pcs } from '../components/prod/constants'
import { fmtDate, fmtDateTime } from '../components/buyers/constants'

const todayStr = () => new Date().toISOString().slice(0, 10)
const METHODS = [['solid', 'Solid size, solid colour'], ['ratio', 'Ratio pack (assorted sizes)'], ['mixed', 'Mixed']]

export default function PackingLists() {
  const { id } = useParams()
  return id ? <PackingListDetail id={id === 'new' ? null : id} /> : <PLList />
}

function PLList() {
  const navigate = useNavigate()
  return (
    <ResourcePage
      title="Packing Lists"
      subtitle="Cartons per order — only pieces that passed final inspection can be packed"
      endpoint="/packing-lists/"
      readOnly
      headerExtra={<button onClick={() => navigate('/packing/new')}>+ New packing list</button>}
      onRowClick={(r) => navigate(`/packing/${r.id}`)}
      columns={[
        { key: 'pl_no', label: 'Packing list' },
        { key: 'oc_no', label: 'Order', render: (r) => <><b>{r.oc_no}</b><div className="muted small">{r.buyer_name} · PO {r.buyer_po_no}</div></> },
        { key: 'pack_date', label: 'Date', render: (r) => fmtDate(r.pack_date) },
        { key: 'total_cartons', label: 'Cartons', num: true },
        { key: 'total_pcs', label: 'Pcs', num: true, render: (r) => pcs(r.total_pcs) },
        { key: 'cbm', label: 'GW kg / CBM', num: true, render: (r) => <>{Number(r.gross_weight).toLocaleString('en-IN')}<div className="muted small">{r.cbm} m³</div></> },
        { key: 'shipment_no', label: 'Shipment', render: (r) => r.shipment ? <Link to={`/shipments/${r.shipment}`} onClick={(e) => e.stopPropagation()}>{r.shipment_no}</Link> : '—' },
        { key: 'status', label: 'Status', render: (r) => <span className={`badge badge-pl-${r.status}`}>{r.status_label}</span> },
      ]}
      fields={[]}
    />
  )
}

const blankGroup = (wo, from) => ({ production_order: wo?.production_order || '', colourway: wo?.colourway || '', from_carton: from, to_carton: from, sizes: {}, net_weight: '', gross_weight: '', length_cm: '58', width_cm: '38', height_cm: '28' })

function PackingListDetail({ id }) {
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [pl, setPl] = useState(null)
  const [form, setForm] = useState(() => (id ? null : { order: query.get('order') || '', pack_date: todayStr(), method: 'solid', shipping_marks: '', notes: '', groups: [] }))
  const [status, setStatus] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const orders = useOptions(id ? null : '/order-confirmations/', id ? null : { status: 'confirmed' })

  const apply = (data) => { setPl(data); setStatus(data.pack_status); setForm({ ...data, groups: data.groups.map((g) => ({ ...g })) }) }
  const load = useCallback(() => { if (id) api.get(`/packing-lists/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e))) }, [id])
  useEffect(() => { load() }, [load])
  // New list: what each style of the chosen order can still pack.
  const orderId = form?.order
  useEffect(() => {
    if (id || !orderId) return
    api.get('/packing-lists/pack-status/', { params: { order: orderId } }).then((r) => setStatus(r.data)).catch((e) => setError(errorMessage(e)))
  }, [id, orderId])

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const editable = !pl || pl.allowed_actions.includes('edit')
  const can = (a) => pl?.allowed_actions.includes(a)
  const set = (n, v) => setForm((f) => ({ ...f, [n]: v }))
  const setGroup = (i, patch) => set('groups', form.groups.map((g, j) => (j === i ? { ...g, ...patch } : g)))
  const sizesOf = (woId) => status.find((w) => String(w.production_order) === String(woId))?.sizes || []
  const nextCarton = form.groups.reduce((m, g) => Math.max(m, Number(g.to_carton) || 0), 0) + 1
  const addGroup = () => {
    const last = form.groups[form.groups.length - 1]
    const wo = status.find((s) => !last || s.production_order === Number(last.production_order)) || status[0]
    set('groups', [...form.groups, last ? { ...last, id: undefined, from_carton: nextCarton, to_carton: nextCarton, sizes: {} } : blankGroup(wo, 1)])
  }
  const g = (gr) => {
    const cartons = Math.max((Number(gr.to_carton) || 0) - (Number(gr.from_carton) || 0) + 1, 0)
    const per = Object.values(gr.sizes || {}).reduce((a, v) => a + (Number(v) || 0), 0)
    const cbm = (Number(gr.length_cm) * Number(gr.width_cm) * Number(gr.height_cm)) / 1e6
    return { cartons, per, total: cartons * per, nw: cartons * (Number(gr.net_weight) || 0), gw: cartons * (Number(gr.gross_weight) || 0), cbm: cartons * (cbm || 0) }
  }
  const sums = form.groups.reduce((a, gr) => { const x = g(gr); return { cartons: a.cartons + x.cartons, total: a.total + x.total, nw: a.nw + x.nw, gw: a.gw + x.gw, cbm: a.cbm + x.cbm } }, { cartons: 0, total: 0, nw: 0, gw: 0, cbm: 0 })
  const packingNow = (woId) => form.groups.filter((gr) => String(gr.production_order) === String(woId)).reduce((a, gr) => a + g(gr).total, 0)

  const save = async (finalize = false) => {
    setBusy(true); setError('')
    const body = {
      order: form.order, pack_date: form.pack_date, method: form.method, shipping_marks: form.shipping_marks, notes: form.notes,
      groups: form.groups.map((gr) => ({
        production_order: gr.production_order, colourway: gr.colourway, from_carton: Number(gr.from_carton), to_carton: Number(gr.to_carton),
        sizes: Object.fromEntries(Object.entries(gr.sizes || {}).filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v)])),
        net_weight: gr.net_weight, gross_weight: gr.gross_weight, length_cm: gr.length_cm, width_cm: gr.width_cm, height_cm: gr.height_cm,
      })),
    }
    try {
      let { data } = pl ? await api.put(`/packing-lists/${pl.id}/`, body) : await api.post('/packing-lists/', body)
      if (finalize) data = (await api.post(`/packing-lists/${data.id}/finalize/`)).data
      if (!pl) navigate(`/packing/${data.id}`, { replace: true })
      else apply(data)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const reopen = async () => { try { apply((await api.post(`/packing-lists/${pl.id}/reopen/`)).data) } catch (err) { setError(errorMessage(err)) } }

  return (
    <>
      <div className="crumbs small"><Link to="/packing">Packing lists</Link> / {pl ? pl.pl_no : 'New'}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{pl ? pl.pl_no : 'New packing list'} {pl && <span className={`badge badge-pl-${pl.status}`}>{pl.status_label}</span>}</h1>
          {pl && <p className="muted"><Link to={`/orders/${pl.order}`}>{pl.oc_no}</Link> · {pl.buyer_name} · PO {pl.buyer_po_no}{pl.shipment && <> · on <Link to={`/shipments/${pl.shipment}`}>{pl.shipment_no}</Link></>}</p>}
        </div>
        <div className="actions">
          {can('pdf') && <button className="secondary" onClick={() => downloadFile(`/packing-lists/${pl.id}/pdf/`, `${pl.pl_no}.pdf`)}>Download PDF</button>}
          {can('reopen') && <button className="secondary" onClick={reopen}>Reopen</button>}
          {editable && <button className="secondary" onClick={() => save(false)} disabled={busy}>Save draft</button>}
          {editable && <button className="approve" onClick={() => save(true)} disabled={busy || !form.groups.length}>Save & finalize</button>}
          {pl?.status === 'finalized' && !pl.shipment && <Link className="button" to={`/shipments/new?order=${pl.order}&pl=${pl.id}`}>Create shipment →</Link>}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {pl?.status === 'finalized' && <div className="notice ok">Finalized by {pl.finalized_by_name} on {fmtDateTime(pl.finalized_at)}.</div>}

      {status.length > 0 && (
        <div className="card">
          <h2>What can be packed</h2>
          <div className="table-wrap">
            <table className="cost-lines">
              <thead><tr><th>Style</th><th className="num">Finished</th><th className="num">Passed final inspection</th><th className="num">On other packing lists</th><th className="num">On this list</th><th className="num">Still packable</th></tr></thead>
              <tbody>{status.map((s) => {
                const now = packingNow(s.production_order)
                const left = s.packable != null ? s.packable - now : null
                return (
                  <tr key={s.production_order}>
                    <td><b>{s.style_no}</b><div className="muted small">{s.wo_no}{s.colourway && ` · ${s.colourway}`}</div></td>
                    <td className="num">{pcs(s.finished)}</td>
                    <td className={`num ${s.passed_inspection ? '' : 'neg'}`}>{s.passed_inspection ? pcs(s.passed_inspection) : 'Not inspected'}</td>
                    <td className="num">{s.packed != null ? pcs(s.packed) : '—'}</td>
                    <td className="num">{pcs(now)}</td>
                    <td className={`num ${left != null && left < 0 ? 'neg' : 'pos'}`}>{left != null ? pcs(left) : '—'}</td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
          <p className="muted small">Packable = the smaller of finished and passed-inspection pieces, minus what finalized packing lists already hold.</p>
        </div>
      )}

      <fieldset className="plain" disabled={!editable}>
        <div className="card">
          <div className="form-grid">
            {!pl ? <label className="field"><span>Confirmed order *</span>
              <select value={form.order} onChange={(e) => setForm((f) => ({ ...f, order: e.target.value, groups: [] }))} required>
                <option value="">— choose —</option>{orders.map((o) => <option key={o.id} value={o.id}>{o.oc_no} · {o.buyer_name} · PO {o.buyer_po_no}</option>)}
              </select></label> : <label className="field"><span>Order</span><input value={`${pl.oc_no} · ${pl.buyer_name}`} disabled /></label>}
            <label className="field"><span>Packing date</span><input type="date" value={form.pack_date} onChange={(e) => set('pack_date', e.target.value)} /></label>
            <label className="field"><span>Packing method</span><select value={form.method} onChange={(e) => set('method', e.target.value)}>{METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
            <label className="field full"><span>Shipping marks (printed on cartons)</span><textarea rows={4} value={form.shipping_marks} onChange={(e) => set('shipping_marks', e.target.value)} placeholder="Left empty: buyer, PO, style, carton no., Made in India" /></label>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h2>Cartons</h2>{editable && form.order && <button type="button" className="secondary small-btn" onClick={addGroup}>+ Add carton range</button>}</div>
          {form.groups.length === 0 ? <div className="empty-state">{form.order ? 'Add carton ranges: e.g. cartons 1–10, 24 pcs of size 6Y each.' : 'Choose the order first.'}</div> : (
            <div className="carton-groups">
              {form.groups.map((gr, i) => {
                const x = g(gr)
                const sizes = sizesOf(gr.production_order)
                return (
                  <div key={i} className="carton-group">
                    <div className="cg-head">
                      <label className="field"><span>Style</span>
                        <select value={gr.production_order} onChange={(e) => setGroup(i, { production_order: e.target.value, sizes: {}, colourway: status.find((w) => String(w.production_order) === e.target.value)?.colourway || '' })} aria-label="Work order">
                          <option value="">—</option>{status.map((w) => <option key={w.production_order} value={w.production_order}>{w.style_no} · {w.wo_no}</option>)}</select></label>
                      <label className="field"><span>Cartons</span><span className="range">
                        <input className="num" type="number" min="1" value={gr.from_carton} onChange={(e) => setGroup(i, { from_carton: e.target.value })} aria-label="From carton" />
                        <span>–</span>
                        <input className="num" type="number" min="1" value={gr.to_carton} onChange={(e) => setGroup(i, { to_carton: e.target.value })} aria-label="To carton" /></span></label>
                      <label className="field"><span>Colour</span><input value={gr.colourway} onChange={(e) => setGroup(i, { colourway: e.target.value })} /></label>
                      {editable && <button type="button" className="link" onClick={() => set('groups', form.groups.filter((_, j) => j !== i))} aria-label="Remove range">✕</button>}
                    </div>
                    <div className="cg-sizes">
                      <span className="muted small">Pcs per carton:</span>
                      {sizes.map((s) => (
                        <label key={s} className="size-in"><span>{s}</span><input className="num" type="number" min="0" value={gr.sizes?.[s] ?? ''} onChange={(e) => setGroup(i, { sizes: { ...gr.sizes, [s]: e.target.value } })} aria-label={`Pcs ${s}`} /></label>
                      ))}
                    </div>
                    <div className="cg-dims">
                      <label className="size-in"><span>NW kg</span><input className="num" type="number" min="0" step="0.01" value={gr.net_weight} onChange={(e) => setGroup(i, { net_weight: e.target.value })} aria-label="Net weight" /></label>
                      <label className="size-in"><span>GW kg</span><input className="num" type="number" min="0" step="0.01" value={gr.gross_weight} onChange={(e) => setGroup(i, { gross_weight: e.target.value })} aria-label="Gross weight" /></label>
                      <label className="size-in"><span>L cm</span><input className="num" type="number" min="1" value={gr.length_cm} onChange={(e) => setGroup(i, { length_cm: e.target.value })} aria-label="Length" /></label>
                      <label className="size-in"><span>W cm</span><input className="num" type="number" min="1" value={gr.width_cm} onChange={(e) => setGroup(i, { width_cm: e.target.value })} aria-label="Width" /></label>
                      <label className="size-in"><span>H cm</span><input className="num" type="number" min="1" value={gr.height_cm} onChange={(e) => setGroup(i, { height_cm: e.target.value })} aria-label="Height" /></label>
                      <span className="cg-sum">{x.cartons} ctns × {x.per} = <b>{pcs(x.total)} pcs</b> · {x.gw.toFixed(1)} kg · {x.cbm.toFixed(3)} m³</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          {form.groups.length > 0 && (
            <div className="pl-totals">
              <div><span>Cartons</span><b>{sums.cartons}</b></div><div><span>Pieces</span><b>{pcs(sums.total)}</b></div>
              <div><span>Net kg</span><b>{sums.nw.toFixed(2)}</b></div><div><span>Gross kg</span><b>{sums.gw.toFixed(2)}</b></div><div><span>CBM</span><b>{sums.cbm.toFixed(3)}</b></div>
            </div>
          )}
        </div>
      </fieldset>
      {pl && <History items={pl.history} />}
    </>
  )
}
