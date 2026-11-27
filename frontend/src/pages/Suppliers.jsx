import ResourcePage from '../components/ResourcePage'
import { BOM_CATEGORIES } from '../components/dev/constants'
import { labelOf } from '../components/buyers/constants'

export default function Suppliers() {
  return (
    <ResourcePage
      title="Suppliers"
      subtitle="Fabric mills, trim and label makers, thread and packaging suppliers"
      endpoint="/suppliers/"
      defaults={{ country: 'India', lead_time_days: 14, is_active: true, categories: [] }}
      columns={[
        { key: 'name', label: 'Supplier', render: (r) => <><b>{r.name}</b>{!r.is_active && <span className="badge badge-po-cancelled">inactive</span>}<div className="muted small">{r.contact_name}</div></> },
        { key: 'categories', label: 'Supplies', render: (r) => r.categories.map((c) => labelOf(BOM_CATEGORIES, c)).join(', ') || '—' },
        { key: 'city', label: 'City' },
        { key: 'payment_terms', label: 'Payment terms' },
        { key: 'lead_time_days', label: 'Lead time', num: true, render: (r) => `${r.lead_time_days} days` },
        { key: 'email', label: 'Email' },
      ]}
      fields={[
        { name: 'company', label: 'Our company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'name', label: 'Supplier name', required: true },
        { name: 'contact_name', label: 'Contact person' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'tax_id', label: 'GSTIN' },
        { name: 'city', label: 'City' },
        { name: 'country', label: 'Country' },
        { name: 'payment_terms', label: 'Payment terms' },
        { name: 'lead_time_days', label: 'Lead time (days)', type: 'number' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
        { name: 'address', label: 'Address', type: 'textarea', full: true },
      ]}
      renderFormExtra={(form, { set }) => <CategoryPicker form={form} set={set} />}
    />
  )
}

function CategoryPicker({ form, set }) {
  const value = form.categories || []
  const toggle = (v) => set('categories', value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  return (
    <div className="field full" style={{ marginTop: 8 }}>
      <span>Supplies</span>
      <div className="chips" role="group" aria-label="Supplies">
        {BOM_CATEGORIES.map(([v, l]) => (
          <button key={v} type="button" className={`chip ${value.includes(v) ? 'on' : ''}`} aria-pressed={value.includes(v)} onClick={() => toggle(v)}>
            {value.includes(v) && '✓ '}{l}
          </button>
        ))}
      </div>
    </div>
  )
}
