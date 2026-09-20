"""State machine for non-financial buyer/supplier matchmaking.

This module deliberately does not import orders, wallets, ledgers, payments or
rewards.  A matchmaking agreement records negotiated terms and credential
delivery only; it cannot move money or card-hours.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.sensitive import fingerprint, protect, reveal
from app.models.buy_request import (
    BuyRequest,
    BuyRequestCredential,
    BuyRequestDeal,
    BuyRequestEvent,
    BuyRequestQuote,
    BuyRequestQuoteRevision,
)
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.buy_request import MatchmakingCredentialIn, QuoteRevisionIn
from app.services.trade_mode import credential_escrow_enabled
from app.utils.response import BizError


CREDENTIAL_ENVELOPE_NAMESPACE = "wod.matchmaking.ssh-credential"
CREDENTIAL_ENVELOPE_VERSION = 1
ACTIVE_DEAL_STATUSES = {
    "buyer_selected",
    "platform_review",
    "credential_pending",
    "credential_rejected",
    "credential_submitted",
    "credential_released",
    "delivery_disputed",
}
TERMINAL_DEAL_STATUSES = {
    "supplier_declined",
    "platform_rejected",
    "completed",
    "cancelled",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def require_credential_escrow_enabled() -> None:
    if not credential_escrow_enabled():
        raise BizError("凭证托管服务暂未开放", status_code=409)


def _safe_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    if re.search(
        r"-----BEGIN\s+.+PRIVATE\s+KEY-----|"
        r"\bssh\s+\S+@\S+|"
        r"\b(?:password|passwd|secret|private[_ -]?key)\s*[:=]",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "[敏感连接信息已隐藏]"
    return normalized[:1000] or None


def _event(
    db: Session,
    request: BuyRequest,
    *,
    actor: User | None,
    actor_role: str,
    event_type: str,
    deal: BuyRequestDeal | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    quote_id: int | None = None,
    revision_id: int | None = None,
    reason: str | None = None,
) -> BuyRequestEvent:
    # This allow-listed payload is intentionally unable to accept credential
    # fields.  It is safe for buyer/supplier timelines and application logs.
    data: dict[str, Any] = {}
    if quote_id is not None:
        data["quote_id"] = quote_id
    if revision_id is not None:
        data["revision_id"] = revision_id
    safe_reason = _safe_reason(reason)
    if safe_reason:
        data["reason"] = safe_reason
    row = BuyRequestEvent(
        buy_request_id=request.id,
        deal_id=deal.id if deal else None,
        actor_user_id=actor.id if actor else None,
        actor_role=actor_role,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        event_data=data or None,
    )
    db.add(row)
    return row


def revision_out(row: BuyRequestQuoteRevision) -> dict:
    return {
        "id": row.id,
        "quote_id": row.quote_id,
        "revision_no": row.revision_number,
        "actor_role": row.proposer_role,
        "unit_price": float(row.unit_price) if row.unit_price is not None else None,
        "total_price": float(row.total_price),
        "currency": row.currency,
        "available_at": iso(row.available_at),
        "message": row.message,
        "status": row.status,
        "expires_at": iso(row.expires_at),
        "created_at": iso(row.created_at),
    }


def _redact_supplier_contact(value: str | None, supplier: Supplier | None) -> str | None:
    if not value:
        return value
    sanitized = value
    if supplier:
        for token in (supplier.contact, supplier.phone):
            if token:
                sanitized = sanitized.replace(token, "[已隐藏]")
    sanitized = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[已隐藏]", sanitized)
    sanitized = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[已隐藏]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def latest_revision(db: Session, quote_id: int) -> BuyRequestQuoteRevision | None:
    return db.query(BuyRequestQuoteRevision).filter(
        BuyRequestQuoteRevision.quote_id == quote_id,
    ).order_by(
        BuyRequestQuoteRevision.revision_number.desc(),
        BuyRequestQuoteRevision.id.desc(),
    ).first()


def ensure_initial_revision(
    db: Session,
    request: BuyRequest,
    quote: BuyRequestQuote,
    proposer_user_id: int,
) -> BuyRequestQuoteRevision:
    existing = latest_revision(db, quote.id)
    if existing:
        return existing
    row = BuyRequestQuoteRevision(
        quote_id=quote.id,
        buy_request_id=request.id,
        supplier_id=quote.supplier_id,
        revision_number=1,
        proposer_role="supplier",
        proposer_user_id=proposer_user_id,
        unit_price=quote.unit_price,
        total_price=quote.total_price,
        currency=quote.currency,
        available_at=quote.available_at,
        message=quote.message,
        expires_at=quote.expires_at,
        status="active" if quote.status == "active" else quote.status,
    )
    db.add(row)
    db.flush()
    _event(
        db,
        request,
        actor=None,
        actor_role="system",
        event_type="quote_history_initialized",
        quote_id=quote.id,
        revision_id=row.id,
    )
    return row


def create_initial_revision(
    db: Session,
    request: BuyRequest,
    quote: BuyRequestQuote,
    actor: User,
) -> BuyRequestQuoteRevision:
    row = BuyRequestQuoteRevision(
        quote_id=quote.id,
        buy_request_id=request.id,
        supplier_id=quote.supplier_id,
        revision_number=1,
        proposer_role="supplier",
        proposer_user_id=actor.id,
        unit_price=quote.unit_price,
        total_price=quote.total_price,
        currency=quote.currency,
        available_at=quote.available_at,
        message=quote.message,
        expires_at=quote.expires_at,
        status="active",
    )
    db.add(row)
    db.flush()
    _event(
        db,
        request,
        actor=actor,
        actor_role="supplier",
        event_type="quote_submitted",
        quote_id=quote.id,
        revision_id=row.id,
    )
    return row


def revise_quote(
    db: Session,
    request: BuyRequest,
    quote: BuyRequestQuote,
    actor: User,
    supplier: Supplier,
    data: QuoteRevisionIn,
) -> BuyRequestQuoteRevision:
    if quote.supplier_id != supplier.id:
        raise BizError("报价不存在", status_code=404)
    if quote.status != "active" or request.status not in ("published", "quoting"):
        raise BizError("该报价当前不能议价", status_code=409)
    if actor.id not in (request.user_id, supplier.user_id):
        raise BizError("无权修改该报价", status_code=403)

    current = ensure_initial_revision(db, request, quote, supplier.user_id)
    actor_role = "buyer" if actor.id == request.user_id else "supplier"
    if current.proposer_role == actor_role:
        raise BizError("请等待对方回应当前方案", status_code=409)
    if current.status != "active":
        raise BizError("该报价当前不能议价", status_code=409)
    if current.expires_at and current.expires_at < utcnow():
        current.status = "expired"
        quote.status = "expired"
        raise BizError("报价已过期", status_code=409)

    current.status = "superseded"
    available_at = data.available_at
    if available_at and available_at.tzinfo:
        available_at = available_at.astimezone(timezone.utc).replace(tzinfo=None)
    expires_at = utcnow() + timedelta(hours=data.expires_in_hours)
    row = BuyRequestQuoteRevision(
        quote_id=quote.id,
        buy_request_id=request.id,
        supplier_id=supplier.id,
        revision_number=current.revision_number + 1,
        proposer_role=actor_role,
        proposer_user_id=actor.id,
        parent_revision_id=current.id,
        unit_price=Decimal(str(data.unit_price)) if data.unit_price is not None else None,
        total_price=Decimal(str(data.total_price)),
        currency=data.currency.upper(),
        available_at=available_at,
        message=data.message,
        expires_at=expires_at,
        status="active",
    )
    db.add(row)
    db.flush()

    # Installed clients still read these projection columns.
    quote.unit_price = row.unit_price
    quote.total_price = row.total_price
    quote.currency = row.currency
    quote.available_at = row.available_at
    quote.message = row.message
    quote.expires_at = row.expires_at
    _event(
        db,
        request,
        actor=actor,
        actor_role=actor_role,
        event_type="quote_countered",
        quote_id=quote.id,
        revision_id=row.id,
    )
    return row


def withdraw_quote(
    db: Session,
    request: BuyRequest,
    quote: BuyRequestQuote,
    actor: User,
    supplier: Supplier,
) -> BuyRequestQuote:
    if quote.supplier_id != supplier.id or supplier.user_id != actor.id:
        raise BizError("报价不存在", status_code=404)
    if quote.status == "withdrawn":
        return quote
    if quote.status != "active" or request.status not in ("published", "quoting"):
        raise BizError("该报价当前不能撤回", status_code=409)
    revision = ensure_initial_revision(db, request, quote, actor.id)
    revision.status = "withdrawn"
    quote.status = "withdrawn"
    remaining = db.query(BuyRequestQuote).filter(
        BuyRequestQuote.buy_request_id == request.id,
        BuyRequestQuote.id != quote.id,
        BuyRequestQuote.status == "active",
    ).count()
    request.status = "quoting" if remaining else "published"
    _event(
        db,
        request,
        actor=actor,
        actor_role="supplier",
        event_type="quote_withdrawn",
        quote_id=quote.id,
        revision_id=revision.id,
    )
    return quote


def _active_deal(db: Session, request_id: int) -> BuyRequestDeal | None:
    return db.query(BuyRequestDeal).filter(
        BuyRequestDeal.active_slot == f"request:{request_id}",
    ).first()


def select_quote(
    db: Session,
    request: BuyRequest,
    quote: BuyRequestQuote,
    buyer: User,
) -> BuyRequestDeal:
    existing = _active_deal(db, request.id)
    revision = ensure_initial_revision(
        db,
        request,
        quote,
        db.query(Supplier).filter(Supplier.id == quote.supplier_id).one().user_id,
    )
    if existing:
        if existing.quote_id == quote.id and existing.selected_revision_id == revision.id:
            return existing
        raise BizError("该需求已有进行中的撮合方案", status_code=409)
    if request.user_id != buyer.id:
        raise BizError("求购不存在", status_code=404)
    if request.status not in ("published", "quoting"):
        raise BizError("该求购当前不能确认合作意向", status_code=409)
    if quote.status != "active" or revision.status != "active":
        raise BizError("报价不存在或已失效", status_code=409)
    if revision.expires_at and revision.expires_at < utcnow():
        revision.status = "expired"
        quote.status = "expired"
        raise BizError("报价已过期", status_code=409)

    deal = BuyRequestDeal(
        buy_request_id=request.id,
        quote_id=quote.id,
        selected_revision_id=revision.id,
        buyer_id=buyer.id,
        supplier_id=quote.supplier_id,
        status="buyer_selected",
        version=1,
        active_slot=f"request:{request.id}",
    )
    quote.status = "coordination_requested"
    revision.status = "selected"
    request.status = "buyer_selected"
    db.add(deal)
    try:
        db.flush()
    except (IntegrityError, OperationalError) as exc:
        if isinstance(exc, OperationalError) and "locked" not in str(exc).lower():
            raise
        db.rollback()
        concurrent = _active_deal(db, request.id)
        if concurrent and concurrent.quote_id == quote.id:
            return concurrent
        raise BizError("该需求已有进行中的撮合方案", status_code=409) from None
    _event(
        db,
        request,
        actor=buyer,
        actor_role="buyer",
        event_type="buyer_selected_quote",
        deal=deal,
        from_status="quoting",
        to_status="buyer_selected",
        quote_id=quote.id,
        revision_id=revision.id,
    )
    return deal


def get_deal(db: Session, request_id: int, deal_id: int) -> BuyRequestDeal:
    deal = db.query(BuyRequestDeal).filter(
        BuyRequestDeal.id == deal_id,
        BuyRequestDeal.buy_request_id == request_id,
    ).first()
    if not deal:
        raise BizError("撮合方案不存在", status_code=404)
    return deal


def _version_guard(deal: BuyRequestDeal, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != deal.version:
        raise BizError("撮合状态已更新，请刷新后重试", status_code=409)


def _transition(
    db: Session,
    request: BuyRequest,
    deal: BuyRequestDeal,
    *,
    actor: User,
    actor_role: str,
    event_type: str,
    allowed: set[str],
    target: str,
    expected_version: int | None,
    reason: str | None = None,
    terminal: bool = False,
) -> bool:
    if deal.status == target:
        return False
    if deal.status not in allowed:
        raise BizError("当前状态不能执行此操作", status_code=409)
    _version_guard(deal, expected_version)
    previous = deal.status
    deal.status = target
    deal.version += 1
    deal.status_reason = _safe_reason(reason)
    request.status = target
    if terminal:
        deal.active_slot = None
        deal.cancelled_at = utcnow() if target != "completed" else deal.cancelled_at
    _event(
        db,
        request,
        actor=actor,
        actor_role=actor_role,
        event_type=event_type,
        deal=deal,
        from_status=previous,
        to_status=target,
        quote_id=deal.quote_id,
        revision_id=deal.selected_revision_id,
        reason=reason,
    )
    return True


def supplier_decision(
    db: Session,
    request: BuyRequest,
    deal: BuyRequestDeal,
    actor: User,
    supplier: Supplier,
    *,
    confirm: bool,
    expected_version: int | None = None,
    reason: str | None = None,
) -> BuyRequestDeal:
    if deal.supplier_id != supplier.id or supplier.user_id != actor.id:
        raise BizError("撮合方案不存在", status_code=404)
    target = "platform_review" if confirm else "supplier_declined"
    changed = _transition(
        db,
        request,
        deal,
        actor=actor,
        actor_role="supplier",
        event_type="supplier_confirmed" if confirm else "supplier_declined",
        allowed={"buyer_selected"},
        target=target,
        expected_version=expected_version,
        reason=reason,
        terminal=not confirm,
    )
    if changed and confirm:
        deal.supplier_confirmed_at = utcnow()
    elif changed:
        quote = db.query(BuyRequestQuote).filter(BuyRequestQuote.id == deal.quote_id).one()
        quote.status = "withdrawn"
        revision = db.query(BuyRequestQuoteRevision).filter(
            BuyRequestQuoteRevision.id == deal.selected_revision_id,
        ).one()
        revision.status = "withdrawn"
        request.status = "quoting" if db.query(BuyRequestQuote).filter(
            BuyRequestQuote.buy_request_id == request.id,
            BuyRequestQuote.id != quote.id,
            BuyRequestQuote.status == "active",
        ).count() else "published"
    return deal


def admin_review(
    db: Session,
    request: BuyRequest,
    deal: BuyRequestDeal,
    actor: User,
    *,
    approve: bool,
    expected_version: int | None = None,
    reason: str | None = None,
) -> BuyRequestDeal:
    target = "credential_pending" if approve else "platform_rejected"
    changed = _transition(
        db,
        request,
        deal,
        actor=actor,
        actor_role="admin",
        event_type="platform_approved" if approve else "platform_rejected",
        allowed={"platform_review"},
        target=target,
        expected_version=expected_version,
        reason=reason,
        terminal=not approve,
    )
    if changed:
        deal.platform_reviewed_by = actor.id
        deal.platform_reviewed_at = utcnow()
        if not approve:
            quote = db.query(BuyRequestQuote).filter(BuyRequestQuote.id == deal.quote_id).one()
            revision = db.query(BuyRequestQuoteRevision).filter(
                BuyRequestQuoteRevision.id == deal.selected_revision_id,
            ).one()
            quote.status = "active"
            revision.status = "active"
            request.status = "quoting"
    return deal


def _credential_plain(data: MatchmakingCredentialIn) -> dict[str, Any]:
    return {
        "host": data.host,
        "port": data.port,
        "username": data.username,
        "auth_type": data.auth_type,
        "secret": data.secret,
        "note": data.note.strip() if data.note and data.note.strip() else None,
    }


def _encode_credential(data: MatchmakingCredentialIn) -> tuple[str, str]:
    envelope = {
        "namespace": CREDENTIAL_ENVELOPE_NAMESPACE,
        "version": CREDENTIAL_ENVELOPE_VERSION,
        "credential": _credential_plain(data),
    }
    canonical = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    protected = protect(canonical)
    if not protected or protected == canonical:
        raise RuntimeError("credential encryption failed closed")
    return protected, fingerprint(canonical)


def submit_credential(
    db: Session,
    request: BuyRequest,
    deal: BuyRequestDeal,
    actor: User,
    supplier: Supplier,
    data: MatchmakingCredentialIn,
) -> BuyRequestCredential:
    require_credential_escrow_enabled()
    if deal.supplier_id != supplier.id or supplier.user_id != actor.id:
        raise BizError("撮合方案不存在", status_code=404)
    current = db.query(BuyRequestCredential).filter(
        BuyRequestCredential.deal_id == deal.id,
    ).first()
    protected_payload, payload_fingerprint = _encode_credential(data)
    if deal.status == "credential_submitted" and current:
        if current.payload_fingerprint == payload_fingerprint:
            return current
        raise BizError("凭证正在等待平台审核", status_code=409)
    if deal.status not in {"credential_pending", "credential_rejected"}:
        raise BizError("当前状态不能提交凭证", status_code=409)
    _version_guard(deal, data.expected_version)
    now = utcnow()
    if current:
        current.protected_payload = protected_payload
        current.payload_fingerprint = payload_fingerprint
        current.envelope_namespace = CREDENTIAL_ENVELOPE_NAMESPACE
        current.envelope_version = CREDENTIAL_ENVELOPE_VERSION
        current.credential_version += 1
        current.status = "submitted"
        current.submitted_by = actor.id
        current.submitted_at = now
        current.inspected_by = None
        current.inspected_at = None
        current.released_by = None
        current.released_at = None
        current.rejected_at = None
        credential = current
    else:
        credential = BuyRequestCredential(
            deal_id=deal.id,
            protected_payload=protected_payload,
            payload_fingerprint=payload_fingerprint,
            envelope_namespace=CREDENTIAL_ENVELOPE_NAMESPACE,
            envelope_version=CREDENTIAL_ENVELOPE_VERSION,
            credential_version=1,
            status="submitted",
            submitted_by=actor.id,
            submitted_at=now,
        )
        db.add(credential)
    previous = deal.status
    deal.status = "credential_submitted"
    deal.version += 1
    deal.credential_submitted_at = now
    request.status = "credential_submitted"
    _event(
        db,
        request,
        actor=actor,
        actor_role="supplier",
        event_type="credential_submitted",
        deal=deal,
        from_status=previous,
        to_status="credential_submitted",
    )
    return credential


def credential_metadata(row: BuyRequestCredential | None) -> dict | None:
    if not row:
        return None
    return {
        "status": row.status,
        "fingerprint": row.payload_fingerprint,
        "envelope_version": row.envelope_version,
        "credential_version": row.credential_version,
        "submitted_at": iso(row.submitted_at),
        "inspected_at": iso(row.inspected_at),
        "released_at": iso(row.released_at),
    }


def reveal_credential(row: BuyRequestCredential) -> dict[str, Any]:
    plain = reveal(row.protected_payload)
    try:
        envelope = json.loads(plain)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise BizError("凭证无法解密，请商家重新提交", status_code=409) from None
    if (
        not isinstance(envelope, dict)
        or envelope.get("namespace") != CREDENTIAL_ENVELOPE_NAMESPACE
        or envelope.get("version") != CREDENTIAL_ENVELOPE_VERSION
        or not isinstance(envelope.get("credential"), dict)
    ):
        raise BizError("凭证格式不受支持，请商家重新提交", status_code=409)
    return dict(envelope["credential"])


def inspect_credential(
    db: Session,
    deal: BuyRequestDeal,
    actor: User,
) -> dict[str, Any]:
    require_credential_escrow_enabled()
    row = db.query(BuyRequestCredential).filter(
        BuyRequestCredential.deal_id == deal.id,
    ).first()
    if not row or row.status not in {"submitted", "released"}:
        raise BizError("尚无可审核凭证", status_code=409)
    credential = reveal_credential(row)
    if row.inspected_at is None:
        row.inspected_by = actor.id
        row.inspected_at = utcnow()
    return {**credential, **credential_metadata(row)}


def admin_credential_decision(
    db: Session,
    request: BuyRequest,
    deal: BuyRequestDeal,
    actor: User,
    *,
    release_to_buyer: bool,
    expected_version: int | None = None,
    reason: str | None = None,
) -> BuyRequestDeal:
    require_credential_escrow_enabled()
    row = db.query(BuyRequestCredential).filter(
        BuyRequestCredential.deal_id == deal.id,
    ).first()
    if release_to_buyer and deal.status == "credential_released" and row and row.status == "released":
        return deal
    if not release_to_buyer and deal.status == "credential_rejected" and row and row.status == "rejected":
        return deal
    allowed = {"credential_submitted"} if release_to_buyer else {
        "credential_submitted", "delivery_disputed"
    }
    if not row or row.status not in {"submitted", "released"} or deal.status not in allowed:
        raise BizError("当前状态不能审核凭证", status_code=409)
    _version_guard(deal, expected_version)
    # Decrypt before release so malformed/corrupt data can never be exposed as
    # a successful delivery state.
    reveal_credential(row)
    now = utcnow()
    previous = deal.status
    deal.status = "credential_released" if release_to_buyer else "credential_rejected"
    deal.version += 1
    deal.status_reason = _safe_reason(reason)
    request.status = deal.status
    if release_to_buyer:
        row.status = "released"
        row.released_by = actor.id
        row.released_at = now
        deal.credential_released_at = now
    else:
        row.status = "rejected"
        row.rejected_at = now
        row.released_by = None
        row.released_at = None
        deal.credential_released_at = None
    _event(
        db,
        request,
        actor=actor,
        actor_role="admin",
        event_type="credential_released" if release_to_buyer else "credential_rejected",
        deal=deal,
        from_status=previous,
        to_status=deal.status,
        reason=reason,
    )
    return deal


def buyer_read_credential(
    db: Session,
    deal: BuyRequestDeal,
    actor: User,
) -> dict[str, Any]:
    require_credential_escrow_enabled()
    if deal.buyer_id != actor.id:
        raise BizError("撮合方案不存在", status_code=404)
    if deal.status not in {"credential_released", "delivery_disputed", "completed"}:
        raise BizError("凭证尚未由平台释放", status_code=403)
    row = db.query(BuyRequestCredential).filter(
        BuyRequestCredential.deal_id == deal.id,
        BuyRequestCredential.status == "released",
    ).first()
    if not row:
        raise BizError("凭证尚未由平台释放", status_code=403)
    return {**reveal_credential(row), "released_at": iso(row.released_at)}


def buyer_delivery_decision(
    db: Session,
    request: BuyRequest,
    deal: BuyRequestDeal,
    actor: User,
    *,
    confirm: bool,
    expected_version: int | None = None,
    reason: str | None = None,
) -> BuyRequestDeal:
    if deal.buyer_id != actor.id:
        raise BizError("撮合方案不存在", status_code=404)
    target = "completed" if confirm else "delivery_disputed"
    changed = _transition(
        db,
        request,
        deal,
        actor=actor,
        actor_role="buyer",
        event_type="delivery_confirmed" if confirm else "delivery_reported",
        allowed={"credential_released"},
        target=target,
        expected_version=expected_version,
        reason=reason,
        terminal=confirm,
    )
    if changed and confirm:
        deal.completed_at = utcnow()
        quote = db.query(BuyRequestQuote).filter(BuyRequestQuote.id == deal.quote_id).one()
        quote.status = "completed"
    return deal


def deal_out(
    db: Session,
    deal: BuyRequestDeal,
    *,
    viewer_role: str,
) -> dict:
    supplier = db.query(Supplier).filter(Supplier.id == deal.supplier_id).first()
    revision = db.query(BuyRequestQuoteRevision).filter(
        BuyRequestQuoteRevision.id == deal.selected_revision_id,
    ).first()
    credential = db.query(BuyRequestCredential).filter(
        BuyRequestCredential.deal_id == deal.id,
    ).first()
    actions = {
        "can_supplier_confirm": viewer_role == "supplier" and deal.status == "buyer_selected",
        "can_supplier_decline": viewer_role == "supplier" and deal.status == "buyer_selected",
        "can_submit_credential": viewer_role == "supplier" and deal.status in {
            "credential_pending", "credential_rejected"
        },
        "can_buyer_view_credential": viewer_role == "buyer" and deal.status in {
            "credential_released", "delivery_disputed", "completed"
        },
        "can_buyer_confirm": viewer_role == "buyer" and deal.status == "credential_released",
        "can_report": viewer_role == "buyer" and deal.status == "credential_released",
        "can_admin_approve": viewer_role == "admin" and deal.status == "platform_review",
        "can_admin_reject": viewer_role == "admin" and deal.status == "platform_review",
        "can_admin_inspect_credential": viewer_role == "admin" and deal.status in {
            "credential_submitted", "credential_released", "delivery_disputed"
        },
        "can_admin_release_credential": viewer_role == "admin" and deal.status == "credential_submitted",
        "can_admin_reject_credential": viewer_role == "admin" and deal.status in {
            "credential_submitted", "delivery_disputed"
        },
    }
    selected_revision = revision_out(revision) if revision else None
    if selected_revision and viewer_role == "buyer":
        selected_revision["message"] = _redact_supplier_contact(
            selected_revision.get("message"), supplier
        )
    result = {
        "id": deal.id,
        "buy_request_id": deal.buy_request_id,
        "quote_id": deal.quote_id,
        "selected_revision_id": deal.selected_revision_id,
        "selected_revision": selected_revision,
        "supplier_id": deal.supplier_id,
        "supplier_name": supplier.company_name if supplier else "",
        "supplier_rating": supplier.rating if supplier else None,
        "status": deal.status,
        "version": deal.version,
        "status_reason": deal.status_reason,
        "credential_status": credential.status if credential else None,
        "credential": credential_metadata(credential),
        "selected_at": iso(deal.selected_at),
        "supplier_confirmed_at": iso(deal.supplier_confirmed_at),
        "platform_reviewed_at": iso(deal.platform_reviewed_at),
        "credential_submitted_at": iso(deal.credential_submitted_at),
        "credential_released_at": iso(deal.credential_released_at),
        "completed_at": iso(deal.completed_at),
        "created_at": iso(deal.created_at),
        "updated_at": iso(deal.updated_at),
        "actions": actions,
        **actions,
    }
    if viewer_role == "admin":
        result["buyer_id"] = deal.buyer_id
        result["platform_reviewed_by"] = deal.platform_reviewed_by
    return result


def latest_visible_deal(
    db: Session,
    request: BuyRequest,
    *,
    viewer_role: str,
    viewer_user_id: int,
    viewer_supplier_id: int | None = None,
) -> BuyRequestDeal | None:
    query = db.query(BuyRequestDeal).filter(BuyRequestDeal.buy_request_id == request.id)
    if viewer_role == "buyer":
        query = query.filter(BuyRequestDeal.buyer_id == viewer_user_id)
    elif viewer_role == "supplier":
        if viewer_supplier_id is None:
            return None
        query = query.filter(BuyRequestDeal.supplier_id == viewer_supplier_id)
    return query.order_by(BuyRequestDeal.created_at.desc(), BuyRequestDeal.id.desc()).first()


def events_out(
    db: Session,
    request: BuyRequest,
    *,
    viewer_role: str,
    viewer_supplier_id: int | None = None,
    deal: BuyRequestDeal | None = None,
) -> list[dict]:
    query = db.query(BuyRequestEvent).filter(BuyRequestEvent.buy_request_id == request.id)
    rows = query.order_by(BuyRequestEvent.created_at.asc(), BuyRequestEvent.id.asc()).all()
    if viewer_role == "supplier":
        own_quote_ids = {
            row[0] for row in db.query(BuyRequestQuote.id).filter(
                BuyRequestQuote.buy_request_id == request.id,
                BuyRequestQuote.supplier_id == viewer_supplier_id,
            ).all()
        }
        visible_deal_id = deal.id if deal else None
        rows = [
            row for row in rows
            if row.deal_id == visible_deal_id
            or (
                row.deal_id is None
                and isinstance(row.event_data, dict)
                and row.event_data.get("quote_id") in own_quote_ids
            )
        ]
    result = []
    for row in rows:
        payload = {
            "id": row.id,
            "event_type": row.event_type,
            "status": row.to_status,
            "label": row.event_type,
            "actor_role": row.actor_role,
            "message": (row.event_data or {}).get("reason"),
            "from_status": row.from_status,
            "to_status": row.to_status,
            "created_at": iso(row.created_at),
        }
        if viewer_role == "admin":
            payload["actor_user_id"] = row.actor_user_id
            payload["data"] = row.event_data or {}
        result.append(payload)
    return result
