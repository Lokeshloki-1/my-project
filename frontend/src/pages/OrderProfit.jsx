import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { money, num } from '../components/merch/constants'
import { pcs } from '../components/prod/constants'
import { fmtDate } from '../components/buyers/constants'
import { inr } from '../components/fin/constants'

const CATEGORIES = [['freight', 'Freight'], ['clearing', 'Clearing / CHA'], ['courier', 'Courier'], ['testing', 'Testing / inspection'],
  ['commission', 'Agent commission'], ['bank', 'Bank charges (local)'], ['other', 'Other']]
const todayStr = () => new Date().toISOString().slice(0, 10)
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(1)}%`)

export default function OrderProfit() {
  const { id } = useParams()
  return id ? <ProfitDetail id={id} /> : <ProfitList />
}

function ProfitList() {
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.get('/order-profit/').then((r) => setRows(r.data)).catch((e) => setError(errorMessage(e))) }, [])
  if (error) return <div className="error">{error}</div>
  if (!rows) return <div className="muted">Loading…</div>
  return (
    <>
      <div className="page-head"><div><h1>Order Profit</h1><p className="muted">Invoiced revenue minus materials, conversion, expenses and bank charges, plus exchange gain/loss — for what has shipped so far.</p></div></div>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Order</th><th className="num">Order value</th><th className="num">Shipped</th><th className="num">Invoiced (INR)</th><th className="num">Cost (INR)</th><th className="num">Profit (INR)</th><th className="num">Margin</th><th className="num">Planned</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="muted center">No confirmed orders.</td></tr>}
            {rows.map((r) => (
              <tr key={r.order} className="clickable" onClick={() => navigate(`/finance/profit/${r.order}`)}>
                <td><b>{r.oc_no}</b><div className="muted small">{r.buyer_name}</div></td>
                <td className="num">{money(r.order_value, r.currency, 0)}</td>
                <td className="num">{pct(r.shipped_share_pct)}<div className="muted small">{pcs(r.shipped_pcs)} / {pcs(r.ordered_pcs)} pcs</div></td>
                <td className="num">{Number(r.invoiced_inr) ? inr(r.invoiced_inr) : <span className="muted">not invoiced</span>}</td>
                <td className="num">{inr(r.costs.total_inr)}</td>
                <td className={`num ${Number(r.profit_inr) < 0 ? 'neg' : 'pos'}`}><b>{Number(r.invoiced_inr) ? inr(r.profit_inr) : '—'}</b>{r.warnings.length > 0 && <div className="small warn-text" title={r.warnings.join('\n')}>⚠ check</div>}</td>
                <td className={`num ${r.margin_pct != null && Number(r.margin_pct) < Number(r.planned_margin_pct) ? 'warn-text' : ''}`}>{pct(r.margin_pct)}</td>
                <td className="num muted">{pct(r.planned_margin_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function ProfitDetail({ id }) {
  const { canFinance } = useAuth()
  const [p, setP] = useState(null)
  const [error, setError] = useState('')
  const [exp, setExp] = useState(() => ({ date: todayStr(), category: 'freight', amount_inr: '', note: '' }))
  const load = useCallback(() => api.get(`/order-profit/${id}/`).then((r) => setP(r.data)).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])
  if (!p) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const addExpense = async (e) => {
    e.preventDefault(); setError('')
    try { await api.post('/order-expenses/', { ...exp, order: p.order }); setExp((x) => ({ ...x, amount_inr: '', note: '' })); load() } catch (err) { setError(errorMessage(err)) }
  }
  const removeExpense = async (x) => { try { await api.delete(`/order-expenses/${x.id}/`); load() } catch (err) { setError(errorMessage(err)) } }
  const rows = [
    ['Invoiced revenue', p.invoiced_inr, 'pos', `${money(p.invoiced, p.currency)} at ₹${p.invoice_rate ?? '—'}`],
    ['Materials (matched to shipped pcs)', -p.costs.materials_inr, '', `${inr(p.materials_issued_inr)} issued · ${inr(p.materials_in_wip_inr)} still in WIP`],
    ['Conversion (CMT, wash, print, testing, packing)', -p.costs.conversion_inr, '', 'Cost sheet rates × shipped pcs'],
    ['Order expenses', -p.costs.expenses_inr, '', Object.entries(p.costs.expenses_by_category).map(([k, v]) => `${k} ${inr(v)}`).join(' · ') || 'None'],
    ['Bank charges on receipts', -p.costs.bank_charges_inr, '', ''],
    ['Exchange gain / loss', p.exchange_gain_loss_inr, '', 'Realised vs invoice rate'],
  ]

  return (
    <>
      <div className="crumbs small"><Link to="/finance/profit">Order profit</Link> / {p.oc_no}</div>
      <div className="page-head">
        <div><h1>{p.oc_no} · profit</h1><p className="muted">{p.buyer_name} · <Link to={`/orders/${p.order}`}>order</Link> · {pcs(p.shipped_pcs)} of {pcs(p.ordered_pcs)} pcs shipped ({pct(p.shipped_share_pct)})</p></div>
      </div>
      {error && <div className="error">{error}</div>}
      {p.warnings.length > 0 && <div className="notice warn block"><ul>{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>}
      <div className="wo-kpis">
        <div className="card kpi"><div className="muted small">Revenue</div><div className="kpi-value">{inr(p.invoiced_inr)}</div><div className="small muted">received {inr(p.received_inr)}</div></div>
        <div className="card kpi"><div className="muted small">Cost</div><div className="kpi-value">{inr(p.costs.total_inr)}</div></div>
        <div className="card kpi"><div className="muted small">Profit</div><div className={`kpi-value ${Number(p.profit_inr) < 0 ? 'neg' : 'pos'}`}>{inr(p.profit_inr)}</div></div>
        <div className="card kpi"><div className="muted small">Margin · planned</div><div className="kpi-value">{pct(p.margin_pct)}</div><div className="small muted">planned {pct(p.planned_margin_pct)} (cost sheets)</div></div>
      </div>
      <div className="order-layout">
        <div>
          <div className="card">
            <h2>Profit statement</h2>
            <table className="pnl">
              <tbody>
                {rows.map(([label, v, tone, note]) => (
                  <tr key={label}><td>{label}{note && <div className="muted small">{note}</div>}</td><td className={`num ${tone || (Number(v) < 0 ? '' : 'pos')}`}>{Number(v) < 0 ? `− ${inr(-v)}` : inr(v)}</td></tr>
                ))}
                <tr className="total"><td>Profit</td><td className={`num ${Number(p.profit_inr) < 0 ? 'neg' : 'pos'}`}>{inr(p.profit_inr)}</td></tr>
              </tbody>
            </table>
          </div>
          <div className="card">
            <h2>Styles</h2>
            <div className="table-wrap">
              <table className="cost-lines">
                <thead><tr><th>Style</th><th className="num">Ordered</th><th className="num">Shipped</th><th className="num">Price</th><th className="num">Cost sheet cost/pc</th><th className="num">Conversion/pc</th><th className="num">Materials issued</th></tr></thead>
                <tbody>{p.styles.map((s) => (
                  <tr key={s.style_no}><td><b>{s.style_no}</b></td><td className="num">{pcs(s.ordered)}</td><td className="num">{pcs(s.shipped)}</td><td className="num">{num(s.price)}</td>
                    <td className="num">{num(s.cost_per_pc)}</td><td className="num">{num(s.conversion_per_pc)}</td><td className="num">{inr(s.materials_issued_inr)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h2>Invoices</h2>
            {p.invoices.length === 0 ? <p className="muted small">No invoices yet — raise them from shipped export shipments.</p> : (
              <div className="table-wrap"><table className="compact"><tbody>{p.invoices.map((i) => (
                <tr key={i.id}><td><Link to={`/finance/invoices/${i.id}`}>{i.invoice_no}</Link></td><td>{fmtDate(i.invoice_date)}</td><td className="num">{money(i.amount, i.currency)}</td><td><span className={`badge badge-inv-${i.status}`}>{i.status_label}</span></td></tr>
              ))}</tbody></table></div>
            )}
          </div>
        </div>
        <aside>
          <div className="card">
            <h2>Order expenses</h2>
            {p.expenses.length === 0 ? <p className="muted small">None yet.</p> : (
              <dl className="summary">{p.expenses.map((x) => (
                <div key={x.id}><dt>{x.category_label}<small className="muted">{x.note && ` · ${x.note}`}</small></dt><dd>{inr(x.amount_inr)} {canFinance && <button className="link" onClick={() => removeExpense(x)} aria-label="Delete expense">✕</button>}</dd></div>
              ))}</dl>
            )}
            {canFinance && (
              <form onSubmit={addExpense} className="expense-form">
                <select value={exp.category} onChange={(e) => setExp({ ...exp, category: e.target.value })} aria-label="Category">{CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                <input type="number" min="0.01" step="0.01" placeholder="Amount ₹" value={exp.amount_inr} onChange={(e) => setExp({ ...exp, amount_inr: e.target.value })} required aria-label="Amount" />
                <input type="date" value={exp.date} onChange={(e) => setExp({ ...exp, date: e.target.value })} aria-label="Date" />
                <input placeholder="Note" value={exp.note} onChange={(e) => setExp({ ...exp, note: e.target.value })} aria-label="Note" />
                <button type="submit" className="secondary">Add expense</button>
              </form>
            )}
          </div>
        </aside>
      </div>
    </>
  )
}
