import ResourcePage from '../components/ResourcePage'

export default function Companies() {
  return (
    <ResourcePage
      title="Companies"
      endpoint="/companies/"
      managerOnly
      defaults={{ country: 'India', currency: 'INR', is_active: true }}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'city', label: 'City' },
        { key: 'country', label: 'Country' },
        { key: 'currency', label: 'Currency' },
        { key: 'is_active', label: 'Active', render: (r) => (r.is_active ? 'Yes' : 'No') },
      ]}
      fields={[
        { name: 'name', label: 'Company name', required: true },
        { name: 'code', label: 'Code', required: true },
        { name: 'tax_id', label: 'GSTIN / Tax ID' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'city', label: 'City' },
        { name: 'country', label: 'Country' },
        { name: 'currency', label: 'Currency (3 letters)' },
        { name: 'address', label: 'Address', type: 'textarea', full: true },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
    />
  )
}
