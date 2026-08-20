from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BuyRequestQuote,
    InventoryReservation,
    MerchantServer,
    Order,
    Product,
    ProductPriceVersion,
    ProductReviewEvent,
    SupplierApplication,
    User,
)
from app.config import settings
from app.resource_schemas import ResourceCreateIn, ResourceUpdateIn
from app.security import ApiError
from app.services.internal_modules import create_notification
from app.services import agents as agent_service


OCCUPYING_RESERVATION_STATUSES = ("reserved", "allocated")
RESOURCE_STATUSES = ("draft", "pending_review", "approved", "published", "rejected", "archived")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resource_number() -> str:
    return f"PR{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _reservation_number() -> str:
    return f"IR{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _server_number() -> str:
    return f"SV{_now():%Y%m%d}{uuid4().hex[:12].upper()}"


def _money(value: Decimal) -> str:
    return format(value, "f")


def _require_approved_supplier(db: Session, user: User) -> SupplierApplication:
    if user.role != "supplier":
        raise ApiError("SUPPLIER_REQUIRED", "仅商家可以管理算力资源", 403)
    application = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == user.id,
        SupplierApplication.status == "approved",
    ).first()
    if application is None:
        raise ApiError("SUPPLIER_APPROVAL_REQUIRED", "商家申请审核通过后才能管理资源", 403)
    return application


def _check_version(row: Product | InventoryReservation, version: int, code: str) -> None:
    if row.version != version:
        raise ApiError(code, "数据已被更新，请刷新后重试", 409)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError("RESOURCE_CONFLICT", "资源数据发生冲突，请刷新后重试", 409) from exc


def reserved_quantity(db: Session, product_id: int) -> int:
    value = db.query(func.coalesce(func.sum(InventoryReservation.quantity), 0)).filter(
        InventoryReservation.product_id == product_id,
        InventoryReservation.status.in_(OCCUPYING_RESERVATION_STATUSES),
    ).scalar()
    return int(value or 0)


def reserved_quantities(db: Session, product_ids: list[int]) -> dict[int, int]:
    """Load reservation totals for a product list in one query."""
    if not product_ids:
        return {}
    rows = db.query(
        InventoryReservation.product_id,
        func.coalesce(func.sum(InventoryReservation.quantity), 0),
    ).filter(
        InventoryReservation.product_id.in_(product_ids),
        InventoryReservation.status.in_(OCCUPYING_RESERVATION_STATUSES),
    ).group_by(InventoryReservation.product_id).all()
    return {int(product_id): int(quantity or 0) for product_id, quantity in rows}


def available_quantity(db: Session, product: Product) -> int:
    return max(product.total_quantity - reserved_quantity(db, product.id), 0)


def resource_out(db: Session, row: Product, *, include_review: bool = True) -> dict:
    reserved = reserved_quantity(db, row.id)
    server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).first()
    if server is not None:
        agent_service.refresh_presence(server)
    data = {
        "id": row.id,
        "resource_no": row.resource_no,
        "name": row.name,
        "gpu_model": row.gpu_model,
        "gpu_memory_gb": row.gpu_memory_gb,
        "memory": row.memory,
        "region": row.region,
        "cpu_cores": row.cpu_cores,
        "ram_gb": row.ram_gb,
        "disk_gb": row.disk_gb,
        "bandwidth_mbps": row.bandwidth_mbps,
        "image_url": row.image_url,
        "description": row.description,
        "price": {
            "amount": _money(row.unit_price),
            "currency": row.price_currency,
            "unit": row.price_unit,
        },
        "total_quantity": row.total_quantity,
        "reserved_quantity": reserved,
        "available_quantity": max(row.total_quantity - reserved, 0),
        "status": row.status,
        "published_at": row.published_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
        "server": ({
            "id": server.id,
            "server_no": server.server_no,
            "public_host": server.public_host,
            "ssh_port": server.ssh_port,
            "ssh_username": server.ssh_username,
            "status": server.status,
            "agent_mode": server.agent_mode,
            "agent_version": server.agent_version,
            "agent_device_id": server.agent_device_id,
            "agent_platform": server.agent_platform,
            "agent_arch": server.agent_arch,
            "agent_hostname": server.agent_hostname,
            "agent_enrolled_at": server.agent_enrolled_at,
            "last_seen_at": server.last_seen_at,
            "hardware": agent_service.hardware_out(server),
            "services": agent_service.service_out(server),
        } if server else None),
    }
    if include_review:
        data.update({
            "review_note": row.review_note,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
        })
    return data


def _event(
    db: Session,
    row: Product,
    actor: User,
    *,
    event_type: str,
    previous: str | None,
    target: str,
    note: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(ProductReviewEvent(
        product_id=row.id,
        actor_user_id=actor.id,
        actor_role=actor.role,
        event_type=event_type,
        from_status=previous,
        to_status=target,
        note=note,
        payload=payload or {},
    ))


def _price_version(
    db: Session,
    row: Product,
    actor: User,
    note: str | None,
) -> None:
    next_version = int(db.query(func.coalesce(func.max(ProductPriceVersion.version), 0)).filter(
        ProductPriceVersion.product_id == row.id
    ).scalar() or 0) + 1
    db.add(ProductPriceVersion(
        product_id=row.id,
        version=next_version,
        amount=row.unit_price,
        currency=row.price_currency,
        price_unit=row.price_unit,
        changed_by=actor.id,
        change_note=note,
    ))


def create_resource(db: Session, user: User, data: ResourceCreateIn) -> Product:
    application = _require_approved_supplier(db, user)
    if data.agent_mode == "local_simulator" and not settings.AGENT_LOCAL_SIMULATOR_ENABLED:
        raise ApiError("LOCAL_AGENT_DISABLED", "生产环境不允许使用本机 Agent 模拟器", 409)
    row = Product(
        resource_no=_resource_number(),
        supplier_id=user.id,
        name=data.name,
        gpu_model=data.gpu_model,
        memory=f"{data.gpu_memory_gb} GB",
        gpu_memory_gb=data.gpu_memory_gb,
        region=data.region,
        cpu_cores=data.cpu_cores,
        ram_gb=data.ram_gb,
        disk_gb=data.disk_gb,
        bandwidth_mbps=data.bandwidth_mbps,
        image_url=data.image_url,
        description=data.description,
        unit_price=data.price_amount,
        price_currency=data.price_currency,
        price_unit=data.price_unit,
        total_quantity=1,
        source_name=application.company_name,
        status="draft",
        version=1,
    )
    db.add(row)
    db.flush()
    now = _now()
    server = MerchantServer(
        server_no=_server_number(),
        supplier_id=user.id,
        product_id=row.id,
        public_host=data.public_host.strip(),
        ssh_port=data.ssh_port,
        ssh_username=data.ssh_username,
        status="online" if data.agent_mode == "local_simulator" else "registered",
        agent_mode=data.agent_mode,
        agent_version="local-simulator/1.0" if data.agent_mode == "local_simulator" else None,
        last_seen_at=now if data.agent_mode == "local_simulator" else None,
        version=1,
    )
    db.add(server)
    db.flush()
    if data.agent_mode == "local_simulator":
        agent_service.apply_hardware_inventory(
            db, server, row, agent_service.synthetic_inventory(row, observed_at=now), observed_at=now
        )
    _price_version(db, row, user, "初始价格")
    _event(db, row, user, event_type="created", previous=None, target="draft")
    _commit(db)
    db.refresh(row)
    return row


def list_supplier_resources(
    db: Session, user: User, *, page: int, page_size: int, status: str | None
) -> tuple[list[Product], int]:
    _require_approved_supplier(db, user)
    query = db.query(Product).filter(Product.supplier_id == user.id)
    if status:
        query = query.filter(Product.status == status)
    total = query.count()
    rows = query.order_by(Product.updated_at.desc(), Product.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return rows, total


def _owned_resource(db: Session, user: User, resource_id: int, *, lock: bool = False) -> Product:
    _require_approved_supplier(db, user)
    query = db.query(Product).filter(
        Product.id == resource_id, Product.supplier_id == user.id
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("RESOURCE_NOT_FOUND", "算力资源不存在", 404)
    return row


def get_supplier_resource(db: Session, user: User, resource_id: int) -> Product:
    return _owned_resource(db, user, resource_id)


def update_resource(
    db: Session, user: User, resource_id: int, data: ResourceUpdateIn
) -> Product:
    row = _owned_resource(db, user, resource_id, lock=True)
    _check_version(row, data.version, "RESOURCE_VERSION_CONFLICT")
    if row.status in ("pending_review", "published", "archived"):
        raise ApiError("RESOURCE_NOT_EDITABLE", "待审核、已发布或已归档资源不能直接编辑", 409)
    values = data.model_dump(exclude_unset=True)
    values.pop("version", None)
    change_note = values.pop("change_note", None)
    server_values = {
        key: values.pop(key)
        for key in ("public_host", "ssh_port", "ssh_username", "agent_mode")
        if key in values
    }
    if server_values.get("agent_mode") == "local_simulator" and not settings.AGENT_LOCAL_SIMULATOR_ENABLED:
        raise ApiError("LOCAL_AGENT_DISABLED", "生产环境不允许使用本机 Agent 模拟器", 409)
    new_total = values.get("total_quantity", row.total_quantity)
    occupied = reserved_quantity(db, row.id)
    if new_total < occupied:
        raise ApiError("RESOURCE_QUANTITY_BELOW_RESERVED", "总容量不能低于已预留数量", 409)
    price_changed = any(key in values for key in ("price_amount", "price_currency", "price_unit"))
    mapping = {
        "price_amount": "unit_price",
        "price_currency": "price_currency",
        "price_unit": "price_unit",
        "total_quantity": "total_quantity",
    }
    for key, value in values.items():
        setattr(row, mapping.get(key, key), value)
    server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).with_for_update().first()
    if server is None:
        raise ApiError("SERVER_REGISTRATION_MISSING", "资源缺少服务器接入信息", 409)
    for key, value in server_values.items():
        setattr(server, key, value.strip() if isinstance(value, str) else value)
    if server_values:
        if server.agent_mode == "local_simulator":
            server.status = "online"
            server.agent_version = "local-simulator/1.0"
            server.last_seen_at = _now()
            agent_service.apply_hardware_inventory(
                db,
                server,
                row,
                agent_service.synthetic_inventory(row, observed_at=server.last_seen_at),
                observed_at=server.last_seen_at,
            )
        else:
            server.status = "registered"
            server.agent_version = None
            server.last_seen_at = None
            server.hardware_inventory = {}
            server.hardware_inventory_hash = None
            server.hardware_observed_at = None
            server.hardware_verified_at = None
            server.hardware_verification_status = "pending"
            server.hardware_mismatches = []
        server.version += 1
    elif server.agent_mode == "local_simulator":
        agent_service.apply_hardware_inventory(
            db,
            server,
            row,
            agent_service.synthetic_inventory(row, observed_at=_now()),
        )
    elif server.hardware_inventory:
        agent_service.apply_hardware_inventory(db, server, row, server.hardware_inventory)
    if "gpu_memory_gb" in values:
        row.memory = f"{row.gpu_memory_gb} GB"
    previous = row.status
    row.status = "draft"
    row.review_note = None
    row.reviewed_by = None
    row.reviewed_at = None
    row.version += 1
    if price_changed:
        _price_version(db, row, user, change_note or "商家更新价格")
    _event(
        db,
        row,
        user,
        event_type="updated",
        previous=previous,
        target="draft",
        note=change_note,
        payload={"fields": sorted(values)},
    )
    _commit(db)
    db.refresh(row)
    return row


def delete_resource(db: Session, user: User, resource_id: int, version: int) -> None:
    row = _owned_resource(db, user, resource_id, lock=True)
    _check_version(row, version, "RESOURCE_VERSION_CONFLICT")
    if row.status not in ("draft", "rejected"):
        raise ApiError("RESOURCE_NOT_DELETABLE", "只有草稿或已驳回资源可以删除", 409)
    has_links = db.query(BuyRequestQuote.id).filter(
        BuyRequestQuote.resource_id == row.id
    ).first() or db.query(InventoryReservation.id).filter(
        InventoryReservation.product_id == row.id
    ).first()
    if has_links:
        raise ApiError("RESOURCE_HAS_HISTORY", "资源已有报价或库存记录，不能删除", 409)
    db.query(ProductReviewEvent).filter(ProductReviewEvent.product_id == row.id).delete()
    db.query(ProductPriceVersion).filter(ProductPriceVersion.product_id == row.id).delete()
    db.query(MerchantServer).filter(MerchantServer.product_id == row.id).delete()
    db.delete(row)
    _commit(db)


def transition_supplier_resource(
    db: Session,
    user: User,
    resource_id: int,
    *,
    action: str,
    version: int,
    note: str | None,
) -> Product:
    row = _owned_resource(db, user, resource_id, lock=True)
    _check_version(row, version, "RESOURCE_VERSION_CONFLICT")
    transitions = {
        "submit-review": (("draft", "rejected"), "pending_review", "submitted_for_review"),
        "withdraw-review": (("pending_review",), "draft", "review_withdrawn"),
        "publish": (("approved",), "published", "published"),
        "unpublish": (("published",), "approved", "unpublished"),
    }
    allowed, target, event_type = transitions[action]
    if row.status not in allowed:
        raise ApiError("RESOURCE_TRANSITION_INVALID", "当前资源状态不能执行此操作", 409)
    if action == "publish":
        server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).first()
        if server is None:
            raise ApiError("SERVER_REGISTRATION_MISSING", "资源缺少服务器接入信息", 409)
        agent_service.refresh_presence(server)
        if server.status != "online":
            raise ApiError("SERVER_AGENT_OFFLINE", "服务器 Agent 在线后才能发布", 409)
        if not agent_service.hardware_is_current(server):
            raise ApiError("SERVER_HARDWARE_NOT_VERIFIED", "Agent 实测配置通过核验后才能发布", 409)
        if not agent_service.service_is_current(server):
            raise ApiError("SERVER_SSH_NOT_READY", "Agent SSH 服务自检通过后才能发布", 409)
    previous = row.status
    row.status = target
    row.version += 1
    if target == "published":
        row.published_at = _now()
        row.source_observed_at = row.published_at
    elif action == "unpublish":
        row.published_at = None
    _event(db, row, user, event_type=event_type, previous=previous, target=target, note=note)
    _commit(db)
    db.refresh(row)
    return row


def list_admin_resources(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: str | None,
    search: str | None,
) -> tuple[list[tuple[Product, User, SupplierApplication | None]], int]:
    query = db.query(Product, User, SupplierApplication).join(
        User, User.id == Product.supplier_id
    ).outerjoin(SupplierApplication, SupplierApplication.user_id == User.id)
    if status:
        query = query.filter(Product.status == status)
    if search:
        value = f"%{search.strip()}%"
        query = query.filter(or_(
            Product.resource_no.ilike(value),
            Product.name.ilike(value),
            Product.gpu_model.ilike(value),
            SupplierApplication.company_name.ilike(value),
        ))
    total = query.count()
    rows = query.order_by(Product.updated_at.desc(), Product.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return rows, total


def review_resource(
    db: Session,
    admin: User,
    resource_id: int,
    *,
    action: str,
    version: int,
    note: str | None,
) -> Product:
    row = db.query(Product).filter(Product.id == resource_id).with_for_update().first()
    if row is None:
        raise ApiError("RESOURCE_NOT_FOUND", "算力资源不存在", 404)
    _check_version(row, version, "RESOURCE_VERSION_CONFLICT")
    if row.status != "pending_review":
        raise ApiError("RESOURCE_NOT_REVIEWABLE", "当前资源不在待审核状态", 409)
    server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).first()
    if action == "approve":
        if server is None:
            raise ApiError("SERVER_AGENT_OFFLINE", "服务器 Agent 在线后才能审核发布", 409)
        agent_service.refresh_presence(server)
        if server.status != "online":
            raise ApiError("SERVER_AGENT_OFFLINE", "服务器 Agent 在线后才能审核发布", 409)
        if not agent_service.hardware_is_current(server):
            raise ApiError(
                "SERVER_HARDWARE_NOT_VERIFIED",
                "Agent 实测配置尚未通过核验，请检查申报配置与检测结果",
                409,
            )
        if not agent_service.service_is_current(server):
            raise ApiError(
                "SERVER_SSH_NOT_READY",
                "Agent 未能确认本机 SSH 服务可用",
                409,
            )
    previous = row.status
    target = "published" if action == "approve" else "rejected"
    row.status = target
    row.review_note = note
    row.reviewed_by = admin.id
    row.reviewed_at = _now()
    if target == "published":
        row.published_at = row.reviewed_at
        row.source_observed_at = row.reviewed_at
    row.version += 1
    _event(
        db,
        row,
        admin,
        event_type="review_approved_and_published" if action == "approve" else "review_rejected",
        previous=previous,
        target=target,
        note=note,
    )
    if row.supplier_id is not None:
        create_notification(
            db,
            user_id=row.supplier_id,
            category="review",
            title="算力资源审核已更新",
            body=f"资源 {row.resource_no} 已{('通过审核并自动发布' if target == 'published' else '被驳回')}。",
            action_path="/supplier/resources",
        )
    _commit(db)
    db.refresh(row)
    return row


def price_versions(db: Session, user: User, resource_id: int) -> list[ProductPriceVersion]:
    _owned_resource(db, user, resource_id)
    return db.query(ProductPriceVersion).filter(
        ProductPriceVersion.product_id == resource_id
    ).order_by(ProductPriceVersion.version.desc()).all()


def review_events(db: Session, resource_id: int) -> list[ProductReviewEvent]:
    return db.query(ProductReviewEvent).filter(
        ProductReviewEvent.product_id == resource_id
    ).order_by(ProductReviewEvent.created_at.asc(), ProductReviewEvent.id.asc()).all()


def review_event_out(row: ProductReviewEvent) -> dict:
    return {
        "id": row.id,
        "actor_role": row.actor_role,
        "event_type": row.event_type,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "note": row.note,
        "payload": row.payload or {},
        "created_at": row.created_at,
    }


def price_version_out(row: ProductPriceVersion) -> dict:
    return {
        "id": row.id,
        "version": row.version,
        "amount": _money(row.amount),
        "currency": row.currency,
        "unit": row.price_unit,
        "change_note": row.change_note,
        "created_at": row.created_at,
    }


def ensure_quote_resource(
    db: Session, supplier: User, resource_id: int, quantity: int, gpu_model: str
) -> Product:
    if quantity != 1:
        raise ApiError(
            "DEDICATED_SERVER_QUANTITY_INVALID",
            "一条服务器商品只能对应一台独占服务器；多台需求请分别关联商品或不绑定商品报价",
            409,
        )
    row = db.query(Product).filter(
        Product.id == resource_id,
        Product.supplier_id == supplier.id,
        Product.status == "published",
    ).first()
    if row is None:
        raise ApiError("QUOTE_RESOURCE_NOT_AVAILABLE", "关联资源不存在或尚未发布", 409)
    if available_quantity(db, row) < quantity:
        raise ApiError("QUOTE_RESOURCE_QUANTITY_INSUFFICIENT", "关联资源可用数量不足", 409)
    if row.gpu_model.strip().casefold() != gpu_model.strip().casefold():
        raise ApiError("QUOTE_RESOURCE_SPEC_MISMATCH", "关联资源的 GPU 型号与求购不一致", 409)
    return row


def reserve_for_order(
    db: Session, order: Order, product_id: int, quantity: int
) -> InventoryReservation:
    if quantity != 1:
        raise ApiError("DEDICATED_SERVER_QUANTITY_INVALID", "独占服务器订单数量必须为 1", 409)
    existing = db.query(InventoryReservation).filter(
        InventoryReservation.order_id == order.id
    ).first()
    if existing is not None:
        return existing
    product = db.query(Product).filter(Product.id == product_id).with_for_update().first()
    if product is None or product.status != "published" or product.supplier_id != order.supplier_id:
        raise ApiError("ORDER_RESOURCE_UNAVAILABLE", "订单关联资源当前不可用", 409)
    if available_quantity(db, product) < quantity:
        raise ApiError("ORDER_RESOURCE_QUANTITY_INSUFFICIENT", "订单关联资源可用容量不足", 409)
    reservation = InventoryReservation(
        reservation_no=_reservation_number(),
        product_id=product.id,
        order_id=order.id,
        supplier_id=order.supplier_id,
        quantity=quantity,
        status="reserved",
        version=1,
    )
    db.add(reservation)
    db.flush()
    return reservation


def release_for_order(db: Session, order_id: int, reason: str) -> InventoryReservation | None:
    row = db.query(InventoryReservation).filter(
        InventoryReservation.order_id == order_id
    ).with_for_update().first()
    if row is None or row.status == "released":
        return row
    row.status = "released"
    row.release_reason = reason
    row.released_at = _now()
    row.version += 1
    return row


def allocate_for_order(db: Session, order_id: int) -> InventoryReservation | None:
    row = db.query(InventoryReservation).filter(
        InventoryReservation.order_id == order_id
    ).with_for_update().first()
    if row is None or row.status == "allocated":
        return row
    if row.status != "reserved":
        raise ApiError("INVENTORY_RESERVATION_NOT_ACTIVE", "库存预留当前不可分配", 409)
    row.status = "allocated"
    row.allocated_at = _now()
    row.version += 1
    return row


def list_reservations(
    db: Session, user: User, *, page: int, page_size: int, status: str | None
) -> tuple[list[tuple[InventoryReservation, Product, Order]], int]:
    _require_approved_supplier(db, user)
    query = db.query(InventoryReservation, Product, Order).join(
        Product, Product.id == InventoryReservation.product_id
    ).join(Order, Order.id == InventoryReservation.order_id).filter(
        InventoryReservation.supplier_id == user.id
    )
    if status:
        query = query.filter(InventoryReservation.status == status)
    total = query.count()
    rows = query.order_by(InventoryReservation.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return rows, total


def reservation_out(row: InventoryReservation, product: Product, order: Order) -> dict:
    return {
        "id": row.id,
        "reservation_no": row.reservation_no,
        "product_id": row.product_id,
        "resource_no": product.resource_no,
        "resource_name": product.name,
        "order_id": row.order_id,
        "order_no": order.order_no,
        "quantity": row.quantity,
        "status": row.status,
        "release_reason": row.release_reason,
        "reserved_at": row.reserved_at,
        "allocated_at": row.allocated_at,
        "released_at": row.released_at,
        "version": row.version,
    }


def release_reservation(
    db: Session, user: User, reservation_id: int, *, version: int, reason: str
) -> InventoryReservation:
    _require_approved_supplier(db, user)
    row = db.query(InventoryReservation).filter(
        InventoryReservation.id == reservation_id,
        InventoryReservation.supplier_id == user.id,
    ).with_for_update().first()
    if row is None:
        raise ApiError("INVENTORY_RESERVATION_NOT_FOUND", "库存预留不存在", 404)
    _check_version(row, version, "INVENTORY_VERSION_CONFLICT")
    if row.status == "released":
        return row
    order = db.get(Order, row.order_id)
    if order is None or order.status not in ("completed", "cancelled"):
        raise ApiError("INVENTORY_RELEASE_NOT_ALLOWED", "订单完成或取消后才能释放库存", 409)
    row.status = "released"
    row.release_reason = reason
    row.released_at = _now()
    row.version += 1
    _commit(db)
    db.refresh(row)
    return row
