"""arq worker definition.

Run via:

    arq app.workers.arq_worker.WorkerSettings
"""

from __future__ import annotations

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.workers.jobs.expirations import (
    expire_loyalty_cards,
    expire_prepaid_packages,
    expire_wallet_entries,
)
from app.workers.jobs.notifications import send_due
from app.workers.jobs.outbox import drain_outbox


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [drain_outbox, send_due, expire_loyalty_cards, expire_prepaid_packages, expire_wallet_entries]
    cron_jobs = [
        # Outbox: every 2 seconds; arq enforces single-fire across workers.
        cron(drain_outbox, second={0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26,
                                    28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50,
                                    52, 54, 56, 58}, run_at_startup=True),
        # Notifications: every 1 second pull, capped by global RPS.
        cron(send_due, second=set(range(0, 60)), run_at_startup=True),
        # Daily expirations at 03:30 UTC.
        cron(expire_loyalty_cards, hour={3}, minute={30}),
        cron(expire_prepaid_packages, hour={3}, minute={31}),
        cron(expire_wallet_entries, hour={3}, minute={32}),
    ]
    job_timeout = 60
    max_jobs = 20
    keep_result = 0
