"""Declarative base with shared column types and conventions."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import BigInteger, MetaData, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Postgres-friendly naming convention so Alembic produces stable names
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---- Reusable column types ---------------------------------------------------

# UUID v4 default. Postgres ``gen_random_uuid()`` is used at the DB level; we
# still let SQLAlchemy generate one client-side as fallback for ORM flushes.
UuidPk = Annotated[
    uuid.UUID,
    mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    ),
]

UuidFk = Annotated[uuid.UUID, mapped_column(UUID(as_uuid=True))]

CreatedAt = Annotated[
    datetime,
    mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
]

UpdatedAt = Annotated[
    datetime,
    mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
]

OptionalDt = Annotated[
    datetime | None,
    mapped_column(TIMESTAMP(timezone=True), nullable=True),
]

# Money: 12 digits total, 2 after the dot. NEVER use Float for money.
Money = Annotated[Decimal, mapped_column(Numeric(12, 2), nullable=False)]
OptionalMoney = Annotated[Decimal | None, mapped_column(Numeric(12, 2), nullable=True)]

# JSONB for flexible config (campaign rules, metadata, audit diffs)
JsonB = Annotated[
    dict,
    mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
]
OptionalJsonB = Annotated[dict | None, mapped_column(JSONB, nullable=True)]

# Telegram IDs are int64
TgId = Annotated[int | None, mapped_column(BigInteger, nullable=True)]

# E.164 phone: stored as TEXT, normalization is enforced in domain layer
PhoneE164 = Annotated[str, mapped_column(String(20), nullable=False)]
