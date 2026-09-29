"""Account-scoped in-app notifications and operational event synchronization.

The in-app inbox is always a first-party database feature. Native OS push is a
separate delivery channel and is never implied by this module.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.notification import Notification, NotificationPreference
from app.models.order import Order
from app.models.product import Product
from app.models.revenue import Revenue
from app.models.supplier import Supplier


VALID_NOTIFICATION_TYPES = {
    "major_announcement",
    "system",
    "order",
    "device",
    "revenue",
    "wallet",
}
PREFERENCE_BY_TYPE = {
    # A major announcement is still governed by the system-message preference
    # when created outside the administrator broadcast path. Administrator
    # broadcasts deliberately bypass optional preferences for every active
    # account and remain visible in the inbox audit trail.
    "major_announcement": "system_enabled",
    "system": "system_enabled",
    "order": "order_enabled",
    "device": "device_enabled",
    "revenue": "revenue_enabled",
    "wallet": "wallet_enabled",
}


def push_delivery_status() -> dict:
    provider = settings.PUSH_PROVIDER.strip()
    configured = bool(settings.PUSH_SERVICE_ENABLED and provider)
    return {
        "in_app_enabled": True,
        "system_push_configured": configured,
        "system_push_provider": provider if configured else None,
        "system_push_status": "configured" if configured else "pending_configuration",
    }


def get_or_create_preferences(db: Session, user_id: int) -> NotificationPreference:
    preferences = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    if preferences is None:
        preferences = NotificationPreference(user_id=user_id)
        db.add(preferences)
        db.flush()
    return preferences


def notification_type_enabled(db: Session, user_id: int, notification_type: str) -> bool:
    field = PREFERENCE_BY_TYPE.get(notification_type)
    if field is None:
        return False
    preferences = get_or_create_preferences(db, user_id)
    return bool(getattr(preferences, field))


def create_notification(
    db: Session,
    *,
    user_id: int,
    title: str,
    content: str | None = None,
    title_en: str | None = None,
    content_en: str | None = None,
    notification_type: str = "system",
    action_url: str | None = None,
    dedupe_key: str | None = None,
    respect_preferences: bool = True,
) -> Notification | None:
    """Add one notification to the caller's transaction.

    No commit is performed so a notice can never survive a rolled-back business
    event. A dedupe key makes background synchronization safely repeatable.
    """
    if notification_type not in VALID_NOTIFICATION_TYPES:
        raise ValueError(f"Unsupported notification type: {notification_type}")
    # Historical assets/orders must not recreate an inbox after account deletion.
    from app.services.account_lifecycle import try_lock_active_user
    if not try_lock_active_user(db, user_id):
        return None
    if respect_preferences and not notification_type_enabled(db, user_id, notification_type):
        return None
    if dedupe_key:
        existing = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.dedupe_key == dedupe_key,
        ).first()
        if existing:
            return existing
    notification = Notification(
        user_id=user_id,
        title=title,
        content=content,
        title_en=title_en,
        content_en=content_en,
        type=notification_type,
        action_url=action_url,
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    db.flush()
    return notification


def ensure_inbox_welcome(db: Session, user_id: int) -> Notification | None:
    push_configured = push_delivery_status()["system_push_configured"]
    content = (
        "站内通知和系统推送均已启用，您可以在通知设置中选择消息类型。"
        if push_configured
        else "站内通知已启用；App 关闭后的系统推送尚未配置。您可以在通知设置中选择消息类型。"
    )
    content_en = (
        "In-app notifications and system push are enabled. Choose message types in Notification Settings."
        if push_configured
        else "In-app notifications are enabled; system push while the app is closed is not configured yet. Choose message types in Notification Settings."
    )
    return create_notification(
        db,
        user_id=user_id,
        title="通知中心已启用",
        content=content,
        title_en="Notification center enabled",
        content_en=content_en,
        notification_type="system",
        dedupe_key="system:inbox-enabled:v1",
        # This is a one-time service state message. Creating it remains useful
        # even when the user later disables optional system announcements.
        respect_preferences=False,
    )


ORDER_STATUS_COPY = {
    "paid": ("订单待交付", "订单 {number} 已提交，正在等待商家交付。", "Order awaiting delivery", "Order {number} was submitted and is awaiting supplier delivery."),
    "delivering": ("订单已交付", "订单 {number} 已收到交付信息，请核对后确认。", "Order delivered", "Delivery information for order {number} is ready. Please review and confirm."),
    "completed": ("订单已完成", "订单 {number} 已确认完成。", "Order completed", "Order {number} has been completed."),
    "running": ("算力服务运行中", "订单 {number} 对应的算力服务正在运行。", "Compute service running", "The compute service for order {number} is running."),
    "canceled": ("订单已取消", "订单 {number} 已取消。", "Order canceled", "Order {number} has been canceled."),
    "done": ("订单已到期", "订单 {number} 已到期。", "Order expired", "Order {number} has expired."),
    "disputed": ("订单待处理", "订单 {number} 已进入待处理状态。", "Order requires attention", "Order {number} requires attention."),
}


def _sync_order_notifications(db: Session) -> int:
    created = 0
    # A bounded window prevents an old production database from being flooded
    # during its first upgraded startup. Future status changes remain in range.
    orders = db.query(Order).order_by(Order.id.desc()).limit(1000).all()
    product_ids = {order.product_id for order in orders}
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.id.in_(product_ids)).all()
    } if product_ids else {}
    supplier_ids = {int(p.supplier_id) for p in products.values() if p.supplier_id}
    suppliers = {
        supplier.id: supplier
        for supplier in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}
    for order in orders:
        copy = ORDER_STATUS_COPY.get(order.status)
        if copy:
            title, content, title_en, content_en = copy
            item = create_notification(
                db,
                user_id=order.user_id,
                title=title,
                content=content.format(number=order.order_no),
                title_en=title_en,
                content_en=content_en.format(number=order.order_no),
                notification_type="order",
                action_url=f"/pages/order/detail?id={order.id}",
                dedupe_key=f"order:{order.id}:{order.status}:buyer",
            )
            if item and item.id:
                created += 1
        if order.status == "paid":
            product = products.get(order.product_id)
            supplier = suppliers.get(int(product.supplier_id)) if product and product.supplier_id else None
            if supplier:
                item = create_notification(
                    db,
                    user_id=supplier.user_id,
                    title="有新的待交付订单",
                    content=f"订单 {order.order_no} 等待您交付算力资源。",
                    title_en="New order awaiting delivery",
                    content_en=f"Order {order.order_no} is awaiting compute resource delivery.",
                    notification_type="order",
                    action_url="/pages/supplier/orders",
                    dedupe_key=f"order:{order.id}:paid:supplier",
                )
                if item and item.id:
                    created += 1
    return created


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _sync_device_notifications(db: Session, now: datetime) -> int:
    created = 0
    assets = db.query(Asset).filter(Asset.end_at.isnot(None)).order_by(Asset.id.desc()).limit(1000).all()
    for asset in assets:
        end_at = _as_utc(asset.end_at)
        if asset.status == "expired" or end_at <= now:
            item = create_notification(
                db,
                user_id=asset.user_id,
                title="算力资产已到期",
                content=f"算力资产 #{asset.id} 已到期，请在设备状态中查看。",
                title_en="Compute asset expired",
                content_en=f"Compute asset #{asset.id} has expired. View it under Device Status.",
                notification_type="device",
                action_url=f"/pages/asset/detail?id={asset.id}",
                dedupe_key=f"asset:{asset.id}:expired",
            )
        elif end_at <= now + timedelta(days=3):
            item = create_notification(
                db,
                user_id=asset.user_id,
                title="算力资产即将到期",
                content=f"算力资产 #{asset.id} 将在 3 天内到期。",
                title_en="Compute asset expiring soon",
                content_en=f"Compute asset #{asset.id} will expire within 3 days.",
                notification_type="device",
                action_url=f"/pages/asset/detail?id={asset.id}",
                dedupe_key=f"asset:{asset.id}:expires-within-3d",
            )
        else:
            item = None
        if item and item.id:
            created += 1
    return created


def _sync_revenue_notifications(db: Session, today: date) -> int:
    created = 0
    totals = db.query(
        Revenue.user_id,
        func.coalesce(func.sum(Revenue.amount), 0),
    ).filter(Revenue.date == today).group_by(Revenue.user_id).all()
    for user_id, total in totals:
        amount = Decimal(str(total)).quantize(Decimal("0.001"))
        if amount <= 0:
            continue
        item = create_notification(
            db,
            user_id=user_id,
            title="今日收益已更新",
            content=f"今日已记录人民币 ¥{amount} 收益，可在收益中心查看明细。",
            title_en="Today's revenue updated",
            content_en=f"CNY ¥{amount} of revenue has been recorded today. View details in Revenue Center.",
            notification_type="revenue",
            action_url="/pages/revenue/index",
            dedupe_key=f"revenue:{today.isoformat()}:summary",
        )
        if item and item.id:
            created += 1
    return created


def sync_operational_notifications() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        created = (
            _sync_order_notifications(db)
            + _sync_device_notifications(db, now)
            + _sync_revenue_notifications(db, now.date())
        )
        db.commit()
        if created:
            print(f"[notifications] synchronized {created} in-app messages")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[notifications] synchronization error: {exc}")
    finally:
        db.close()
