# Deploying Hazpo for real use

This puts Hazpo on a server on the internet, with HTTPS, so your team can use it from any browser.

```
Internet ──HTTPS──▶  web (Caddy)  ──▶  React app (built files)
                         │
                         └── /api, /admin ──▶  backend (Django + gunicorn)  ──▶  db (PostgreSQL)
```

Everything runs in Docker with one command. Caddy gets and renews the HTTPS certificate for you (free, Let's Encrypt).

## What you need

- **A Linux server (VPS)** — Ubuntu 22.04 or 24.04, at least **2 GB RAM**, 1–2 CPUs, 25 GB disk.
  Any provider works: DigitalOcean, AWS Lightsail, Hetzner, Hostinger VPS, Linode, Google Cloud, Azure…
- **A domain name**, e.g. `erp.yourcompany.com`.
- About 30 minutes.

## 1. Point your domain at the server

In your domain provider's DNS settings, add an **A record**: name `erp` (or `@`), value = your server's public IP.
Check it: `ping erp.yourcompany.com` should show the server's IP (can take a few minutes).

## 2. Prepare the server

SSH in (`ssh root@YOUR_SERVER_IP`), then:

```bash
# Firewall: allow SSH, HTTP and HTTPS only
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

# Docker
curl -fsSL https://get.docker.com | sh

# Hazpo
git clone https://github.com/Lokeshloki-1/my-project.git
cd my-project
git checkout main
```

## 3. Settings

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Fill in:

| Setting | Value |
|---|---|
| `SITE_ADDRESS`, `DJANGO_ALLOWED_HOSTS` | your domain, e.g. `erp.yourcompany.com` |
| `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | `https://erp.yourcompany.com` |
| `DJANGO_SECRET_KEY` | output of `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `POSTGRES_PASSWORD` | another long random value (same command) |
| `RAZORPAY_*` | your **live** keys, or leave empty to hide UPI QR |

Keep `.env.prod` private. It is ignored by git — never commit it.

## 4. Start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

The first build takes a few minutes. Then create your own admin login:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python manage.py createsuperuser
```

Open `https://erp.yourcompany.com` and log in. Check `https://erp.yourcompany.com/api/health/` shows `{"status": "ok"}`.

> Do **not** run `seed_demo` on the real server — it adds fake companies and a known `admin` password.

## 5. Set up your business

1. **Companies** → add your company (GSTIN, address — these print on invoices).
2. **Warehouses** → add where you keep stock.
3. **Products** → add products with price, GST %, HSN code, cost price and reorder level.
4. **Stock → Receive** → enter your opening stock.
5. **Employees** → add staff and their monthly targets.
6. Django admin (`/admin/`) → **Users** → create a login for each person with the right **role**
   (admin, manager, accountant, sales). Give people their own logins — never share one.

## 6. Backups (do this on day one)

```bash
./scripts/backup.sh                         # makes backups/hazpo-DATE.dump
crontab -e                                  # then add this line for a daily 2am backup:
0 2 * * * cd /root/my-project && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Backups older than 14 days are deleted automatically. **Also copy them off the server** (another machine, Google
Drive, S3…) — if the server's disk dies, backups on it die too. Most VPS providers also sell automatic snapshots;
turn that on as a second safety net.

Restore (replaces all current data — it asks you to type `RESTORE`):

```bash
./scripts/restore.sh backups/hazpo-2026-11-25_0200.dump
```

Test a restore once, so you know it works before you need it.

## 7. Razorpay (if using UPI QR)

1. Use **Live Mode** keys in `.env.prod` (`rzp_live_...`), then restart: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`.
2. Razorpay Dashboard → **Account & Settings → Webhooks → Add New Webhook**:
   URL `https://erp.yourcompany.com/api/razorpay/webhook/`, event **`qr_code.credited`**, and a secret.
   Put the same secret in `RAZORPAY_WEBHOOK_SECRET` and restart.
3. Try it with a ₹1 invoice, then refund that payment from the Razorpay Dashboard.

## Everyday commands

Run these in the `my-project` folder. Tip: `alias hz='docker compose -f docker-compose.prod.yml --env-file .env.prod'`.

| Task | Command |
|---|---|
| Update to the latest code | `git pull && hz up -d --build` (migrations run automatically) |
| See what's running | `hz ps` |
| Logs (errors show here) | `hz logs -f backend` or `hz logs -f web` |
| Restart | `hz restart` |
| Stop | `hz down` (data is kept) |
| Django shell | `hz exec backend python manage.py shell` |

Back up before every update.

## Go-live checklist

- [ ] HTTPS works (padlock in the browser) and `/api/health/` is ok
- [ ] Your own admin user created; no demo data or `admin/admin12345` login
- [ ] `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` are long and random
- [ ] Daily backup runs, copies go off the server, and a restore was tested
- [ ] Each person has their own login with the right role
- [ ] After a few days of working HTTPS, set `DJANGO_HSTS_SECONDS=31536000` and restart
- [ ] An uptime monitor (e.g. UptimeRobot, free) checks `https://erp.yourcompany.com/api/health/`

## Troubleshooting

- **Site doesn't load / certificate error** — check the DNS A record points at this server and ports 80/443 are open.
  `hz logs web` shows Caddy's certificate messages.
- **"Bad Request (400)"** — your domain is missing from `DJANGO_ALLOWED_HOSTS`.
- **Admin login says CSRF failed** — `CSRF_TRUSTED_ORIGINS` must be `https://your-domain`.
- **Something else** — `hz logs backend` shows the Django error.
