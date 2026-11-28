import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api, { errorMessage } from '../api/client'
import { money } from '../components/merch/constants'
import { fmtDate } from '../components/buyers/constants'
import { inr } from '../components/fin/constants'

const COLORS = { not_due: '#94a3b8', d1_30: '#f59e0b', d31_60: '#f97316', d61_90: '#ef4444', d90_plus: '#991b1b' }
const shortInr = (v) => (v >= 1e7 ? `₹${(v / 1e7).toFixed(1)}Cr` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)}L` : `₹${Math.round(v / 1000)}K`)

export default function Receivables() {
  const [data, setData] = useState(null)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([api.get('/export-invoices/ageing/'), api.get('/export-invoices/summary/')])
      .then(([a, s]) => { setData(a.data); setSummary(s.data) }).catch((e) => setError(errorMessage(e)))
  }, [])
  if (error) return <div className="error">{error}</div>
  if (!data) return <div className="muted">Loading…</div>
  const chart = data.by_buyer.map((b) => ({ name: b.buyer_name, ...Object.fromEntries(data.buckets.map((k) => [k.key, Number(b[k.key])])) }))

  return (
    <>
      <div className="page-head">
        <div><h1>Receivables</h1><p className="muted">What buyers owe on export invoices, by how late it is. INR at each invoice's rate. As of {fmtDate(data.as_of)}.</p></div>
        <div className="actions"><Link className="button secondary" to="/finance/invoices">Export invoices</Link><Link className="button secondary" to="/finance/profit">Order profit</Link></div>
      </div>
      <div className="kpis">
        <div className="card kpi"><div className="muted small">Outstanding</div><div className="kpi-value">{inr(summary.receivable_inr)}</div></div>
        <div className="card kpi"><div className="muted small">Overdue</div><div className={`kpi-value ${Number(summary.overdue_inr) ? 'neg' : 'pos'}`}>{inr(summary.overdue_inr)}</div><div className="small muted">{summary.overdue_invoices} invoices</div></div>
        <div className="card kpi"><div className="muted small">Collected this month</div><div className="kpi-value pos">{inr(summary.collected_this_month_inr)}</div><div className="small muted">invoiced {inr(summary.invoiced_this_month_inr)}</div></div>
        <div className="card kpi"><div className="muted small">Exchange gain / loss (all time)</div><div className={`kpi-value ${Number(summary.exchange_gain_loss_inr) < 0 ? 'neg' : 'pos'}`}>{inr(summary.exchange_gain_loss_inr)}</div>
          {summary.shipped_not_invoiced > 0 && <div className="small neg">{summary.shipped_not_invoiced} shipped shipment(s) not invoiced</div>}</div>
      </div>

      <div className="card">
        <h2>Ageing by buyer</h2>
        {chart.length === 0 ? <p className="muted">Nothing outstanding.</p> : (
          <ResponsiveContainer width="100%" height={Math.max(160, chart.length * 56 + 60)}>
            <BarChart data={chart} layout="vertical" margin={{ left: 20, right: 20 }}>
              <CartesianGrid horizontal={false} stroke="var(--line)" />
              <XAxis type="number" tickFormatter={shortInr} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="name" width={150} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => inr(v)} cursor={{ fill: 'var(--hover)' }} />
              <Legend />
              {data.buckets.map((b) => <Bar key={b.key} dataKey={b.key} name={b.label} stackId="a" fill={COLORS[b.key]} />)}
            </BarChart>
          </ResponsiveContainer>
        )}
        <div className="table-wrap">
          <table className="cost-lines">
            <thead><tr><th>Buyer</th>{data.buckets.map((b) => <th key={b.key} className="num">{b.label}</th>)}<th className="num">Total INR</th><th className="num">Balance / credit limit</th></tr></thead>
            <tbody>
              {data.by_buyer.map((b) => (
                <tr key={b.buyer}>
                  <td><b>{b.buyer_name}</b></td>
                  {data.buckets.map((k) => <td key={k.key} className={`num ${k.key !== 'not_due' && Number(b[k.key]) ? 'neg' : ''}`}>{Number(b[k.key]) ? inr(b[k.key]) : '—'}</td>)}
                  <td className="num"><b>{inr(b.balance_inr)}</b></td>
                  <td className={`num ${b.over_limit ? 'neg' : ''}`}>{money(b.balance, b.currency)}{b.credit_limit != null && <div className="small">of {money(b.credit_limit, b.credit_currency)}{b.over_limit && ' — over limit'}</div>}</td>
                </tr>
              ))}
            </tbody>
            {data.by_buyer.length > 0 && <tfoot><tr><td><b>Total</b></td>{data.buckets.map((k) => <td key={k.key} className="num">{inr(data.totals[k.key])}</td>)}<td className="num"><b>{inr(data.total_inr)}</b></td><td /></tr></tfoot>}
          </table>
        </div>
      </div>

      <div className="card table-wrap">
        <table>
          <thead><tr><th>Invoice</th><th>Buyer</th><th>Invoice date</th><th>Due</th><th className="num">Days late</th><th className="num">Balance</th><th className="num">INR</th></tr></thead>
          <tbody>
            {data.invoices.length === 0 && <tr><td colSpan={7} className="muted center">No open invoices.</td></tr>}
            {data.invoices.map((r) => (
              <tr key={r.invoice}>
                <td><Link to={`/finance/invoices/${r.invoice}`}>{r.invoice_no}</Link></td><td>{r.buyer_name}</td><td>{fmtDate(r.invoice_date)}</td><td>{fmtDate(r.due_date)}</td>
                <td className={`num ${r.days_overdue ? 'neg' : 'muted'}`}>{r.days_overdue || '—'}</td><td className="num">{money(r.balance, r.currency)}</td><td className="num">{inr(r.balance_inr)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
