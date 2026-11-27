import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Companies from './pages/Companies'
import Employees from './pages/Employees'
import Customers from './pages/Customers'
import Products from './pages/Products'
import SalesOrders from './pages/SalesOrders'
import Shipments from './pages/Shipments'
import Reports from './pages/Reports'
import Invoices from './pages/Invoices'
import Payments from './pages/Payments'
import Stock from './pages/Stock'
import StockMovements from './pages/StockMovements'
import Warehouses from './pages/Warehouses'
import BuyerEnquiries from './pages/BuyerEnquiries'
import Buyers from './pages/Buyers'
import BuyerPipeline from './pages/BuyerPipeline'
import BuyerDetail from './pages/BuyerDetail'
import CostSheets from './pages/CostSheets'
import CostSheetDetail from './pages/CostSheetDetail'
import Quotations from './pages/Quotations'
import QuotationDetail from './pages/QuotationDetail'
import Orders from './pages/Orders'
import OrderDetail from './pages/OrderDetail'

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center muted">Loading…</div>
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Dashboard />} />
        <Route path="buyer-enquiries" element={<BuyerEnquiries />} />
        <Route path="buyers" element={<Buyers />} />
        <Route path="buyers/pipeline" element={<BuyerPipeline />} />
        <Route path="buyers/:id" element={<BuyerDetail />} />
        <Route path="costing" element={<CostSheets />} />
        <Route path="costing/:id" element={<CostSheetDetail />} />
        <Route path="quotations" element={<Quotations />} />
        <Route path="quotations/new" element={<QuotationDetail key="new" />} />
        <Route path="quotations/:id" element={<QuotationDetail />} />
        <Route path="orders" element={<Orders />} />
        <Route path="orders/:id" element={<OrderDetail />} />
        <Route path="companies" element={<Companies />} />
        <Route path="employees" element={<Employees />} />
        <Route path="customers" element={<Customers />} />
        <Route path="products" element={<Products />} />
        <Route path="sales" element={<SalesOrders />} />
        <Route path="invoices" element={<Invoices />} />
        <Route path="payments" element={<Payments />} />
        <Route path="stock" element={<Stock />} />
        <Route path="stock-movements" element={<StockMovements />} />
        <Route path="warehouses" element={<Warehouses />} />
        <Route path="ddp" element={<Shipments />} />
        <Route path="reports" element={<Reports />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
