import ResourcePage from '../components/ResourcePage'

export default function ProductionLines() {
  return (
    <ResourcePage
      title="Sewing Lines"
      subtitle="Capacity per line: operators × minutes × efficiency = sewing minutes available per day"
      endpoint="/production-lines/"
      managerOnly
      defaults={{ operators: 30, working_minutes: 480, efficiency_pct: 60, is_active: true }}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Line', render: (r) => <><b>{r.name}</b>{!r.is_active && <span className="badge badge-wo-cancelled">inactive</span>}</> },
        { key: 'operators', label: 'Operators', num: true },
        { key: 'working_minutes', label: 'Minutes / day', num: true },
        { key: 'efficiency_pct', label: 'Efficiency', num: true, render: (r) => `${Number(r.efficiency_pct)}%` },
        { key: 'cap', label: 'Sewing minutes / day', num: true, render: (r) => Math.round(r.operators * r.working_minutes * r.efficiency_pct / 100).toLocaleString('en-IN') },
        { key: 'eg', label: 'Tees / day (SMV 12)', num: true, render: (r) => Math.floor(r.operators * r.working_minutes * r.efficiency_pct / 100 / 12).toLocaleString('en-IN') },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Name', required: true },
        { name: 'operators', label: 'Operators', type: 'number', required: true },
        { name: 'working_minutes', label: 'Working minutes per day', type: 'number', required: true },
        { name: 'efficiency_pct', label: 'Efficiency %', type: 'number', required: true },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
    />
  )
}
