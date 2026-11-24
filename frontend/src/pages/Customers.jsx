import ResourcePage from '../components/ResourcePage'

export default function Customers() {
  return (
    <ResourcePage
      title="Customers"
      endpoint="/customers/"
      defaults={{ country: 'India' }}
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'city', label: 'City' },
        { key: 'country', label: 'Country' },
        { key: 'phone', label: 'Phone' },
        { key: 'email', label: 'Email' },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'name', label: 'Customer name', required: true },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'tax_id', label: 'GSTIN / Tax ID' },
        { name: 'city', label: 'City' },
        { name: 'country', label: 'Country' },
        { name: 'address', label: 'Address', type: 'textarea', full: true },
      ]}
    />
  )
}
