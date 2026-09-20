"""Account-deletion eligibility and scoped, transactional data minimisation.

This module never commits, changes monetary amounts, touches the filesystem or
changes commerce switches. The lifecycle service must serialize eligibility
checks with account writes, obtain explicit consent, persist the returned file
cleanup work and only then commit. Unknown business states fail closed.

Retention boundary: IDs, amounts, ledger/reward/settlement facts and resolved
dispute/finance-operator evidence remain restricted audit records. We clear
user-authored profile, contact and content fields, not arbitrarily redact
another participant's historical statements. Those retained audit narratives
and payout receipts require the documented retention/access policy; this is
not a promise to erase every mention of a person from third-party free text.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import (
    AccountRecoveryMailOutbox, AccountRecoveryToken, Address, Asset, AuthSession, BankCard, BuyRequest, BuyRequestCredential,
    BuyRequestDeal, BuyRequestEvent, BuyRequestQuote, BuyRequestQuoteRevision,
    Comment, CommunityBlock, CommunityReport, ComputeOnboarding, Coupon, ExternalAuthBindTicket,
    ExternalAuthFlow, ExternalAuthTicket, ExternalIdentity, Follow, InviteCode,
    InviteRecord, Like, MerchantSettlement, Notification, NotificationPreference,
    OfflinePurchase, Order, OrderFundingAllocation, OrderRenewal,
    PaymentInstructionGrant, PaymentOrder, PaymentRefund, Post, Product, RewardAccrual, Supplier,
    SupportConversation, SupportMessage, SupportTicket, User, Verification,
    Wallet, WithdrawalOrder,
)
from app.services.buy_request_matchmaking import TERMINAL_DEAL_STATUSES


DELETED_LABEL = "已注销用户"
OPEN_REQUEST_STATUSES = ("published", "quoting")
TERMINAL_REQUEST_STATUSES = (
    "completed", "done", "cancelled", "canceled", "closed", "expired", "rejected",
)
TERMINAL_ORDER_STATUSES = ("done", "canceled", "cancelled")
WALLET_BUCKETS = (
    "balance", "frozen", "promotional_balance", "promotional_frozen",
    "withdrawable_balance", "withdraw_frozen",
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _scope(db: Session, user: User):
    suppliers = db.query(Supplier.id).filter(Supplier.user_id == user.id)
    products = db.query(Product.id).filter(Product.supplier_id.in_(suppliers))
    orders = db.query(Order.id).filter(or_(
        Order.user_id == user.id, Order.product_id.in_(products),
    ))
    return suppliers, products, orders


def get_deletion_blockers(db: Session, user: User) -> list[dict]:
    """Return counted obligations without expiring, settling or modifying any row."""
    suppliers, products, orders = _scope(db, user)
    now = _now()
    blockers: list[dict] = []

    def add(code: str, message: str, query) -> None:
        count = query.count()
        if count:
            blockers.append({"code": code, "message": message, "count": count})

    add("active_matchmaking", "存在待确认、交付中或争议中的撮合合作，请先处理完成。",
        db.query(BuyRequestDeal).filter(
            or_(BuyRequestDeal.buyer_id == user.id, BuyRequestDeal.supplier_id.in_(suppliers)),
            BuyRequestDeal.status.notin_(TERMINAL_DEAL_STATUSES),
        ))
    add("active_orders", "存在未结束的算力订单或交付争议，请先完成、终止或交接。",
        db.query(Order).filter(Order.id.in_(orders), ~or_(
            Order.status.in_(TERMINAL_ORDER_STATUSES),
            and_(Order.status == "completed", Order.end_at.isnot(None), Order.end_at <= now),
        )))
    add("active_assets", "仍有未关闭的算力资产，请先结束服务或完成资产处理。",
        db.query(Asset).filter(
            or_(Asset.user_id == user.id, Asset.product_id.in_(products)),
            Asset.status.notin_(("expired", "sold", "used")),
        ))
    # Renewals are immutable completed debit events with no status column.
    # A future service end remains an obligation even if the parent was
    # incorrectly marked done or a legacy asset row is missing.
    add("active_renewals", "仍有处于服务期的续费记录，请先完成服务处理。",
        db.query(OrderRenewal).filter(OrderRenewal.order_id.in_(orders), OrderRenewal.new_end_at > now))
    related_quotes = db.query(BuyRequestQuote.buy_request_id).filter(
        BuyRequestQuote.supplier_id.in_(suppliers),
        BuyRequestQuote.status.in_(("selected", "coordination_requested")),
    )
    add("unresolved_requests", "存在已选定方案或未结束的历史需求，请联系平台完成交接。",
        db.query(BuyRequest).filter(
            or_(BuyRequest.user_id == user.id, BuyRequest.id.in_(related_quotes)),
            BuyRequest.status.notin_(OPEN_REQUEST_STATUSES + TERMINAL_REQUEST_STATUSES),
        ))
    add("offline_cooperation", "历史线下采购仍在联系或履约中，请先确认结束。",
        db.query(OfflinePurchase).filter(
            OfflinePurchase.user_id == user.id,
            OfflinePurchase.status.notin_(("submitted", "done", "rejected", "cancelled", "canceled")),
        ))
    # Qixiang's 0 means unpaid, NOT closed, and local canceled orders can
    # still receive a late success requiring manual review. CREATE_FAILED with
    # no provider artefact is the one persisted, explicit create rejection.
    # Legacy MaPay checkout is a browser form and did not save a start marker:
    # absence of artefacts cannot prove an expired MaPay order was never sent.
    # Its signed notification handler recognises exactly these final failures.
    no_provider_artifact = and_(
        or_(PaymentOrder.provider_trade_no.is_(None), PaymentOrder.provider_trade_no == ""),
        or_(PaymentOrder.provider_checkout_url.is_(None), PaymentOrder.provider_checkout_url == ""),
        PaymentOrder.checkout_started_at.is_(None),
    )
    safe_unpaid_terminal = and_(
        PaymentOrder.status.in_(("expired", "failed", "canceled", "cancelled")),
        PaymentOrder.credited_at.is_(None),
        or_(
            and_(PaymentOrder.provider == "qixiangpay", no_provider_artifact,
                 or_(PaymentOrder.provider_status.is_(None), PaymentOrder.provider_status.in_(("", "CREATE_FAILED")))),
            and_(PaymentOrder.provider == "mapay", PaymentOrder.provider_status.in_(
                ("TRADE_CLOSED", "TRADE_FAILED", "PAYERROR"))),
        ),
    )
    succeeded_refunds = db.query(PaymentRefund.payment_order_id).filter(
        PaymentRefund.status == "succeeded"
    )
    safe_refunded_terminal = and_(
        PaymentOrder.status == "refunded",
        PaymentOrder.id.in_(succeeded_refunds),
    )
    # Explicitly coalesce nullable status expressions: SQL NOT UNKNOWN would
    # otherwise silently drop ambiguous rows rather than fail closed.
    add("unsettled_payments", "存在未确认、未关闭或待复核的充值支付，请联系平台核对；本地超时不代表支付平台已关闭订单。",
        db.query(PaymentOrder).filter(PaymentOrder.user_id == user.id, ~or_(
            and_(PaymentOrder.status == "paid", PaymentOrder.credited_at.isnot(None)),
            safe_refunded_terminal,
            func.coalesce(safe_unpaid_terminal, False),
        )))
    add("unsettled_withdrawals", "存在待审核或待打款的提现，请先完成核对。",
        db.query(WithdrawalOrder).filter(
            WithdrawalOrder.user_id == user.id,
            WithdrawalOrder.status.notin_(("paid", "rejected", "failed", "canceled", "cancelled")),
        ))
    add("unsettled_funding", "存在未结清的订单资金分配，请联系平台核对。",
        db.query(OrderFundingAllocation).filter(
            OrderFundingAllocation.order_id.in_(orders),
            OrderFundingAllocation.status.notin_(("captured", "refunded")),
        ))
    add("unsettled_merchant_sales", "存在未完成的商家结算，请先完成结算。",
        db.query(MerchantSettlement).filter(
            or_(MerchantSettlement.supplier_user_id == user.id, MerchantSettlement.buyer_user_id == user.id),
            or_(MerchantSettlement.status.notin_(("settled", "refunded", "cancelled", "canceled")),
                and_(MerchantSettlement.status == "settled", MerchantSettlement.ledger_id.is_(None))),
        ))
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if wallet and any(Decimal(str(getattr(wallet, field) or 0)) != 0 for field in WALLET_BUCKETS):
        blockers.append({"code": "wallet_not_empty", "message": "账户仍有余额、冻结资金或其他卡时权益，请先核对处理；注销不会自动清零。", "count": 1})
    relationships = db.query(InviteRecord.id).filter(or_(
        InviteRecord.inviter_id == user.id, InviteRecord.invitee_id == user.id,
    ))
    add("pending_rewards", "存在本人或关联交易、邀请关系的待结算返佣，请先结算。",
        db.query(RewardAccrual).filter(
            or_(RewardAccrual.beneficiary_user_id == user.id, RewardAccrual.order_id.in_(orders),
                and_(RewardAccrual.source_type == "invite_record", RewardAccrual.source_id.in_(relationships))),
            RewardAccrual.status.notin_(("settled", "forfeited", "cancelled", "canceled")),
        ))
    add("legacy_pending_rewards", "历史资产仍有待处理返佣，请联系平台核对。",
        db.query(Asset).filter(
            or_(Asset.user_id == user.id, Asset.product_id.in_(products)),
            Asset.rebate_status == "pending",
        ))
    add("legacy_invite_rewards", "存在已触发但未完成的历史邀请奖励，请先核对。",
        db.query(InviteRecord).filter(
            or_(InviteRecord.inviter_id == user.id, InviteRecord.invitee_id == user.id),
            InviteRecord.status == "ordered", InviteRecord.rewarded_at.is_(None),
            InviteRecord.qualification_policy_version.is_(None),
        ))
    # A normal unanswered support question is not a contractual dispute.
    add("unresolved_disputes", "存在未关闭的争议工单，请先完成处理。",
        db.query(SupportTicket).filter(
            SupportTicket.user_id == user.id,
            SupportTicket.category.in_(("dispute", "delivery_dispute", "payment_dispute", "refund_dispute")),
            SupportTicket.status.notin_(("closed", "resolved", "cancelled", "canceled")),
        ))
    return blockers


def get_automatic_actions(db: Session, user: User) -> list[str]:
    """Effects explicitly confirmed by the deletion UI, not extra blockers."""
    suppliers, _, _ = _scope(db, user)
    actions = ["退出全部设备并解除算力星图的 KAI 身份绑定", "清理个人资料、实名材料、社区内容与上传附件", "保留受限访问的必要交易及财务凭证"]
    if db.query(BuyRequest.id).filter(BuyRequest.user_id == user.id, BuyRequest.status.in_(OPEN_REQUEST_STATUSES)).first():
        actions.append("撤回尚未成交的需求及其未选中报价")
    if db.query(BuyRequestQuote.id).filter(BuyRequestQuote.supplier_id.in_(suppliers), BuyRequestQuote.status == "active").first():
        actions.append("撤回商家尚未被接受的报价")
    if db.query(Product.id).filter(Product.supplier_id.in_(suppliers), Product.status == "on").first():
        actions.append("下架本账号的商家资源")
    if db.query(Coupon.id).filter(Coupon.user_id == user.id, Coupon.status == "available").first():
        actions.append("停用尚未使用的优惠券；卡时余额仍须先处理，不会自动放弃")
    return actions


def _owned_media(value: str | None, user_id: int) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path
    match = re.fullmatch(rf"/(?:api/)?uploads/community/{user_id}/([0-9a-f]{{32}}\.(?:jpg|png|webp|mp4|mov|webm))", path)
    return f"community/{user_id}/{match.group(1)}" if match else None


def scrub_account_data(db: Session, user: User) -> list[str]:
    """Stage idempotent cleanup; caller owns the transaction and file-job commit.

    Precondition: the lifecycle service has rechecked get_deletion_blockers in
    its serialized transaction. Returned paths are upload-root-relative,
    strictly user-owned names, never arbitrary client-provided disk paths.
    """
    suppliers, products, orders = _scope(db, user)
    supplier_ids = [row[0] for row in suppliers.all()]
    product_ids = {row[0] for row in products.all()}
    order_ids = [row[0] for row in orders.all()]
    files = {f"avatars/avatar_{user.id}.{ext}" for ext in ("jpg", "png", "webp")}
    files.update(f"id_cards/id_{side}_{user.id}.{ext}" for side in ("front", "back") for ext in ("jpg", "png", "webp"))

    def remove(model, *filters):
        db.query(model).filter(*filters).delete(synchronize_session="fetch")

    now = _now()
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update(
        {AuthSession.revoked_at: now}, synchronize_session="fetch")
    for model in (Address, Verification, ExternalIdentity, ExternalAuthFlow, ExternalAuthTicket,
                  ExternalAuthBindTicket, AccountRecoveryMailOutbox, AccountRecoveryToken, Notification,
                  NotificationPreference, InviteCode):
        remove(model, model.user_id == user.id)
    # Deleting the verification row makes in-flight OCR token-guarded writes
    # affect zero rows, instead of restoring identity data after deletion.
    for card in db.query(BankCard).filter(BankCard.user_id == user.id).all():
        remove(PaymentInstructionGrant, PaymentInstructionGrant.bank_card_id == card.id)
        if db.query(WithdrawalOrder.id).filter(WithdrawalOrder.bank_card_id == card.id).first():
            card.bank_name = card.holder = DELETED_LABEL
            card.card_number = ""
            card.phone = card.card_fingerprint = card.review_reason = None
            card.is_default = False
            card.status = "deleted"
        else:
            db.delete(card)
    remove(PaymentInstructionGrant, PaymentInstructionGrant.actor_user_id == user.id)
    db.query(WithdrawalOrder).filter(WithdrawalOrder.user_id == user.id).update({
        WithdrawalOrder.holder_snapshot: DELETED_LABEL,
        WithdrawalOrder.card_last4_snapshot: "",
    }, synchronize_session="fetch")
    db.query(PaymentOrder).filter(PaymentOrder.user_id == user.id).update({
        PaymentOrder.provider_checkout_url: None,
    }, synchronize_session="fetch")
    db.query(InviteRecord).filter(InviteRecord.invitee_id == user.id).update({
        InviteRecord.invitee_phone: DELETED_LABEL,
    }, synchronize_session="fetch")
    # Keep recorded historical referrals/accruals but remove live profile links.
    db.query(User).filter(User.invited_by == user.id).update({User.invited_by: None}, synchronize_session="fetch")
    for supplier in db.query(Supplier).filter(Supplier.user_id == user.id).all():
        supplier.company_name = supplier.contact = DELETED_LABEL
        supplier.phone = ""
        supplier.region = supplier.desc = None
        supplier.status = "rejected"
    for product in db.query(Product).filter(Product.supplier_id.in_(supplier_ids)).all():
        media = _owned_media(product.image_url, user.id)
        if media:
            files.add(media)
        product.status = "off"
        product.name = "已下架资源"
        product.desc = product.image_url = None
        product.city = None

    for request in db.query(BuyRequest).filter(BuyRequest.user_id == user.id).all():
        request.contact = request.phone = request.requirements = None
        if request.status in OPEN_REQUEST_STATUSES:
            request.status = "closed"
            db.query(BuyRequestQuote).filter(BuyRequestQuote.buy_request_id == request.id, BuyRequestQuote.status == "active").update({BuyRequestQuote.status: "withdrawn"}, synchronize_session="fetch")
            db.query(BuyRequestQuoteRevision).filter(BuyRequestQuoteRevision.buy_request_id == request.id, BuyRequestQuoteRevision.status == "active").update({BuyRequestQuoteRevision.status: "withdrawn"}, synchronize_session="fetch")
    for quote in db.query(BuyRequestQuote).filter(BuyRequestQuote.supplier_id.in_(supplier_ids)).all():
        quote.message = None
        if quote.status == "active":
            quote.status = "withdrawn"
            db.query(BuyRequestQuoteRevision).filter(
                BuyRequestQuoteRevision.quote_id == quote.id,
                BuyRequestQuoteRevision.status == "active",
            ).update({BuyRequestQuoteRevision.status: "withdrawn"}, synchronize_session="fetch")
            request = db.get(BuyRequest, quote.buy_request_id)
            db.flush()
            if request and request.status == "quoting" and not db.query(BuyRequestQuote.id).filter(BuyRequestQuote.buy_request_id == request.id, BuyRequestQuote.status == "active").first():
                request.status = "published"
    for revision in db.query(BuyRequestQuoteRevision).filter(BuyRequestQuoteRevision.proposer_user_id == user.id).all():
        revision.message = None
        if revision.status == "active":
            revision.status = "withdrawn"
    deal_ids = db.query(BuyRequestDeal.id).filter(
        or_(BuyRequestDeal.buyer_id == user.id, BuyRequestDeal.supplier_id.in_(supplier_ids)),
        BuyRequestDeal.status.in_(TERMINAL_DEAL_STATUSES),
    )
    # Credential audit IDs/versions/timestamps remain, encrypted secrets do not.
    db.query(BuyRequestCredential).filter(BuyRequestCredential.deal_id.in_(deal_ids)).update({
        BuyRequestCredential.protected_payload: "", BuyRequestCredential.payload_fingerprint: "",
        BuyRequestCredential.status: "deleted",
    }, synchronize_session="fetch")
    db.query(BuyRequestEvent).filter(BuyRequestEvent.actor_user_id == user.id).update({
        BuyRequestEvent.event_data: None,
    }, synchronize_session="fetch")
    for order in db.query(Order).filter(Order.id.in_(order_ids)).all():
        order.ssh_info = None
        if order.user_id == user.id:
            order.dispute_reason = None
        if order.product_snapshot and order.product_id in product_ids:
            order.product_snapshot = {**order.product_snapshot, "seller_name": DELETED_LABEL, "product_name": "已下架资源", "city": None}
    # Response snapshots contain plaintext delivery fields from order_out;
    # keep the durable numeric renewal facts in columns, not a stale secret.
    db.query(OrderRenewal).filter(OrderRenewal.order_id.in_(order_ids)).update({
        OrderRenewal.response_payload: {},
    }, synchronize_session="fetch")
    for row in db.query(OfflinePurchase).filter(OfflinePurchase.user_id == user.id).all():
        row.contact = DELETED_LABEL
        row.phone = ""
        row.remark = None
        if row.status == "submitted":
            row.status = "rejected"
    for row in db.query(ComputeOnboarding).filter(ComputeOnboarding.user_id == user.id).all():
        row.contact = DELETED_LABEL
        row.phone = ""
        row.location = row.remark = None
        row.status = "rejected"
    db.query(Coupon).filter(Coupon.user_id == user.id, Coupon.status == "available").update({Coupon.status: "expired"}, synchronize_session="fetch")

    # Preserve other authors' comments under a tombstone instead of deleting
    # their content by cascading an owned post deletion.
    for post in db.query(Post).filter(Post.user_id == user.id).all():
        try:
            image_urls = json.loads(post.images or "[]")
        except (TypeError, ValueError):
            image_urls = []
        refs = image_urls if isinstance(image_urls, list) else []
        for ref in [*refs, post.video, post.video_url, post.thumbnail_url]:
            media = _owned_media(ref, user.id) if isinstance(ref, str) else None
            if media:
                files.add(media)
        post.content = "[内容已删除]"
        for field in ("images", "video", "video_duration", "topic", "content_en", "topic_en",
                      "source_key", "source_name", "source_url", "source_item_id", "source_author",
                      "summary", "video_provider", "video_id", "video_url", "embed_url",
                      "thumbnail_url", "canonical_url", "content_hash"):
            setattr(post, field, None)
    comment_posts = {row[0] for row in db.query(Comment.post_id).filter(Comment.user_id == user.id).all()}
    like_posts = {row[0] for row in db.query(Like.post_id).filter(Like.user_id == user.id).all()}
    remove(Comment, Comment.user_id == user.id)
    remove(Like, Like.user_id == user.id)
    remove(Follow, or_(Follow.follower_id == user.id, Follow.following_id == user.id))
    remove(
        CommunityBlock,
        or_(
            CommunityBlock.blocker_user_id == user.id,
            CommunityBlock.blocked_user_id == user.id,
        ),
    )
    remove(CommunityReport, CommunityReport.reporter_user_id == user.id)
    for post in db.query(Post).filter(Post.id.in_(comment_posts | like_posts)).all():
        if post.id in comment_posts:
            post.comments = db.query(Comment).filter(
                Comment.post_id == post.id,
                Comment.moderation_status == "visible",
            ).count()
        if post.id in like_posts:
            post.likes = db.query(Like).filter(Like.post_id == post.id).count()
    conversation_ids = db.query(SupportConversation.id).filter(SupportConversation.user_id == user.id)
    # Ordinary chats are deleted. Resolved dispute tickets remain minimal
    # restricted audit records with personal descriptions removed.
    db.query(SupportTicket).filter(SupportTicket.user_id == user.id).update({
        SupportTicket.subject: "账号已注销", SupportTicket.description: "[内容已删除]",
        SupportTicket.assigned_to: None, SupportTicket.status: "closed",
        SupportTicket.source_message_id: None,
    }, synchronize_session="fetch")
    db.query(SupportMessage).filter(SupportMessage.conversation_id.in_(conversation_ids)).update({SupportMessage.reply_to_id: None}, synchronize_session="fetch")
    remove(SupportMessage, SupportMessage.conversation_id.in_(conversation_ids))
    db.query(SupportConversation).filter(SupportConversation.user_id == user.id).update({SupportConversation.status: "closed"}, synchronize_session="fetch")

    user.username = DELETED_LABEL
    # A reserved, non-phone prefix plus integer primary key remains <= 20
    # characters even for a signed 64-bit ID, unique, and cannot be registered
    # through the phone-number validator.
    user.phone = f"x{user.id}"
    user.phone_bound = False
    user.password = "!account-deleted"
    user.avatar = None
    user.recovery_email = None
    user.recovery_email_fingerprint = None
    user.recovery_email_verified_at = None
    user.auth_version = int(user.auth_version or 0) + 1
    user.invited_by = None
    user.role = "personal"
    user.supplier_status = "none"
    db.flush()
    return sorted(files)
