import { money, num } from './constants'

/**
 * Style lines of a quotation or order. Each line comes from an approved cost sheet;
 * the price defaults to the cost sheet's FOB price and is flagged when below cost.
 */
export default function DocLines({ lines, onChange, editable, currency, sheets }) {
  const sheetById = Object.fromEntries((sheets || []).map((s) => [String(s.id), s]))
  const setLine = (i, patch) => onChange(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))

  const pickSheet = (i, id) => {
    const s = sheetById[id]
    if (!s) return
    setLine(i, {
      cost_sheet: s.id, cost_no: s.cost_no, style_no: s.style_no, description: s.style_name,
      unit_price: s.fob_price, cost_fob_price: s.fob_price, cost_total_cost: s.total_cost,
    })
  }
  const add = () => onChange([...lines, { cost_sheet: '', style_no: '', description: '', quantity: '', unit_price: '' }])
  const total = lines.reduce((a, l) => a + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0)
  const pcs = lines.reduce((a, l) => a + (Number(l.quantity) || 0), 0)

  return (
    <>
      <div className="table-wrap">
        <table className="cost-lines">
          <thead>
            <tr><th>Cost sheet</th><th>Style</th><th>Description</th><th className="num">Quantity (pcs)</th><th className="num">Price / pc</th><th className="num">Amount</th><th /></tr>
          </thead>
          <tbody>
            {lines.length === 0 && <tr><td colSpan={7} className="muted center">No styles yet.</td></tr>}
            {lines.map((l, i) => {
              const price = Number(l.unit_price) || 0
              const below = l.cost_total_cost != null && l.unit_price !== '' && price < Number(l.cost_total_cost)
              const under = l.cost_fob_price != null && price < Number(l.cost_fob_price)
              return (
                <tr key={l.id ?? `n${i}`}>
                  <td>
                    {editable ? (
                      <select value={l.cost_sheet ?? ''} onChange={(e) => pickSheet(i, e.target.value)} required aria-label="Cost sheet">
                        <option value="">— choose —</option>
                        {(sheets || []).map((s) => <option key={s.id} value={s.id}>{s.cost_no} · {s.style_no} · {money(s.fob_price, s.currency)}</option>)}
                      </select>
                    ) : <span className="muted">{l.cost_no}</span>}
                  </td>
                  <td>{editable ? <input className="w-md" value={l.style_no} onChange={(e) => setLine(i, { style_no: e.target.value })} aria-label="Style" /> : <b>{l.style_no}</b>}</td>
                  <td>{editable ? <input value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} aria-label="Description" /> : l.description}</td>
                  <td className="num">{editable ? <input className="num w-md" type="number" min="1" step="1" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} required aria-label="Quantity" /> : Number(l.quantity).toLocaleString('en-IN')}</td>
                  <td className="num">
                    {editable ? <input className="num w-md" type="number" min="0" step="0.01" value={l.unit_price} onChange={(e) => setLine(i, { unit_price: e.target.value })} required aria-label="Price per piece" /> : num(l.unit_price)}
                    {l.cost_fob_price != null && (
                      <small className={below ? 'neg' : under ? 'warn-text' : 'muted'}>
                        {below ? `Below cost (${num(l.cost_total_cost)})` : `FOB ${num(l.cost_fob_price)}`}
                      </small>
                    )}
                  </td>
                  <td className="num">{num(price * (Number(l.quantity) || 0))}</td>
                  <td>{editable && <button type="button" className="link" onClick={() => onChange(lines.filter((_, j) => j !== i))} aria-label="Remove style">✕</button>}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr><td colSpan={3}>{editable && <button type="button" className="secondary" onClick={add}>+ Add style</button>}</td>
              <td className="num"><b>{pcs.toLocaleString('en-IN')}</b></td><td /><td className="num"><b>{money(total, currency)}</b></td><td /></tr>
          </tfoot>
        </table>
      </div>
      {editable && sheets && sheets.length === 0 && <p className="muted small">This buyer has no approved cost sheets in {currency}. Create and approve one under Cost Sheets first.</p>}
    </>
  )
}
