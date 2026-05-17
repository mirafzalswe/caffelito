"""Domain-level exceptions. They map to user-friendly bot/API messages.

Every error has a stable ``code`` (used for i18n & metrics) and a default
human message; service callers may override the message with extra context.
"""

from __future__ import annotations


class DomainError(Exception):
    code: str = "domain_error"
    message: str = "Domain error"
    http_status: int = 400

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


# ---- identity ----------------------------------------------------------------


class UserNotFound(DomainError):
    code = "user_not_found"
    message = "User not found"
    http_status = 404


class UserBlocked(DomainError):
    code = "user_blocked"
    message = "User is blocked"
    http_status = 403


class TelegramConflict(DomainError):
    """Phone exists, but linked to a different telegram_id."""

    code = "telegram_conflict"
    message = "Phone is already linked to another Telegram account"
    http_status = 409


# ---- loyalty / wallet --------------------------------------------------------


class CampaignNotApplicable(DomainError):
    code = "campaign_not_applicable"
    message = "No applicable campaign"


class FreeCoffeeNotAvailable(DomainError):
    code = "free_coffee_not_available"
    message = "No free coffee available"


class FreeCoffeeExpired(DomainError):
    code = "free_coffee_expired"
    message = "Free coffee has expired"


class PrepaidNotFound(DomainError):
    code = "prepaid_not_found"
    message = "No active prepaid package"


class PrepaidExhausted(DomainError):
    code = "prepaid_exhausted"
    message = "Prepaid package is exhausted"


class InsufficientCashback(DomainError):
    code = "insufficient_cashback"
    message = "Not enough cashback balance"


class CooldownActive(DomainError):
    code = "cooldown_active"
    message = "Action too frequent — try again in a moment"


class IdempotencyConflict(DomainError):
    """Same idempotency key used with different payload."""

    code = "idempotency_conflict"
    message = "Conflicting request with the same idempotency key"
    http_status = 409


class ConcurrentUpdate(DomainError):
    """Optimistic lock failed — another transaction touched the row first."""

    code = "concurrent_update"
    message = "Concurrent update; retry the operation"
    http_status = 409


# ---- refund -----------------------------------------------------------------


class TransactionNotFound(DomainError):
    code = "transaction_not_found"
    message = "Transaction not found"
    http_status = 404


class RefundNotAllowed(DomainError):
    code = "refund_not_allowed"
    message = "Transaction cannot be refunded"
    http_status = 409


# ---- access ------------------------------------------------------------------


class PermissionDenied(DomainError):
    code = "permission_denied"
    message = "Permission denied"
    http_status = 403


class StaffNotAssignedToBranch(PermissionDenied):
    code = "staff_branch_denied"
    message = "Staff is not assigned to this branch"
