import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api, { errorMessage } from '../api/client'
import useOptions from '../components/useOptions'
import { MONTHS, money, shortMoney } from '../utils/format'
import { Progress } from './Dashboard'

const COLORS = ['var(--accent)', 'var(--accent-2)', '#d97706', '#7c3aed']

export default function Reports() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [company, setCompany] = useState('')
  const companies = useOptions('/companies/')
  const [monthly, setMonthly] = useState(null)
  const [team, setTeam] = useState(null)
  const [byCompany, setByCompany] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const params = { year, company: company || undefined }
    Promise.all([
      api.get('/reports/monthly-sales/', { params }),
      api.get('/reports/employee-sales/', { params: { ...params, month } }),
      api.get('/reports/company-sales/', { params: { year } }),
    ])
      .then(([m, t, c]) => { setMonthly(m.data); setTeam(t.data); setByCompany(c.data); setError('') })
      .catch((e) => setError(errorMessage(e)))
  }, [year, month, company])

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i)
  const companyChart = byCompany && MONTHS.map((label, i) => Object.fromEntries([['label', label], ...byCompany.companies.map((c) => [c.company, Number(c.months[i])])]))

  return (
    <>
      <div className="page-head">
        <h1>Sales Reports</h1>
        <div className="actions">
          <select value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">All companies</option>
            {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {years.map((y) => <option key={y}>{y}</option>)}
          </select>
        </div>
      </div>
      {error && <div className="error">{error}</div>}

      {monthly && (
        <div className="card">
          <div className="card-head"><h2>Monthly sales · {year}</h2><strong>{money(monthly.grand_total)}</strong></div>
          <div className="table-wrap">
            <table className="compact">
              <thead><tr><th>Month</th>{monthly.months.map((m) => <th key={m.month} className="num">{m.label}</th>)}</tr></thead>
              <tbody>
                <tr><td>Sales</td>{monthly.months.map((m) => <td key={m.month} className="num">{shortMoney(m.total)}</td>)}</tr>
                <tr><td>Orders</td>{monthly.months.map((m) => <td key={m.month} className="num">{m.orders}</td>)}</tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {team && (
        <div className="card">
          <div className="card-head">
            <h2>Employee sales vs target</h2>
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m} {year}</option>)}
            </select>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Code</th><th>Employee</th><th>Company</th><th className="num">Orders</th><th className="num">Sales</th><th className="num">Target</th><th className="num">Achievement</th></tr></thead>
              <tbody>
                {team.employees.length === 0 && <tr><td colSpan={7} className="muted center">No employees.</td></tr>}
                {team.employees.map((e) => (
                  <tr key={e.employee_id}>
                    <td>{e.employee_code}</td><td>{e.name}</td><td>{e.company}</td>
                    <td className="num">{e.orders}</td><td className="num">{money(e.sales)}</td>
                    <td className="num">{money(e.target)}</td><td className="num"><Progress value={e.achievement_percent} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {byCompany && (
        <div className="card">
          <h2>Company-wise sales · {year}</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={companyChart}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis tickFormatter={shortMoney} tickLine={false} axisLine={false} width={60} />
              <Tooltip formatter={(v) => money(v)} cursor={{ fill: 'var(--hover)' }} />
              <Legend />
              {byCompany.companies.map((c, i) => <Bar key={c.company_id} dataKey={c.company} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </>
  )
}
