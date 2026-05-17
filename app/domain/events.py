"""Domain event types written to outbox. Plain dicts for portability."""

from __future__ import annotations

from typing import Any, Final

# Aggregate types
AGG_USER: Final = "user"
AGG_TRANSACTION: Final = "transaction"
AGG_LOYALTY_CARD: Final = "loyalty_card"
AGG_PREPAID: Final = "prepaid_package"
AGG_WALLET: Final = "cashback_wallet"

# Event types
EVT_USER_LINKED: Final = "UserLinked"
EVT_USER_CREATED: Final = "UserCreated"
EVT_PURCHASE_RECORDED: Final = "PurchaseRecorded"
EVT_FREE_UNLOCKED: Final = "FreeCoffeeUnlocked"
EVT_FREE_REDEEMED: Final = "FreeCoffeeRedeemed"
EVT_PREPAID_OPENED: Final = "PrepaidPackageOpened"
EVT_PREPAID_CONSUMED: Final = "PrepaidConsumed"
EVT_PREPAID_EXHAUSTED: Final = "PrepaidExhausted"
EVT_CASHBACK_EARNED: Final = "CashbackEarned"
EVT_CASHBACK_SPENT: Final = "CashbackSpent"
EVT_TRANSACTION_REFUNDED: Final = "TransactionRefunded"


def make(type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Lightweight event factory; we keep events as plain dicts for outbox.

    Consumers should treat unknown fields as ignorable to allow forward
    compatibility.
    """
    return {"type": type_, "payload": payload}
