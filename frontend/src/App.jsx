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
import TechPacks from './pages/TechPacks'
import TechPackDetail from './pages/TechPackDetail'
import Samples from './pages/Samples'
import SampleDetail from './pages/SampleDetail'
import Suppliers from './pages/Suppliers'
import MaterialRequirements from './pages/MaterialRequirements'
import MaterialRequirementDetail from './pages/MaterialRequirementDetail'
import RFQs from './pages/RFQs'
import RFQDetail from './pages/RFQDetail'
import PurchaseOrders from './pages/PurchaseOrders'
import PurchaseOrderDetail from './pages/PurchaseOrderDetail'
import GoodsReceipts from './pages/GoodsReceipts'
import GoodsReceiptDetail from './pages/GoodsReceiptDetail'
import MaterialStock from './pages/MaterialStock'
import Allocation from './pages/Allocation'
import ProductionPlan from './pages/ProductionPlan'
import ProductionOrderDetail from './pages/ProductionOrderDetail'
import DailyOutput from './pages/DailyOutput'
import ProductionLines from './pages/ProductionLines'

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
        <Route path="tech-packs" element={<TechPacks />} />
        <Route path="tech-packs/:id" element={<TechPackDetail />} />
        <Route path="samples" element={<Samples />} />
        <Route path="samples/:id" element={<SampleDetail />} />
        <Route path="suppliers" element={<Suppliers />} />
        <Route path="requirements" element={<MaterialRequirements />} />
        <Route path="requirements/:id" element={<MaterialRequirementDetail />} />
        <Route path="rfqs" element={<RFQs />} />
        <Route path="rfqs/new" element={<RFQDetail key="new" />} />
        <Route path="rfqs/:id" element={<RFQDetail />} />
        <Route path="purchase-orders" element={<PurchaseOrders />} />
        <Route path="purchase-orders/new" element={<PurchaseOrderDetail key="new" />} />
        <Route path="purchase-orders/:id" element={<PurchaseOrderDetail />} />
        <Route path="receipts" element={<GoodsReceipts />} />
        <Route path="receipts/new" element={<GoodsReceiptDetail key="new" />} />
        <Route path="receipts/:id" element={<GoodsReceiptDetail />} />
        <Route path="material-stock" element={<MaterialStock />} />
        <Route path="allocation" element={<Allocation />} />
        <Route path="allocation/:id" element={<Allocation />} />
        <Route path="production" element={<ProductionPlan />} />
        <Route path="production/new" element={<ProductionOrderDetail key="new" />} />
        <Route path="production/daily" element={<DailyOutput />} />
        <Route path="production/lines" element={<ProductionLines />} />
        <Route path="production/:id" element={<ProductionOrderDetail />} />
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
