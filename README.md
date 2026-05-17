# Coffee Loyalty

Multi-tenant Telegram-based loyalty / cashback / prepaid platform for coffee shops.
See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for product, architecture, DB schema, business logic, security, scaling, and roadmap.

## Stack

- Python 3.12+ · FastAPI · aiogram 3 · SQLAlchemy 2 (async) · asyncpg
- PostgreSQL 16+ · Redis 7+
- arq (workers) · Alembic (migrations)
- structlog · pydantic-settings

## Quickstart (macOS, no Docker)

```bash
# 1. system services (you already have postgres + redis if you followed the plan)
brew services start redis
# postgres: official installer or `brew services start postgresql@16`

# 2. create the database
createdb -U postgres coffee_loyalty       # adjust user if needed

# 3. python env
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"

# 4. configure
cp .env.example .env
$EDITOR .env                              # set DATABASE_URL, bot tokens, secrets

# 5. migrate
alembic upgrade head

# 6. seed demo data (one tenant, one branch, products, a punchcard campaign)
python -m scripts.seed

# 7. run components (separate terminals)
uvicorn app.main:app --reload --port 8000
python -m app.bots.customer            # long-polling locally
python -m app.bots.staff
arq app.workers.arq_worker.WorkerSettings
```

## Layout

```
app/
  core/         settings, db engine, redis, logging
  models/       SQLAlchemy ORM
  domain/       pure business logic (identity, loyalty engine, prepaid, wallet)
  schemas/      Pydantic DTOs
  bots/
    customer/   end-user TG bot
    staff/      barista TG bot
  api/          FastAPI app + webhook receivers + admin REST
  workers/      arq jobs (outbox, notifications, expirations)
alembic/        DB migrations
scripts/        seed, ops helpers
tests/          pytest
```

## Operating principles (from the plan)

1. **Append-only ledger.** All money/loyalty changes write to `transactions` + `ledger_entries` in one DB transaction. Balances are projections.
2. **Idempotency everywhere.** Every mutating call carries a `client_request_id` (UUID). Replays return the original result.
3. **Locking.** `SELECT … FOR UPDATE` on prepaid; optimistic `version` on loyalty cards & wallets.
4. **Identity by phone.** `users.phone_e164` is unique per tenant. `telegram_id` is nullable; linked deferred via `request_contact`.
5. **Outbox pattern.** Domain events written in same DB tx; arq publisher fans out to consumers.
6. **RLS as second line.** Each connection sets `app.tenant_id`; Postgres RLS policies enforce isolation.
