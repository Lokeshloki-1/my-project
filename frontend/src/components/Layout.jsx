import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { section: 'Buyers' },
  { to: '/buyer-enquiries', label: 'Enquiries' },
  { to: '/buyers/pipeline', label: 'Buyer Pipeline' },
  { to: '/buyers', label: 'Buyers', end: true },
  { section: 'Sales' },
  { to: '/costing', label: 'Cost Sheets' },
  { to: '/quotations', label: 'Quotations' },
  { to: '/orders', label: 'Order Confirmations' },
  { section: 'Product Development' },
  { to: '/tech-packs', label: 'Tech Packs' },
  { to: '/samples', label: 'Samples' },
  { section: 'Purchase' },
  { to: '/requirements', label: 'Material Requirements' },
  { to: '/rfqs', label: 'RFQs' },
  { to: '/purchase-orders', label: 'Supplier POs' },
  { to: '/suppliers', label: 'Suppliers' },
  { section: 'Inventory & Warehouse' },
  { to: '/receipts', label: 'Goods Receipts' },
  { to: '/material-stock', label: 'Material Stock' },
  { to: '/allocation', label: 'Stock Allocation' },
  { section: 'Production' },
  { to: '/production', label: 'Production Plan', end: true },
  { to: '/production/daily', label: 'Daily Output' },
  { to: '/production/lines', label: 'Sewing Lines' },
  { section: 'Quality' },
  { to: '/quality/inline', label: 'Inline QC' },
  { to: '/quality/final', label: 'Final Inspection' },
  { to: '/quality', label: 'Defect Control', end: true },
  { to: '/quality/defects', label: 'Defect Library' },
  { section: 'ERP' },
  { to: '/companies', label: 'Companies' },
  { to: '/employees', label: 'Employees' },
  { to: '/customers', label: 'Customers' },
  { to: '/products', label: 'Products' },
  { to: '/sales', label: 'Sales Orders' },
  { section: 'Finished Goods' },
  { to: '/stock', label: 'Stock' },
  { to: '/stock-movements', label: 'Stock Movements' },
  { to: '/warehouses', label: 'Warehouses' },
  { section: 'Billing' },
  { to: '/invoices', label: 'Invoices' },
  { to: '/payments', label: 'Payments' },
  { section: 'DDP' },
  { to: '/ddp', label: 'DDP Shipments' },
  { section: 'Analytics' },
  { to: '/reports', label: 'Sales Reports' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Hazpo<span>ERP</span></div>
        <nav>
          {NAV.map((item, i) =>
            item.section ? (
              <div key={i} className="nav-section">{item.section}</div>
            ) : (
              <NavLink key={item.to} to={item.to} end={item.end}>{item.label}</NavLink>
            ),
          )}
        </nav>
        <div className="sidebar-user">
          <div>{user.first_name || user.username}</div>
          <div className="muted small">{user.role}</div>
          <button className="link" onClick={logout}>Log out</button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
