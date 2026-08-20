"""Idempotent local-development data for the procurement workflow."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db import SessionLocal
from app.models import (
    AccessLease,
    AgentCommand,
    BuyRequest,
    BuyRequestContact,
    BuyRequestEvent,
    BuyRequestQuote,
    CloudComputeRequestDetail,
    InventoryReservation,
    KycApplication,
    LedgerEntry,
    LedgerJournal,
    MerchantServer,
    Order,
    OrderEvent,
    PaymentIntent,
    Product,
    ProductPriceVersion,
    ProductReviewEvent,
    SandboxInstance,
    Session as LoginSession,
    SupplierApplication,
    SupplierApplicationEvent,
    User,
)
from app.security import hash_password


SEED_PASSWORD = "KaiDev#2026-E2E!"
BUYER_EMAIL = "dev-buyer-e2e@example.com"
SUPPLIER_EMAIL = "dev-supplier-e2e@example.com"
ADMIN_EMAIL = "dev-seed-admin@example.com"
DEMO_REQUEST_NO = "BRDEVDEMO0000001"
DEMO_QUOTE_NO = "BQDEVDEMO0000001"
E2E_REQUEST_NO = "BRDEVE2E000000001"
ORDER_DEMO_REQUEST_NO = "BRDEVORDER0000001"
ORDER_DEMO_QUOTE_NO = "BQDEVORDER0000001"
DEMO_ORDER_NO = "KAIDEVORDER000001"
DEMO_RESOURCE_NO = "PRDEVDEMO0000001"
E2E_RESOURCE_NO = "PRDEVE2E00000001"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_user(
    db: OrmSession,
    *,
    email: str,
    display_name: str,
    role: str,
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, display_name=display_name)
        db.add(user)
    user.display_name = display_name
    user.password_hash = hash_password(SEED_PASSWORD)
    user.email_verified = True
    user.role = role
    user.status = "active"
    db.flush()
    return user


def _remove_seed_request(db: OrmSession, request_no: str) -> None:
    request = db.query(BuyRequest).filter(BuyRequest.request_no == request_no).first()
    if request is None:
        return
    order_ids = [
        row[0]
        for row in db.query(Order.id).filter(Order.buy_request_id == request.id).all()
    ]
    if order_ids:
        db.query(InventoryReservation).filter(
            InventoryReservation.order_id.in_(order_ids)
        ).delete(synchronize_session=False)
        db.query(OrderEvent).filter(OrderEvent.order_id.in_(order_ids)).delete(
            synchronize_session=False
        )
        db.query(Order).filter(Order.id.in_(order_ids)).delete(synchronize_session=False)
    db.query(BuyRequestEvent).filter(
        BuyRequestEvent.buy_request_id == request.id
    ).delete(synchronize_session=False)
    db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == request.id
    ).delete(synchronize_session=False)
    db.query(BuyRequestContact).filter(
        BuyRequestContact.buy_request_id == request.id
    ).delete(synchronize_session=False)
    db.query(CloudComputeRequestDetail).filter(
        CloudComputeRequestDetail.buy_request_id == request.id
    ).delete(synchronize_session=False)
    db.delete(request)
    db.flush()


def _remove_seed_resource(db: OrmSession, resource_no: str) -> None:
    resource = db.query(Product).filter(Product.resource_no == resource_no).first()
    if resource is None:
        return
    direct_order_ids = [
        row[0]
        for row in db.query(Order.id).filter(Order.product_id == resource.id).all()
    ]
    if direct_order_ids:
        lease_ids = [row[0] for row in db.query(AccessLease.id).filter(
            AccessLease.order_id.in_(direct_order_ids)
        ).all()]
        if lease_ids:
            db.query(AgentCommand).filter(AgentCommand.lease_id.in_(lease_ids)).delete(synchronize_session=False)
            db.query(AccessLease).filter(AccessLease.id.in_(lease_ids)).delete(synchronize_session=False)
        journal_ids = [
            row[0]
            for row in db.query(LedgerJournal.id).filter(
                LedgerJournal.reference_type == "sandbox_order",
                LedgerJournal.reference_id.in_([str(item) for item in direct_order_ids]),
            ).all()
        ]
        if journal_ids:
            db.query(LedgerEntry).filter(LedgerEntry.journal_id.in_(journal_ids)).delete(synchronize_session=False)
            db.query(LedgerJournal).filter(LedgerJournal.id.in_(journal_ids)).delete(synchronize_session=False)
        db.query(PaymentIntent).filter(PaymentIntent.order_id.in_(direct_order_ids)).delete(synchronize_session=False)
        db.query(SandboxInstance).filter(SandboxInstance.order_id.in_(direct_order_ids)).delete(synchronize_session=False)
        db.query(InventoryReservation).filter(InventoryReservation.order_id.in_(direct_order_ids)).delete(synchronize_session=False)
        db.query(OrderEvent).filter(OrderEvent.order_id.in_(direct_order_ids)).delete(synchronize_session=False)
        db.query(Order).filter(Order.id.in_(direct_order_ids)).delete(synchronize_session=False)
    db.query(ProductReviewEvent).filter(
        ProductReviewEvent.product_id == resource.id
    ).delete(synchronize_session=False)
    db.query(ProductPriceVersion).filter(
        ProductPriceVersion.product_id == resource.id
    ).delete(synchronize_session=False)
    db.query(MerchantServer).filter(MerchantServer.product_id == resource.id).delete(synchronize_session=False)
    db.delete(resource)
    db.flush()


def _seed_resource(
    db: OrmSession,
    *,
    resource_no: str,
    supplier: User,
    admin: User,
    status: str,
    name: str,
    now: datetime,
) -> Product:
    row = Product(
        resource_no=resource_no,
        supplier_id=supplier.id,
        name=name,
        gpu_model="H100",
        memory="80 GB",
        gpu_memory_gb=80,
        region="CN-SH",
        cpu_cores=64,
        ram_gb=512,
        disk_gb=2048,
        bandwidth_mbps=1000,
        description="H100 独占算力资源，支持 CUDA 12.4 与容器交付。",
        unit_price=Decimal("24.000000"),
        price_currency="CNY",
        price_unit="server_hour",
        total_quantity=1,
        source_name="KAI 开发算力供应商",
        status=status,
        review_note="开发种子自动批准" if status == "published" else None,
        reviewed_by=admin.id if status == "published" else None,
        reviewed_at=now if status == "published" else None,
        published_at=now if status == "published" else None,
        source_observed_at=now if status == "published" else None,
        version=3 if status == "published" else 2,
    )
    db.add(row)
    db.flush()
    db.add(MerchantServer(
        server_no=f"SV{resource_no[2:]}",
        supplier_id=supplier.id,
        product_id=row.id,
        public_host="127.0.0.1",
        ssh_port=22,
        ssh_username="kai",
        status="online",
        agent_mode="local_simulator",
        agent_version="local-simulator/1.0",
        last_seen_at=now,
        version=1,
    ))
    db.add(ProductPriceVersion(
        product_id=row.id,
        version=1,
        amount=row.unit_price,
        currency=row.price_currency,
        price_unit=row.price_unit,
        changed_by=supplier.id,
        change_note="开发种子初始价格",
    ))
    db.add(ProductReviewEvent(
        product_id=row.id,
        actor_user_id=supplier.id,
        actor_role="supplier",
        event_type="submitted_for_review",
        from_status="draft",
        to_status="pending_review",
        note="开发种子提交",
        payload={"seed": True},
    ))
    if status == "published":
        db.add(ProductReviewEvent(
            product_id=row.id,
            actor_user_id=admin.id,
            actor_role="admin",
            event_type="review_approved",
            from_status="pending_review",
            to_status="approved",
            note="开发种子自动批准",
            payload={"seed": True},
        ))
        db.add(ProductReviewEvent(
            product_id=row.id,
            actor_user_id=supplier.id,
            actor_role="supplier",
            event_type="published",
            from_status="approved",
            to_status="published",
            payload={"seed": True},
        ))
    return row


def _request(
    *,
    request_no: str,
    buyer: User,
    title: str,
    status: str,
    now: datetime,
    version: int,
) -> BuyRequest:
    deadline = now + timedelta(days=7)
    return BuyRequest(
        request_no=request_no,
        buyer_id=buyer.id,
        request_type="cloud_compute",
        title=title,
        status=status,
        visibility="public",
        gpu_model="H100",
        min_gpu_memory_gb=80,
        gpu_quantity=8,
        region_codes=["CN-SH"],
        delivery_mode="remote",
        budget_amount=Decimal("30.000000"),
        budget_currency="USD",
        budget_unit="gpu_hour",
        quote_deadline_at=deadline,
        expected_start_at=now + timedelta(days=8),
        expected_duration_hours=240,
        requirements="需要 CUDA 12.4、PyTorch 2.4、容器部署和稳定公网出口。",
        published_at=now if status != "draft" else None,
        expires_at=deadline if status != "draft" else None,
        version=version,
    )


def _add_cloud_detail(db: OrmSession, request: BuyRequest) -> None:
    db.add(CloudComputeRequestDetail(
        buy_request_id=request.id,
        min_cpu_cores=64,
        min_ram_gb=512,
        min_disk_gb=2048,
        min_download_mbps=1000,
        public_ip_required=True,
        container_image="pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime",
        software_stack=["CUDA 12.4", "PyTorch 2.4"],
        special_requirements="开发种子数据，只用于本地演示与 E2E。",
    ))


def seed_dev_data(db: OrmSession) -> dict:
    now = _now()
    buyer = _upsert_user(
        db,
        email=BUYER_EMAIL,
        display_name="KAI 开发买家",
        role="personal",
    )
    supplier = _upsert_user(
        db,
        email=SUPPLIER_EMAIL,
        display_name="KAI 开发商家",
        role="supplier",
    )
    admin = _upsert_user(
        db,
        email=ADMIN_EMAIL,
        display_name="KAI 种子管理员",
        role="admin",
    )

    db.query(LoginSession).filter(
        LoginSession.user_id.in_([buyer.id, supplier.id, admin.id])
    ).delete(synchronize_session=False)

    application = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == supplier.id
    ).first()
    if application is None:
        application = SupplierApplication(
            user_id=supplier.id,
            company_name="KAI 开发算力供应商",
            contact_name="开发联系人",
            contact_phone="13900000000",
        )
        db.add(application)
    application.company_name = "KAI 开发算力供应商"
    application.contact_name = "开发联系人"
    application.contact_phone = "13900000000"
    application.region = "CN-SH"
    application.description = "固定开发种子商家，仅用于本地联调。"
    application.status = "approved"
    application.review_note = "开发种子自动批准"
    application.reviewed_by = admin.id
    application.reviewed_at = now
    application.version = 1
    db.flush()
    db.query(SupplierApplicationEvent).filter(
        SupplierApplicationEvent.application_id == application.id
    ).delete(synchronize_session=False)
    db.add(SupplierApplicationEvent(
        application_id=application.id,
        actor_user_id=supplier.id,
        actor_role="personal",
        event_type="submitted",
        from_status=None,
        to_status="pending",
        note="开发种子提交",
        payload={"seed": True},
    ))
    db.add(SupplierApplicationEvent(
        application_id=application.id,
        actor_user_id=admin.id,
        actor_role="admin",
        event_type="approved",
        from_status="pending",
        to_status="approved",
        note="开发种子自动批准",
        payload={"seed": True, "assigned_role": "supplier"},
    ))

    identity = db.query(KycApplication).filter(KycApplication.user_id == supplier.id).first()
    if identity is None:
        identity = KycApplication(user_id=supplier.id)
        db.add(identity)
    identity.status = "approved"
    identity.provider = "manual_review"
    identity.verification_type = "business"
    identity.country_code = "CN"
    identity.review_note = "开发种子自动批准"
    identity.reviewed_by_user_id = admin.id
    identity.submitted_at = now
    identity.reviewed_at = now
    identity.declaration_accepted_at = now

    _remove_seed_request(db, DEMO_REQUEST_NO)
    _remove_seed_request(db, E2E_REQUEST_NO)
    _remove_seed_request(db, ORDER_DEMO_REQUEST_NO)
    _remove_seed_resource(db, DEMO_RESOURCE_NO)
    _remove_seed_resource(db, E2E_RESOURCE_NO)

    demo_resource = _seed_resource(
        db,
        resource_no=DEMO_RESOURCE_NO,
        supplier=supplier,
        admin=admin,
        status="published",
        name="开发演示 H100 资源池",
        now=now,
    )
    e2e_resource = _seed_resource(
        db,
        resource_no=E2E_RESOURCE_NO,
        supplier=supplier,
        admin=admin,
        status="pending_review",
        name="E2E H100 审核资源池",
        now=now,
    )

    demo = _request(
        request_no=DEMO_REQUEST_NO,
        buyer=buyer,
        title="开发演示：8 张 H100 训练算力需求",
        status="negotiating",
        now=now,
        version=3,
    )
    db.add(demo)
    db.flush()
    _add_cloud_detail(db, demo)
    demo_quote = BuyRequestQuote(
        quote_no=DEMO_QUOTE_NO,
        buy_request_id=demo.id,
        supplier_id=supplier.id,
        status="submitted",
        price_amount=Decimal("25.000000"),
        price_currency="USD",
        price_unit="gpu_hour",
        available_quantity=8,
        delivery_time_hours=2,
        valid_until=now + timedelta(days=3),
        service_description="8 张 H100 独占实例，支持 CUDA 12.4 和容器部署。",
        submitted_at=now,
        version=2,
    )
    db.add(demo_quote)
    db.flush()
    db.add(BuyRequestEvent(
        buy_request_id=demo.id,
        actor_user_id=buyer.id,
        actor_role="personal",
        event_type="published",
        from_status="draft",
        to_status="published",
        payload={"seed": True},
    ))
    db.add(BuyRequestEvent(
        buy_request_id=demo.id,
        actor_user_id=supplier.id,
        actor_role="supplier",
        event_type="quote_submitted",
        from_status="published",
        to_status="negotiating",
        payload={"seed": True, "quote_id": demo_quote.id, "quote_no": demo_quote.quote_no},
    ))

    e2e_request = _request(
        request_no=E2E_REQUEST_NO,
        buyer=buyer,
        title="E2E：8 张 H100 训练算力需求",
        status="draft",
        now=now,
        version=1,
    )
    db.add(e2e_request)
    db.flush()
    _add_cloud_detail(db, e2e_request)

    order_request = _request(
        request_no=ORDER_DEMO_REQUEST_NO,
        buyer=buyer,
        title="开发演示：待商家确认的 H100 算力订单",
        status="matched",
        now=now,
        version=4,
    )
    db.add(order_request)
    db.flush()
    _add_cloud_detail(db, order_request)
    order_quote = BuyRequestQuote(
        quote_no=ORDER_DEMO_QUOTE_NO,
        buy_request_id=order_request.id,
        supplier_id=supplier.id,
        status="accepted",
        price_amount=Decimal("23.500000"),
        price_currency="USD",
        price_unit="gpu_hour",
        available_quantity=8,
        delivery_time_hours=2,
        valid_until=now + timedelta(days=3),
        service_description="固定订单演示报价，不包含任何交付凭据。",
        submitted_at=now,
        accepted_at=now,
        version=3,
    )
    db.add(order_quote)
    db.flush()
    order = Order(
        order_no=DEMO_ORDER_NO,
        buyer_id=buyer.id,
        supplier_id=supplier.id,
        buy_request_id=order_request.id,
        accepted_quote_id=order_quote.id,
        status="pending_confirmation",
        amount=order_quote.price_amount,
        currency=order_quote.price_currency,
        price_unit=order_quote.price_unit,
        quantity=order_request.gpu_quantity,
        snapshot={
            "pricing_semantics": "quoted_unit_price",
            "request": {
                "request_no": order_request.request_no,
                "title": order_request.title,
                "request_type": order_request.request_type,
                "gpu_model": order_request.gpu_model,
                "gpu_quantity": order_request.gpu_quantity,
                "region_codes": order_request.region_codes,
                "delivery_mode": order_request.delivery_mode,
                "expected_start_at": order_request.expected_start_at.isoformat(),
                "expected_duration_hours": order_request.expected_duration_hours,
                "requirements": order_request.requirements,
            },
            "quote": {
                "quote_no": order_quote.quote_no,
                "price_amount": format(order_quote.price_amount, "f"),
                "price_currency": order_quote.price_currency,
                "price_unit": order_quote.price_unit,
                "available_quantity": order_quote.available_quantity,
                "delivery_time_hours": order_quote.delivery_time_hours,
                "valid_until": order_quote.valid_until.isoformat(),
                "service_description": order_quote.service_description,
            },
            "supplier": {
                "id": supplier.id,
                "display_name": supplier.display_name,
                "company_name": application.company_name,
            },
        },
        buyer_confirmed_at=now,
        version=1,
    )
    db.add(order)
    db.flush()
    db.add(BuyRequestEvent(
        buy_request_id=order_request.id,
        actor_user_id=buyer.id,
        actor_role=buyer.role,
        event_type="quote_accepted",
        from_status="negotiating",
        to_status="matched",
        payload={
            "seed": True,
            "quote_id": order_quote.id,
            "quote_no": order_quote.quote_no,
            "order_id": order.id,
            "order_no": order.order_no,
        },
    ))
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=buyer.id,
        actor_role=buyer.role,
        event_type="created_from_accepted_quote",
        from_status=None,
        to_status="pending_confirmation",
        payload={
            "seed": True,
            "buy_request_id": order_request.id,
            "accepted_quote_id": order_quote.id,
            "payment_required": False,
        },
    ))

    db.commit()
    return {
        "accounts": {
            "buyer": {"email": BUYER_EMAIL, "password": SEED_PASSWORD},
            "supplier": {"email": SUPPLIER_EMAIL, "password": SEED_PASSWORD},
            "admin": {"email": ADMIN_EMAIL, "password": SEED_PASSWORD},
        },
        "demo": {
            "request_id": demo.id,
            "request_no": demo.request_no,
            "quote_id": demo_quote.id,
            "quote_no": demo_quote.quote_no,
            "status": demo.status,
        },
        "e2e": {
            "request_id": e2e_request.id,
            "request_no": e2e_request.request_no,
            "status": e2e_request.status,
            "resource_id": e2e_resource.id,
            "resource_no": e2e_resource.resource_no,
        },
        "resource_demo": {
            "resource_id": demo_resource.id,
            "resource_no": demo_resource.resource_no,
            "status": demo_resource.status,
        },
        "order_demo": {
            "request_id": order_request.id,
            "request_no": order_request.request_no,
            "quote_id": order_quote.id,
            "quote_no": order_quote.quote_no,
            "order_id": order.id,
            "order_no": order.order_no,
            "status": order.status,
        },
    }


def _is_local_database() -> bool:
    url = make_url(settings.DATABASE_URL)
    if url.drivername.startswith("sqlite"):
        return True
    if url.host in {"127.0.0.1", "localhost", "::1"}:
        return True
    return (
        settings.APP_ENV.casefold() == "development"
        and url.host == "postgres"
        and Path("/.dockerenv").exists()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset KAI-owned local development seed data.")
    parser.add_argument(
        "--confirm-local",
        action="store_true",
        help="Confirm that the configured local database may be updated.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args()
    if not args.confirm_local:
        parser.error("--confirm-local is required")
    if not _is_local_database():
        parser.error("refusing to seed a non-local database")
    with SessionLocal() as db:
        try:
            result = seed_dev_data(db)
        except Exception:
            db.rollback()
            raise
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("KAI development seed is ready.")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
