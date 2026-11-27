# Hazpo ERP

A small ERP for textile exporters: buyer onboarding, companies, employees, customers, products, sales orders,
stock and warehouses, invoices and payments, monthly sales reports and **DDP (Delivered Duty Paid)** export shipments.

| Layer    | Technology |
|----------|------------|
| Frontend | React 19 + Vite, React Router, Axios, Recharts |
| Backend  | Django 6 + Django REST Framework, JWT login (SimpleJWT), ReportLab (invoice PDFs) |
| Database | PostgreSQL 16 |

## Features

**Buyer onboarding** (textile flow, step 1 — [API reference](docs/api/buyer-onboarding.md))
- Buyer Enquiry → Registration → Profile → Contact Details → Requirements → Credit Verification → Approval.
- **Enquiries** from email, trade fairs, agents or the website; *Convert to buyer* creates the buyer with its contact.
- **Buyer page** with a 7-step progress bar that says exactly what is still missing, and tabs for profile,
  contacts (one primary), requirements (product categories, GSM, sizes, target price, GOTS / OEKO-TEX / BSCI …),
  credit checks and a timeline of every status change.
- **Credit verification** by accounts: credit limit, payment terms (LC, TT, DA/DP, advance), risk rating,
  bank/trade references, ECGC cover, pass or fail. Credit checks are never edited or deleted.
- **Approval** by a manager or admin creates the **customer**, so only approved buyers can get orders and invoices.
- **Buyer pipeline** board and a dashboard card showing how many buyers are at each step.

**ERP**
- **Companies** – run more than one business entity (e.g. a manufacturing company and an export company).
- **Employees & departments** – employee code, designation, salary, monthly sales target, status.
- **Customers & products** – products carry price, GST % and HS code (needed for customs).
- **Sales orders** – multiple line items; subtotal, GST and total are always calculated by the server.
  Status flow: draft → confirmed → invoiced → paid (or cancelled). Only drafts can be deleted.

**Stock & inventory**
- **Warehouses** per company (e.g. a main warehouse and a depot).
- **Stock page**: stock on hand per product per warehouse, the total across warehouses, cost, stock value,
  and a **Low** flag when a product's total stock is at or below its **reorder level** (set on the product).
- **Receive** (goods in from a supplier, with GRN / bill number), **Issue** (goods out that are not a sale),
  **Adjust** (after a stock count, with a reason; use a minus number to reduce) and **Transfer** between warehouses.
- **Sales orders take stock automatically**: choose a "ship from" warehouse on the order. When the order is
  confirmed the stock is taken; if there isn't enough, the order is refused with a clear message. Cancelling the
  order (or its invoice), or moving it back to draft, puts the stock back. Changing the items or warehouse of a
  confirmed order re-balances the stock. Orders with no warehouse don't touch stock (useful for services).
- **Stock movements**: a permanent record of every change (who, when, why, balance after). It is never edited
  or deleted — mistakes are corrected with an adjustment.
- Stock can never go below zero: the app checks it, and PostgreSQL enforces it too. Rows are locked while
  stock changes, so two people selling the last item at the same moment can't both succeed.
- The dashboard shows total stock value and how many products are low.

**Invoices & payments**
- Create an invoice from a **confirmed** sales order (button on the order). The invoice copies the order's
  amounts, the order becomes *invoiced* and is then **locked** against edits.
- Due date = invoice date + payment terms (default 30 days). Overdue invoices are highlighted.
- **Download PDF**: a tax invoice with HSN codes, GST per line, Indian number format and the amount in words.
- **Record payments** (bank transfer, UPI, cheque, cash, card) — full or part. A payment can't be more than
  the balance. Invoice status moves unpaid → partially paid → paid, and the order becomes *paid* automatically.
- Mistakes: payments can't be edited; an admin/manager deletes the payment and records it again.
  An invoice with no payments can be cancelled, which also cancels its order. Invoices are never deleted.
- The dashboard shows money owed to you and how much of it is overdue.
- **Collect by UPI QR (Razorpay)**: on an unpaid invoice, click *Collect by UPI QR*. A one-time QR for the balance
  appears; the customer scans it with PhonePe, Google Pay, Paytm, BHIM or any UPI app. When Razorpay confirms the
  payment it is recorded automatically (with the UPI reference / UTR) and the invoice turns *Paid*. See
  [Razorpay UPI QR setup](#razorpay-upi-qr-setup).

**DDP shipments**
Under DDP your company pays every cost until the goods reach the customer. For each shipment Hazpo calculates:

```
CIF value    = goods value + freight + insurance
customs duty = CIF × duty %
import VAT   = (CIF + duty) × VAT %
landed cost  = CIF + duty + VAT + other charges
margin       = price charged to customer − landed cost
```
The form shows this live while you type, and tracks status (booked → in transit → at customs → cleared → delivered).

**Reports**
- Dashboard: sales this month vs last month, year to date, active employees, open shipments.
- Monthly sales for the whole year (all companies or one company).
- Employee-wise sales for a month vs their monthly target (achievement %).
- Company-wise monthly sales chart.

Only orders that are *confirmed*, *invoiced* or *paid* count as sales.

**Roles**
| Role | Can do |
|------|--------|
| `admin`, `manager` | everything, including approving or rejecting buyers, editing companies, employees, products, warehouses, moving stock and deleting payments |
| `accountant` | record buyer credit checks, create invoices, record payments, cancel invoices; view everything |
| `sales` | create enquiries and buyers and submit them for credit check, create customers, orders and shipments; view invoices, payments and stock |

## Project structure

```
backend/
  hazpo/            Django settings, URLs
  apps/
    accounts/       User model (with role), login API, permissions
    companies/      Company model + seed_demo command
    employees/      Department, Employee
    buyers/         Buyer onboarding: enquiry, buyer, contacts, requirements, credit checks, approval (services.py)
    sales/          Customer, Product, SalesOrder, SalesOrderItem
    billing/        Invoice, Payment, invoice PDF (pdf.py), Razorpay UPI QR (razorpay.py, upi.py)
    inventory/      Warehouse, StockLevel, StockMovement; services.py is the only code that changes stock
    ddp/            Shipment (DDP landed cost)
    reports/        Dashboard & sales report APIs
frontend/
  src/
    api/client.js   Axios client (adds JWT, auto refresh)
    auth/           Login state
    components/     Layout, ResourcePage (generic list + form), Modal …
    pages/          One file per screen
docker-compose.yml  PostgreSQL for development
```

## Getting started

You need **Python 3.12+**, **Node.js 20+** and **PostgreSQL** (installed locally, or via Docker).

### 1. Database

With Docker:
```bash
docker compose up -d
```
Or with a local PostgreSQL:
```sql
CREATE USER hazpo WITH PASSWORD 'hazpo_dev_password' CREATEDB;
CREATE DATABASE hazpo OWNER hazpo;
```

### 2. Backend (Django) – http://localhost:8000
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit values if needed
python manage.py migrate
python manage.py seed_demo         # optional: demo data + logins admin, manager, accounts, sales (password = name + 12345)
python manage.py runserver
```
Django admin panel: http://localhost:8000/admin/

To create your own admin user instead: `python manage.py createsuperuser`.

### 3. Frontend (React) – http://localhost:5173
```bash
cd frontend
npm install
npm run dev
```
Vite forwards every `/api/...` request to Django on port 8000, so no extra setup is needed.

### Razorpay UPI QR setup

Optional — without keys the *Collect by UPI QR* button is simply hidden.

1. In the [Razorpay Dashboard](https://dashboard.razorpay.com) go to **Account & Settings → API Keys** and generate keys.
   Use **Test Mode** keys (`rzp_test_...`) while developing.
2. Put them in `backend/.env`:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxx
   RAZORPAY_QR_MINUTES=15        # how long a QR stays payable (Razorpay allows 2–120)
   ```
3. Restart Django. The button appears on unpaid invoices.

**How the payment reaches Hazpo** — two ways, both safe to use together (a payment is never recorded twice):
- *While the QR is on screen* the app asks Razorpay every few seconds whether it was paid. This works on your own
  computer with no extra setup.
- *Webhook* (instant, and catches payments after the screen was closed). Needs a public HTTPS address, so set it up
  on your server: Dashboard → **Account & Settings → Webhooks → Add New Webhook**, URL
  `https://your-domain/api/razorpay/webhook/`, event **`qr_code.credited`**, and a secret of your choice. Put the same
  secret in `RAZORPAY_WEBHOOK_SECRET`. Requests without a valid signature are rejected.

**Things to know**
- Razorpay QR codes created in **Test Mode cannot be scanned** (Razorpay's rule). To try a real payment, use Live Mode
  keys on a small invoice (e.g. ₹1) and refund it from the Razorpay Dashboard.
- Each QR is single-use, for the exact balance. Making a new QR closes the previous one, so a customer can't pay twice.
- If money arrives that can't be applied (e.g. the invoice was paid in cash meanwhile), nothing is recorded and the QR
  is marked *needs review* — apply or refund it from the Razorpay Dashboard.

### Run the tests
```bash
cd backend && python manage.py test apps
```

## API overview

All endpoints need `Authorization: Bearer <access token>` except login.

| Endpoint | Purpose |
|----------|---------|
| `POST /api/auth/login/` | `{username, password}` → access + refresh token |
| `POST /api/auth/refresh/` | new access token |
| `GET  /api/auth/me/` | current user |
| `/api/companies/` | CRUD |
| `/api/departments/`, `/api/employees/` | CRUD (`?company=`, `?status=`, `?search=`) |
| `/api/customers/`, `/api/products/` | CRUD |
| `/api/sales-orders/` | CRUD with nested `items` (`?status=`, `?order_date__gte=`) |
| `/api/invoices/` | list / create (`{sales_order, payment_terms_days}`) / view / edit due date & notes |
| `GET  /api/invoices/{id}/pdf/` | invoice PDF download |
| `POST /api/invoices/{id}/cancel/` | cancel an invoice with no payments |
| `POST /api/invoices/{id}/upi-qr/` | create a Razorpay UPI QR for the balance; `GET` = latest QR + payment check |
| `POST /api/razorpay/webhook/` | Razorpay webhook (`qr_code.credited`), verified by `X-Razorpay-Signature` |
| `/api/payments/` | list / record (`{invoice, amount, payment_date, method, reference}`) / delete |
| `/api/warehouses/` | CRUD |
| `GET  /api/stock-levels/` | stock per product per warehouse (`?warehouse=`, `?low_stock=true`, `?hide_empty=true`) |
| `/api/stock-movements/` | ledger list; `POST` `{movement_type: receipt\|issue\|adjustment, product, warehouse, quantity, reference, note}` |
| `POST /api/stock-movements/transfer/` | `{product, from_warehouse, to_warehouse, quantity}` |
| `/api/ddp/shipments/` | CRUD |
| `POST /api/ddp/shipments/quote/` | landed-cost calculator (saves nothing) |
| `GET /api/reports/dashboard/` | dashboard numbers |
| `GET /api/reports/monthly-sales/?year=2026&company=1` | 12 months of sales |
| `GET /api/reports/employee-sales/?year=2026&month=11` | sales per employee vs target |
| `GET /api/reports/company-sales/?year=2026` | sales per company per month |

Lists are paginated (25 per page, `?page=2`, `?page_size=100` up to 500).

## Running it for real (production)

See **[DEPLOY.md](DEPLOY.md)** — a step-by-step guide to put Hazpo on a server with HTTPS using Docker
(`docker-compose.prod.yml`), plus daily backups (`scripts/backup.sh`, `scripts/restore.sh`) and a go-live checklist.

## Ideas for next steps

Credit notes · CGST/SGST vs IGST split by state · purchase orders and suppliers (feeding stock receipts) ·
batch / expiry tracking · payment reminders by email · purchase orders ·
attendance & payroll · export reports to Excel · per-company user access.
