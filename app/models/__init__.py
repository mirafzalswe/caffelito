"""SQLAlchemy ORM models. Importing this package registers all tables on Base.metadata."""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.branch import Branch
from app.models.broadcast import Broadcast
from app.models.campaign import Campaign, CampaignBranch, CampaignProduct
from app.models.ledger import LedgerEntry
from app.models.loyalty import LoyaltyCard, PrepaidPackage
from app.models.membership import Membership
from app.models.notification import NotificationJob, NotificationTemplate
from app.models.outbox import OutboxEvent
from app.models.product import Product
from app.models.staff import Permission, Role, RolePermission, Staff, StaffBranch
from app.models.tenant import Tenant
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User, UserDashboard
from app.models.wallet import CashbackWallet, WalletEntry

__all__ = [
    "AuditLog",
    "Base",
    "Branch",
    "Broadcast",
    "Campaign",
    "CampaignBranch",
    "CampaignProduct",
    "CashbackWallet",
    "LedgerEntry",
    "LoyaltyCard",
    "Membership",
    "NotificationJob",
    "NotificationTemplate",
    "OutboxEvent",
    "Permission",
    "PrepaidPackage",
    "Product",
    "Role",
    "RolePermission",
    "Staff",
    "StaffBranch",
    "Tenant",
    "Transaction",
    "TransactionItem",
    "User",
    "UserDashboard",
    "WalletEntry",
]
