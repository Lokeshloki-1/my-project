import ResourcePage from '../components/ResourcePage'
import { money } from '../utils/format'

export default function Products() {
  return (
    <ResourcePage
      title="Products"
      endpoint="/products/"
      managerOnly
      defaults={{ tax_rate: 18, is_active: true }}
      columns={[
        { key: 'sku', label: 'SKU' },
        { key: 'name', label: 'Name' },
        { key: 'hs_code', label: 'HS code' },
        { key: 'unit_price', label: 'Unit price', num: true, render: (r) => money(r.unit_price) },
        { key: 'tax_rate', label: 'GST %', num: true },
        { key: 'is_active', label: 'Active', render: (r) => (r.is_active ? 'Yes' : 'No') },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'sku', label: 'SKU', required: true },
        { name: 'name', label: 'Product name', required: true },
        { name: 'hs_code', label: 'HS code (customs)' },
        { name: 'unit_price', label: 'Unit price', type: 'number', required: true },
        { name: 'tax_rate', label: 'GST / tax %', type: 'number' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
    />
  )
}
