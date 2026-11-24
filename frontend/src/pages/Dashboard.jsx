import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api, { errorMessage } from '../api/client'
import { money, shortMoney } from '../utils/format'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [monthly, setMonthly] = useState(null)
  const [team, setTeam] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.get('/reports/dashboard/'), api.get('/reports/monthly-sales/'), api.get('/reports/employee-sales/')])
      .then(([s, m, t]) => { setStats(s.data); setMonthly(m.data); setTeam(t.data) })
      .catch((e) => setError(errorMessage(e)))
  }, [])

  if (error) return <div className="error">{error}</div>
  if (!stats) return <div className="muted">Loading…</div>

  return (
    <>
      <div className="page-head"><h1>Dashboard</h1><span className="muted">{stats.month}</span></div>
      <div className="kpis">
        <Kpi label="Sales this month" value={money(stats.sales_this_month)}
          sub={stats.growth_percent == null ? 'No sales last month' : `${stats.growth_percent >= 0 ? '▲' : '▼'} ${Math.abs(stats.growth_percent)}% vs last month`}
          tone={stats.growth_percent >= 0 ? 'pos' : 'neg'} />
        <Kpi label="Sales year to date" value={money(stats.sales_year_to_date)} />
        <Kpi label="Orders this month" value={stats.orders_this_month} />
        <Kpi label="Active employees" value={stats.active_employees} sub={`${stats.companies} companies`} />
        <Kpi label="Open DDP shipments" value={stats.open_ddp_shipments} />
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Monthly sales · {monthly.year}</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={monthly.months.map((m) => ({ ...m, total: Number(m.total) }))}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis tickFormatter={shortMoney} tickLine={false} axisLine={false} width={60} />
              <Tooltip formatter={(v) => money(v)} cursor={{ fill: 'var(--hover)' }} />
              <Bar dataKey="total" name="Sales" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h2>Top salespeople · {team.label}</h2>
          <table>
            <thead><tr><th>Employee</th><th className="num">Sales</th><th className="num">Target</th></tr></thead>
            <tbody>
              {team.employees.slice(0, 6).map((e) => (
                <tr key={e.employee_id}>
                  <td>{e.name}<div className="muted small">{e.company}</div></td>
                  <td className="num">{money(e.sales)}</td>
                  <td className="num"><Progress value={e.achievement_percent} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

function Kpi({ label, value, sub, tone }) {
  return (
    <div className="card kpi">
      <div className="muted small">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className={`small ${tone || 'muted'}`}>{sub}</div>}
    </div>
  )
}

export function Progress({ value }) {
  if (value == null) return <span className="muted">—</span>
  return (
    <div className="progress" title={`${value}% of target`}>
      <div className={value >= 100 ? 'done' : ''} style={{ width: `${Math.min(value, 100)}%` }} />
      <span>{value}%</span>
    </div>
  )
}
