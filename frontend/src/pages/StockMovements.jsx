import { Link } from 'react-router-dom'
import ResourcePage from '../components/ResourcePage'

const qty = (v) => Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })

export default function StockMovements() {
  return (
    <ResourcePage
      title="Stock Movements"
      subtitle="Every change in stock, newest first. Entries are permanent — fix mistakes with an adjustment on the Stock page."
      endpoint="/stock-movements/"
      readOnly
      columns={[
        { key: 'created_at', label: 'When', render: (r) => new Date(r.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) },
        { key: 'type_label', label: 'Type' },
        { key: 'product_name', label: 'Product', render: (r) => `${r.sku} · ${r.product_name}` },
        { key: 'warehouse_name', label: 'Warehouse' },
        { key: 'quantity', label: 'Qty', num: true, render: (r) => <span className={Number(r.quantity) < 0 ? 'neg' : 'pos'}>{Number(r.quantity) > 0 ? '+' : ''}{qty(r.quantity)}</span> },
        { key: 'balance_after', label: 'Balance', num: true, render: (r) => qty(r.balance_after) },
        { key: 'reference', label: 'Reference', render: (r) => (r.sales_order ? <Link to="/sales">{r.order_no}</Link> : r.reference || '—') },
        { key: 'note', label: 'Note' },
        { key: 'created_by_name', label: 'By', render: (r) => r.created_by_name || 'system' },
      ]}
      fields={[]}
    />
  )
}
