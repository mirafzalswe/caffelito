# Deploy — Coffee Loyalty (Ubuntu 22.04 / 24.04)

Production deploy onto a bare VPS using systemd. No Docker.

## Architecture

Four long-running processes on one host:

| Service                    | What it runs                                         | Port  |
|----------------------------|------------------------------------------------------|-------|
| `coffee-api`               | `uvicorn app.main:app` — FastAPI + admin web         | 8000  |
| `coffee-bot-customer`      | `python -m app.bots.customer` — aiogram long-polling | —     |
| `coffee-bot-staff`         | `python -m app.bots.staff`    — aiogram long-polling | —     |
| `coffee-worker`            | `arq app.workers.arq_worker.WorkerSettings`          | —     |

Plus: PostgreSQL 16, Redis 7, nginx (reverse proxy + TLS).

## Server specs (minimum)

- 2 vCPU / 4 GB RAM / 40 GB NVMe SSD
- Ubuntu 22.04 LTS or 24.04 LTS
- Public IPv4
- Domain pointing to the server (for HTTPS / admin panel)

## Quick install

```bash
ssh root@your.server.ip
curl -fsSL https://raw.githubusercontent.com/mirafzalswe/caffelito/main/deploy/install.sh | sudo bash
```

The script:
1. installs Postgres 16, Redis 7, Python 3.12, nginx
2. creates the `coffee` system user and clones the repo into `/opt/coffee-loyalty`
3. creates the `coffee_loyalty` database and `app_role` user with a random password
4. generates `.env` with random secrets (pepper, JWT, webhook)
5. runs `alembic upgrade head`
6. installs and enables all four systemd units (does not start them yet)

## After install — required manual steps

1. **Add Telegram bot tokens** to `/opt/coffee-loyalty/.env`:
   ```
   CUSTOMER_BOT_TOKEN=123:abc...
   STAFF_BOT_TOKEN=456:def...
   ```
2. **Start services:**
   ```bash
   systemctl start coffee-api coffee-bot-customer coffee-bot-staff coffee-worker
   systemctl status coffee-api --no-pager
   ```
3. **Set up HTTPS** (needed if you'll use webhook mode or expose admin panel):
   ```bash
   cp /opt/coffee-loyalty/deploy/nginx/coffee.conf /etc/nginx/sites-available/
   sed -i 's/YOUR_DOMAIN.TLD/coffee.example.com/g' /etc/nginx/sites-available/coffee.conf
   ln -sf /etc/nginx/sites-available/coffee.conf /etc/nginx/sites-enabled/
   nginx -t && systemctl reload nginx
   apt-get install -y certbot python3-certbot-nginx
   certbot --nginx -d coffee.example.com
   ```

## Operating

```bash
# Logs (live tail)
journalctl -u coffee-api -f
journalctl -u coffee-bot-customer -f
journalctl -u coffee-worker -f

# Restart a service
systemctl restart coffee-api

# Restart everything
systemctl restart coffee-api coffee-bot-customer coffee-bot-staff coffee-worker
```

## Deploying updates

```bash
sudo -u coffee bash <<'EOF'
cd /opt/coffee-loyalty
git pull --ff-only
.venv/bin/pip install -e .
.venv/bin/alembic upgrade head
EOF
systemctl restart coffee-api coffee-bot-customer coffee-bot-staff coffee-worker
```

## Backups

Daily Postgres dump → `/var/backups/coffee/`:

```bash
sudo crontab -e
# add:
30 3 * * * pg_dump -U postgres -F c coffee_loyalty > /var/backups/coffee/$(date +\%F).dump
```

Ship dumps offsite (S3, Backblaze B2, rsync) — money lives in `ledger_entries`, you do not want to lose it.

## Switching to webhook mode (optional)

Long-polling is the default and works fine up to ~30 RPS per bot. To switch:

1. Set in `.env`:
   ```
   CUSTOMER_BOT_WEBHOOK_URL=https://coffee.example.com/webhooks/customer
   STAFF_BOT_WEBHOOK_URL=https://coffee.example.com/webhooks/staff
   ```
2. The bot processes are no longer needed — disable them:
   ```bash
   systemctl disable --now coffee-bot-customer coffee-bot-staff
   ```
3. The API handles `/webhooks/*` directly (see `app/api/routes/webhooks.py`).

## Hardening checklist

- [ ] `ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable`
- [ ] `passwd -l root` (disable root SSH login, use sudo)
- [ ] Set `PasswordAuthentication no` in `/etc/ssh/sshd_config`
- [ ] Restrict `/admin` by IP in `deploy/nginx/coffee.conf` if not public
- [ ] Rotate `app_role` Postgres password and update `.env`
- [ ] Confirm `.env` is `chmod 600` and owned by `coffee`
