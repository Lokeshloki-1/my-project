import ResourcePage from '../components/ResourcePage'
import { money } from '../utils/format'

export default function Products() {
  return (
    <ResourcePage
      title="Products"
      endpoint="/products/"
      managerOnly
      defaults={{ tax_rate: 18, cost_price: 0, reorder_level: 0, is_active: true }}
      columns={[
        { key: 'sku', label: 'SKU' },
        { key: 'name', label: 'Name' },
        { key: 'hs_code', label: 'HS code' },
        { key: 'unit_price', label: 'Unit price', num: true, render: (r) => money(r.unit_price) },
        { key: 'tax_rate', label: 'GST %', num: true },
        { key: 'stock_on_hand', label: 'In stock', num: true, render: (r) => (
          <>{Number(r.stock_on_hand).toLocaleString('en-IN')}{r.is_low_stock && <span className="badge badge-low" style={{ marginLeft: 6 }}>Low</span>}</>
        ) },
        { key: 'is_active', label: 'Active', render: (r) => (r.is_active ? 'Yes' : 'No') },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'sku', label: 'SKU', required: true },
        { name: 'name', label: 'Product name', required: true },
        { name: 'hs_code', label: 'HS code (customs)' },
        { name: 'unit_price', label: 'Unit price', type: 'number', required: true },
        { name: 'tax_rate', label: 'GST / tax %', type: 'number' },
        { name: 'cost_price', label: 'Cost price (for stock value)', type: 'number' },
        { name: 'reorder_level', label: 'Reorder level (warn at or below)', type: 'number' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
    />
  )
}
