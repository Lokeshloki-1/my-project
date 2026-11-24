import { useEffect, useState } from 'react'
import api from '../api/client'
import ResourcePage from '../components/ResourcePage'
import StatusBadge from '../components/StatusBadge'
import { money } from '../utils/format'

const COST_FIELDS = ['goods_value', 'freight_cost', 'insurance_cost', 'customs_duty_rate', 'import_vat_rate', 'other_charges']

// Shows the DDP landed cost while the user types, using the backend calculator.
function LandedCostPreview({ form }) {
  const [quote, setQuote] = useState(null)
  const key = COST_FIELDS.map((f) => form[f] ?? '').join('|')
  useEffect(() => {
    if (!form.goods_value) { setQuote(null); return }
    const body = Object.fromEntries(COST_FIELDS.filter((f) => form[f] !== '' && form[f] != null).map((f) => [f, form[f]]))
    const t = setTimeout(() => api.post('/ddp/shipments/quote/', body).then((r) => setQuote(r.data)).catch(() => setQuote(null)), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  if (!quote) return <p className="muted small">Enter the goods value to see the DDP landed cost.</p>
  const margin = Number(form.invoice_value || 0) - Number(quote.landed_cost)
  return (
    <div className="cost-box">
      <div><span>CIF value</span><strong>{money(quote.cif_value)}</strong></div>
      <div><span>Customs duty</span><strong>{money(quote.customs_duty)}</strong></div>
      <div><span>Import VAT</span><strong>{money(quote.import_vat)}</strong></div>
      <div><span>Landed cost</span><strong>{money(quote.landed_cost)}</strong></div>
      <div><span>Margin</span><strong className={margin < 0 ? 'neg' : 'pos'}>{money(margin)}</strong></div>
    </div>
  )
}

export default function Shipments() {
  return (
    <ResourcePage
      title="DDP Shipments"
      subtitle="Delivered Duty Paid — your company pays freight, insurance, duty and import tax up to the customer's door."
      endpoint="/ddp/shipments/"
      defaults={{ status: 'booked', mode: 'sea', currency: 'INR', origin_country: 'India', freight_cost: 0, insurance_cost: 0, customs_duty_rate: 0, import_vat_rate: 0, other_charges: 0, invoice_value: 0 }}
      columns={[
        { key: 'shipment_no', label: 'Shipment #' },
        { key: 'customer_name', label: 'Customer' },
        { key: 'destination_country', label: 'Destination' },
        { key: 'mode', label: 'Mode' },
        { key: 'expected_delivery', label: 'ETA' },
        { key: 'status', label: 'Status', render: (r) => <StatusBadge value={r.status} /> },
        { key: 'landed_cost', label: 'Landed cost', num: true, render: (r) => money(r.landed_cost) },
        { key: 'margin', label: 'Margin', num: true, render: (r) => <span className={Number(r.margin) < 0 ? 'neg' : ''}>{money(r.margin)}</span> },
      ]}
      fields={[
        { name: 'company', label: 'Company', type: 'select', optionsUrl: '/companies/', required: true },
        { name: 'customer', label: 'Customer', type: 'select', optionsUrl: '/customers/', optionsFilter: (f) => (f.company ? { company: f.company } : null), required: true },
        { name: 'sales_order', label: 'Sales order', type: 'select', optionsUrl: '/sales-orders/', optionsFilter: (f) => (f.company && f.customer ? { company: f.company, customer: f.customer } : null), optionLabel: (o) => `${o.order_no} · ${o.total}` },
        { name: 'status', label: 'Status', type: 'select', options: ['booked', 'in_transit', 'at_customs', 'cleared', 'delivered', 'cancelled'].map((v) => ({ value: v, label: v.replace('_', ' ') })) },
        { name: 'mode', label: 'Mode', type: 'select', options: ['sea', 'air', 'road', 'rail', 'courier'].map((v) => ({ value: v, label: v })) },
        { name: 'carrier', label: 'Carrier' },
        { name: 'tracking_no', label: 'Tracking no.' },
        { name: 'origin_country', label: 'Origin country' },
        { name: 'destination_country', label: 'Destination country', required: true },
        { name: 'ship_date', label: 'Ship date', type: 'date' },
        { name: 'expected_delivery', label: 'Expected delivery', type: 'date' },
        { name: 'delivered_date', label: 'Delivered date', type: 'date' },
        { name: 'goods_value', label: 'Goods value', type: 'number', required: true },
        { name: 'freight_cost', label: 'Freight cost', type: 'number' },
        { name: 'insurance_cost', label: 'Insurance cost', type: 'number' },
        { name: 'customs_duty_rate', label: 'Customs duty %', type: 'number' },
        { name: 'import_vat_rate', label: 'Import VAT / GST %', type: 'number' },
        { name: 'other_charges', label: 'Other charges (clearing, port…)', type: 'number' },
        { name: 'invoice_value', label: 'Price charged to customer', type: 'number' },
        { name: 'destination_address', label: 'Delivery address', type: 'textarea', full: true },
      ]}
      renderFormExtra={(form) => <LandedCostPreview form={form} />}
    />
  )
}
