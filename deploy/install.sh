#!/usr/bin/env bash
# Coffee Loyalty — one-shot Ubuntu 22.04/24.04 server bootstrap.
# Run as root (or via sudo) on a fresh VPS:
#   curl -fsSL https://raw.githubusercontent.com/mirafzalswe/caffelito/main/deploy/install.sh | sudo bash
# Or clone first and run: sudo bash deploy/install.sh
set -euo pipefail

APP_USER="coffee"
APP_DIR="/opt/coffee-loyalty"
REPO_URL="${REPO_URL:-https://github.com/mirafzalswe/caffelito.git}"
PYTHON_BIN="python3.12"
DB_NAME="coffee_loyalty"
DB_USER="app_role"

log() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash $0"
    exit 1
fi

# Warn if RAM is below 2 GB — 512 MB / 1 GB hosts will OOM under Postgres+Redis+4 python procs.
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if (( MEM_MB < 1800 )); then
    echo
    echo "  WARNING: detected ${MEM_MB} MB RAM. Minimum recommended is 2048 MB (ideally 4096)."
    echo "  Creating a 2 GB swapfile as safety net..."
    if [[ ! -f /swapfile ]]; then
        fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
fi

log "Updating apt and installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release \
    git build-essential pkg-config \
    nginx \
    postgresql postgresql-contrib \
    redis-server \
    software-properties-common

log "Installing Python 3.12 + venv + dev headers"
# On Ubuntu 24.04 python3.12 is preinstalled but -venv / -dev are not.
# On Ubuntu 22.04 we need the deadsnakes PPA for python3.12 at all.
if ! command -v $PYTHON_BIN >/dev/null 2>&1; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
fi
apt-get install -y $PYTHON_BIN $PYTHON_BIN-venv $PYTHON_BIN-dev

log "Creating system user '$APP_USER'"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"

log "Cloning repository into $APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
    git clone "$REPO_URL" "$APP_DIR"
else
    git -C "$APP_DIR" pull --ff-only
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

log "Creating Python virtualenv and installing dependencies"
sudo -u "$APP_USER" $PYTHON_BIN -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -e "$APP_DIR"

log "Configuring PostgreSQL — database $DB_NAME, role $DB_USER"
DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
sudo -u postgres psql <<SQL
DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';
    ELSE
        ALTER ROLE $DB_USER PASSWORD '$DB_PASS';
    END IF;
END \$\$;
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
SQL

log "Enabling and starting Redis"
systemctl enable --now redis-server

log "Installing .env from template (if missing)"
if [[ ! -f "$APP_DIR/.env" ]]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    SECRET_PEPPER="$(openssl rand -hex 32)"
    SECRET_JWT="$(openssl rand -hex 32)"
    SECRET_WH="$(openssl rand -hex 32)"
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME|" "$APP_DIR/.env"
    sed -i "s|^APP_ENV=.*|APP_ENV=prod|" "$APP_DIR/.env"
    sed -i "s|^APP_DEBUG=.*|APP_DEBUG=false|" "$APP_DIR/.env"
    sed -i "s|^SECURITY_PEPPER=.*|SECURITY_PEPPER=$SECRET_PEPPER|" "$APP_DIR/.env"
    sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$SECRET_JWT|" "$APP_DIR/.env"
    sed -i "s|^TELEGRAM_WEBHOOK_SECRET=.*|TELEGRAM_WEBHOOK_SECRET=$SECRET_WH|" "$APP_DIR/.env"
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo
    echo "  Generated .env with random secrets. Now edit and add:"
    echo "    CUSTOMER_BOT_TOKEN=..."
    echo "    STAFF_BOT_TOKEN=..."
    echo "  File: $APP_DIR/.env"
    echo
fi

log "Running Alembic migrations"
sudo -u "$APP_USER" bash -c "cd $APP_DIR && .venv/bin/alembic upgrade head"

log "Installing systemd units"
install -m 0644 "$APP_DIR/deploy/systemd/coffee-api.service"           /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/coffee-bot-customer.service"  /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/coffee-bot-staff.service"     /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/coffee-worker.service"        /etc/systemd/system/
systemctl daemon-reload
systemctl enable coffee-api coffee-bot-customer coffee-bot-staff coffee-worker

log "Done. Next steps:"
cat <<EOF

  1. Edit $APP_DIR/.env and set CUSTOMER_BOT_TOKEN / STAFF_BOT_TOKEN
  2. Start services:
       systemctl start coffee-api coffee-bot-customer coffee-bot-staff coffee-worker
       systemctl status coffee-api --no-pager
  3. (Optional) Set up nginx + HTTPS for the admin panel / webhooks:
       cp $APP_DIR/deploy/nginx/coffee.conf /etc/nginx/sites-available/
       # edit YOUR_DOMAIN.TLD inside the file
       ln -sf /etc/nginx/sites-available/coffee.conf /etc/nginx/sites-enabled/
       nginx -t && systemctl reload nginx
       apt-get install -y certbot python3-certbot-nginx
       certbot --nginx -d your.domain.tld
  4. Logs:
       journalctl -u coffee-api -f
       journalctl -u coffee-bot-customer -f

EOF
