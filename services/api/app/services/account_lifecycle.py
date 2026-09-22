"""Authentication/write fences required by account deletion, not commerce rules."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.response import BizError


def ensure_active_user(user: User | None) -> None:
    state = getattr(user, "account_status", "active") if user is not None else None
    if state in (None, "active") and user is not None:
        return
    if state == "suspended":
        raise BizError("账号已冻结，请联系客服", status_code=401)
    raise BizError("账号已注销或正在注销", status_code=401)


def lock_active_user(db: Session, user_id: int) -> None:
    # A conditional no-op UPDATE is a row lock on PostgreSQL and a write fence
    # on SQLite (where SELECT FOR UPDATE does not provide a lock). Call this
    # before checking obligations, and before authenticated transaction writes.
    if not try_lock_active_user(db, user_id):
        raise BizError("账号已注销或正在注销", status_code=401)


def try_lock_active_user(db: Session, user_id: int) -> bool:
    result = db.connection().execute(
        update(User.__table__).where(
            User.id == user_id, User.account_status == "active",
        ).values(account_status="active")
    )
    return result.rowcount == 1


def active_user_exists(db: Session, user_id: int) -> bool:
    return db.execute(select(User.id).where(
        User.id == user_id, User.account_status == "active",
    )).scalar_one_or_none() is not None


def fence_new_business_owners(db: Session) -> None:
    """A second participant must not create new work for a deleted account."""
    from app.models.product import Product
    from app.models.supplier import Supplier
    from app.models.buy_request import BuyRequest
    tables = {"orders", "assets", "order_renewals", "buy_requests", "buy_request_deals",
              "buy_request_quotes", "buy_request_quote_revisions", "suppliers", "products", "invite_records"}
    owners = set()
    for row in db.new:
        if getattr(row, "__tablename__", "") not in tables:
            continue
        for field in ("user_id", "buyer_id", "proposer_user_id", "inviter_id", "invitee_id"):
            value = getattr(row, field, None)
            if value is not None:
                owners.add(value)
        supplier_id = getattr(row, "supplier_id", None)
        product_id = getattr(row, "product_id", None)
        if product_id is not None:
            product_supplier = db.connection().execute(select(Product.supplier_id).where(Product.id == product_id)).scalar()
            supplier_id = supplier_id or product_supplier
        if supplier_id is not None:
            owner = db.connection().execute(select(Supplier.user_id).where(Supplier.id == supplier_id)).scalar()
            if owner is not None:
                owners.add(owner)
        request_id = getattr(row, "buy_request_id", None)
        if request_id is not None:
            owner = db.connection().execute(select(BuyRequest.user_id).where(BuyRequest.id == request_id)).scalar()
            if owner is not None:
                owners.add(owner)
    for owner in sorted(owners):
        lock_active_user(db, owner)
