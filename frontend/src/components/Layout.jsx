import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { section: 'ERP' },
  { to: '/companies', label: 'Companies' },
  { to: '/employees', label: 'Employees' },
  { to: '/customers', label: 'Customers' },
  { to: '/products', label: 'Products' },
  { to: '/sales', label: 'Sales Orders' },
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
