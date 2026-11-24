# Hazpo ERP

A small ERP for managing companies, employees, customers, products, sales orders,
invoices and payments, monthly sales reports and **DDP (Delivered Duty Paid)** export shipments.

| Layer    | Technology |
|----------|------------|
| Frontend | React 19 + Vite, React Router, Axios, Recharts |
| Backend  | Django 6 + Django REST Framework, JWT login (SimpleJWT), ReportLab (invoice PDFs) |
| Database | PostgreSQL 16 |

## Features

**ERP**
- **Companies** – run more than one business entity (e.g. a manufacturing company and an export company).
- **Employees & departments** – employee code, designation, salary, monthly sales target, status.
- **Customers & products** – products carry price, GST % and HS code (needed for customs).
- **Sales orders** – multiple line items; subtotal, GST and total are always calculated by the server.
  Status flow: draft → confirmed → invoiced → paid (or cancelled). Only drafts can be deleted.

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
| `admin`, `manager` | everything, including editing companies, employees, products and deleting payments |
| `accountant` | create invoices, record payments, cancel invoices; view everything |
| `sales` | create customers, orders and shipments; view invoices and payments |

## Project structure

```
backend/
  hazpo/            Django settings, URLs
  apps/
    accounts/       User model (with role), login API, permissions
    companies/      Company model + seed_demo command
    employees/      Department, Employee
    sales/          Customer, Product, SalesOrder, SalesOrderItem
    billing/        Invoice, Payment, invoice PDF (pdf.py)
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
python manage.py seed_demo         # optional: demo data + login admin / admin12345
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
| `/api/payments/` | list / record (`{invoice, amount, payment_date, method, reference}`) / delete |
| `/api/ddp/shipments/` | CRUD |
| `POST /api/ddp/shipments/quote/` | landed-cost calculator (saves nothing) |
| `GET /api/reports/dashboard/` | dashboard numbers |
| `GET /api/reports/monthly-sales/?year=2026&company=1` | 12 months of sales |
| `GET /api/reports/employee-sales/?year=2026&month=11` | sales per employee vs target |
| `GET /api/reports/company-sales/?year=2026` | sales per company per month |

Lists are paginated (25 per page, `?page=2`, `?page_size=100` up to 500).

## Before going to production

- Set `DJANGO_DEBUG=false`, a long random `DJANGO_SECRET_KEY`, and real `DJANGO_ALLOWED_HOSTS`.
- Change or delete the demo `admin` user.
- Build the frontend with `npm run build` and serve `frontend/dist/`; run Django with gunicorn.
- Set `VITE_API_URL` if the API is on a different domain, and add that domain to `CORS_ALLOWED_ORIGINS`.

## Ideas for next steps

Credit notes · CGST/SGST vs IGST split by state · payment reminders by email · stock / inventory · purchase orders ·
attendance & payroll · export reports to Excel · per-company user access.
