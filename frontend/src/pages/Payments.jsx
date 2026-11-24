import { Link } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'
import { money } from '../utils/format'

const METHOD_LABELS = { bank_transfer: 'Bank transfer', upi: 'UPI', cheque: 'Cheque', cash: 'Cash', card: 'Card' }

export default function Payments() {
  return (
    <ResourcePage
      title="Payments"
      subtitle="Payments received from customers. Record a payment from the invoice it belongs to."
      endpoint="/payments/"
      readOnly
      columns={[
        { key: 'payment_date', label: 'Date' },
        { key: 'invoice_no', label: 'Invoice', render: (r) => <Link to={`/invoices?open=${r.invoice}`}>{r.invoice_no}</Link> },
        { key: 'customer_name', label: 'Customer' },
        { key: 'method', label: 'Method', render: (r) => METHOD_LABELS[r.method] ?? r.method },
        { key: 'reference', label: 'Reference' },
        { key: 'amount', label: 'Amount', num: true, render: (r) => money(r.amount) },
      ]}
      fields={[]}
    />
  )
}
