import ResourcePage from '../components/ResourcePage'
import StatusBadge from '../components/StatusBadge'
import { money } from '../utils/format'

export default function Employees() {
  return (
    <ResourcePage
      title="Employees"
      endpoint="/employees/"
      managerOnly
      defaults={{ status: 'active', monthly_salary: 0, monthly_sales_target: 0 }}
      columns={[
        { key: 'employee_code', label: 'Code' },
        { key: 'full_name', label: 'Name' },
        { key: 'company_name', label: 'Company' },
        { key: 'department_name', label: 'Department' },
        { key: 'designation', label: 'Designation' },
        { key: 'monthly_sales_target', label: 'Monthly target', num: true, render: (r) => money(r.monthly_sales_target) },
        { key: 'status', label: 'Status', render: (r) => <StatusBadge value={r.status} /> },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'department', label: 'Department', type: 'select', optionsUrl: '/departments/',
          optionsFilter: (f) => (f.company ? { company: f.company } : null) },
        { name: 'employee_code', label: 'Employee code', required: true },
        { name: 'first_name', label: 'First name', required: true },
        { name: 'last_name', label: 'Last name' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'designation', label: 'Designation' },
        { name: 'date_joined', label: 'Date joined', type: 'date', required: true },
        { name: 'monthly_salary', label: 'Monthly salary', type: 'number' },
        { name: 'monthly_sales_target', label: 'Monthly sales target', type: 'number' },
        { name: 'status', label: 'Status', type: 'select', options: [
          { value: 'active', label: 'Active' }, { value: 'on_leave', label: 'On leave' }, { value: 'exited', label: 'Exited' },
        ] },
      ]}
    />
  )
}
