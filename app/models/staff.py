"""Staff = employee (owner / barista) and RBAC tables."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, PhoneE164, TgId, UuidFk, UuidPk


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_staff_tenant_email"),
        CheckConstraint(
            "role IN ('owner','barista')",
            name="role_valid",
        ),
        CheckConstraint(
            "status IN ('active','suspended','left')", name="status_valid"
        ),
    )

    id: Mapped[UuidPk]
    tenant_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    phone_e164: Mapped[PhoneE164 | None] = mapped_column(String(20), nullable=True)  # type: ignore[assignment]
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    telegram_id: Mapped[TgId]

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )

    # Argon2 hashes (with HMAC-pepper applied before hashing — see core.security)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pin_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[CreatedAt]


class StaffBranch(Base):
    """Many-to-many: which branches an employee is allowed to operate on."""

    __tablename__ = "staff_branches"

    staff_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[UuidFk] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True
    )


class Role(Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True
    )
