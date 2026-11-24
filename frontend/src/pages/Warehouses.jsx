import ResourcePage from '../components/ResourcePage'

export default function Warehouses() {
  return (
    <ResourcePage
      title="Warehouses"
      endpoint="/warehouses/"
      managerOnly
      defaults={{ is_active: true }}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'company_name', label: 'Company' },
        { key: 'city', label: 'City' },
        { key: 'is_active', label: 'Active', render: (r) => (r.is_active ? 'Yes' : 'No') },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Warehouse name', required: true },
        { name: 'city', label: 'City' },
        { name: 'address', label: 'Address', type: 'textarea', full: true },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
    />
  )
}
