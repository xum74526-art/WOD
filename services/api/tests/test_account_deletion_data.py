import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Address, Asset, AuthSession, BankCard, BuyRequest, BuyRequestCredential,
    BuyRequestDeal, BuyRequestEvent, BuyRequestQuote, BuyRequestQuoteRevision,
    Comment, ComputeOnboarding, Coupon, ExternalAuthBindTicket, ExternalAuthFlow,
    ExternalAuthTicket, ExternalIdentity, Follow, InviteCode, InviteRecord,
    Ledger, Like, MerchantSettlement, Notification, NotificationPreference,
    OfflinePurchase, Order, OrderFundingAllocation, OrderRenewal, PaymentOrder,
    Post, Product, RewardAccrual, Supplier, SupportConversation, SupportMessage,
    SupportTicket, User, Verification, Wallet, WithdrawalOrder,
)
from app.services.account_deletion_data import (
    DELETED_LABEL, WALLET_BUCKETS, get_automatic_actions, get_deletion_blockers,
    scrub_account_data,
)


class AccountDeletionDataTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        # Match the canonical API's autoflush=False transaction behavior.
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.user = User(username="Private Name", phone="13910000001", password="old-hash")
        self.other = User(username="Other Person", phone="13910000002", password="other-hash")
        self.db.add_all([self.user, self.other])
        self.db.flush()
        self.supplier = Supplier(user_id=self.user.id, company_name="Private Company", contact="Private Contact", phone=self.user.phone, status="approved")
        self.db.add(self.supplier)
        self.db.flush()
        self.product = Product(name="GPU", gpu_model="H100", memory="80GB", price=1, supplier_id=self.supplier.id, status="on")
        self.db.add(self.product)
        self.db.flush()
        self.wallet = Wallet(user_id=self.user.id)
        self.db.add(self.wallet)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def codes(self, user=None):
        return {row["code"] for row in get_deletion_blockers(self.db, user or self.user)}

    def order(self, **values):
        row = Order(order_no=f"ORDER-{self.db.query(Order).count()}", user_id=self.other.id,
                    product_id=self.product.id, amount=10, status="done",
                    end_at=self.now - timedelta(days=1), **values)
        self.db.add(row)
        self.db.flush()
        return row

    def reward(self, *, beneficiary=None, source_type="order", source_id=1, order_id=None):
        row = RewardAccrual(program_code="test", policy_version="test", beneficiary_user_id=beneficiary or self.user.id,
                            source_type=source_type, source_id=source_id, order_id=order_id, period_key="2026-09",
                            base_amount=10, rate_bps=100, reward_amount=1, policy_snapshot={}, due_at=self.now,
                            status="pending", idempotency_key=f"test-{source_type}-{source_id}")
        self.db.add(row)
        self.db.flush()
        return row

    def deal(self, status="completed"):
        request = BuyRequest(user_id=self.other.id, request_type="online", gpu_model="H100", status="completed")
        self.db.add(request)
        self.db.flush()
        quote = BuyRequestQuote(buy_request_id=request.id, supplier_id=self.supplier.id, total_price=10, status="completed")
        self.db.add(quote)
        self.db.flush()
        revision = BuyRequestQuoteRevision(quote_id=quote.id, buy_request_id=request.id, supplier_id=self.supplier.id,
                                           revision_number=1, proposer_role="supplier", proposer_user_id=self.user.id,
                                           total_price=10, message="private quote", status="selected")
        self.db.add(revision)
        self.db.flush()
        row = BuyRequestDeal(buy_request_id=request.id, quote_id=quote.id, selected_revision_id=revision.id,
                             buyer_id=self.other.id, supplier_id=self.supplier.id, status=status)
        self.db.add(row)
        self.db.flush()
        return row

    def test_empty_account_and_ordinary_support_are_not_blocked(self):
        conversation = SupportConversation(user_id=self.user.id, status="open")
        self.db.add(conversation)
        self.db.flush()
        self.db.add(SupportMessage(conversation_id=conversation.id, user_id=self.user.id, role="user", content="How to delete?"))
        self.db.add(SupportTicket(ticket_no="NORMAL", user_id=self.user.id, conversation_id=conversation.id,
                                  subject="Help", description="Question", category="other", status="pending_unassigned"))
        self.db.commit()
        self.assertEqual(self.codes(), set())
        self.assertTrue(any("下架" in value for value in get_automatic_actions(self.db, self.user)))
        self.assertEqual(self.product.status, "on")

    def test_every_wallet_bucket_blocks_without_changing_amounts(self):
        for bucket in WALLET_BUCKETS:
            for amount in (Decimal("0.000001"), Decimal("-0.000001")):
                with self.subTest(bucket=bucket, amount=amount):
                    setattr(self.wallet, bucket, amount)
                    self.db.flush()
                    self.assertIn("wallet_not_empty", self.codes())
                    self.assertEqual(getattr(self.wallet, bucket), amount)
                    setattr(self.wallet, bucket, Decimal(0))
        self.db.flush()
        self.assertNotIn("wallet_not_empty", self.codes())

    def test_completed_order_can_still_be_active_for_buyer_and_supplier(self):
        order = self.order()
        order.status = "completed"
        order.end_at = self.now + timedelta(days=1)
        self.db.flush()
        self.assertIn("active_orders", self.codes())
        self.assertIn("active_orders", self.codes(self.other))
        order.end_at = self.now - timedelta(days=1)
        self.db.flush()
        self.assertNotIn("active_orders", self.codes())
        asset = Asset(user_id=self.other.id, product_id=self.product.id, order_id=order.id, status="active")
        self.db.add(asset)
        self.db.flush()
        self.assertIn("active_assets", self.codes())
        self.assertIn("active_assets", self.codes(self.other))
        asset.status = "expired"
        order.status = "unexpected"
        self.db.flush()
        self.assertIn("active_orders", self.codes())

    def test_future_renewal_and_unsettled_funding_block(self):
        order = self.order()
        renewal = OrderRenewal(order_id=order.id, user_id=self.other.id, client_request_id="r1", amount=1,
                               new_end_at=self.now + timedelta(days=1), total_amount_after=11, response_payload={})
        self.db.add(renewal)
        self.db.flush()
        self.assertIn("active_renewals", self.codes())
        funding = OrderFundingAllocation(source_type="order", source_id=order.id, order_id=order.id,
                                         user_id=self.user.id, wallet_id=self.wallet.id, gross_amount=1,
                                         cash_amount=1, promotional_amount=0, policy_version="test", status="frozen", policy_snapshot={})
        self.db.add(funding)
        self.db.flush()
        self.assertIn("unsettled_funding", self.codes())

    def test_matchmaking_and_legacy_selection_block_both_sides(self):
        deal = self.deal("credential_released")
        self.assertIn("active_matchmaking", self.codes())
        self.assertIn("active_matchmaking", self.codes(self.other))
        deal.status = "completed"
        request = self.db.get(BuyRequest, deal.buy_request_id)
        request.status = "quote_selected"
        self.db.get(BuyRequestQuote, deal.quote_id).status = "selected"
        self.db.flush()
        self.assertIn("unresolved_requests", self.codes())
        self.assertIn("unresolved_requests", self.codes(self.other))
        request.status = "completed"
        self.db.flush()
        self.assertEqual(self.codes(), set())

    def test_rewards_block_through_order_and_invite_not_just_beneficiary(self):
        order = self.order()
        accrual = self.reward(beneficiary=self.other.id, order_id=order.id)
        self.assertIn("pending_rewards", self.codes())
        accrual.status = "settled"
        record = InviteRecord(inviter_id=self.other.id, invitee_id=self.user.id, invitee_phone="139****0001")
        self.db.add(record)
        self.db.flush()
        self.reward(beneficiary=self.other.id, source_type="invite_record", source_id=record.id)
        self.assertIn("pending_rewards", self.codes())
        self.assertIn("pending_rewards", self.codes(self.other))

    def test_review_and_uncertain_payments_and_true_dispute_block(self):
        payment = PaymentOrder(order_no="PAY", user_id=self.user.id, provider="qixiangpay", amount_cny=1, card_hours=1, card_hour_rate=1,
                               checkout_token_hash="p" * 64, expires_at=self.now, status="expired", provider_status="CREATE_UNKNOWN")
        self.db.add(payment)
        self.db.flush()
        self.assertIn("unsettled_payments", self.codes())
        payment.provider_status = "CLOSED"
        self.db.flush()
        self.assertIn("unsettled_payments", self.codes())
        payment.provider_status = "CREATE_FAILED"
        self.db.flush()
        self.assertNotIn("unsettled_payments", self.codes())
        payment.status = "paid"
        self.db.flush()
        self.assertIn("unsettled_payments", self.codes())
        payment.credited_at = self.now
        conversation = SupportConversation(user_id=self.user.id)
        self.db.add(conversation)
        self.db.flush()
        ticket = SupportTicket(ticket_no="DISPUTE", user_id=self.user.id, conversation_id=conversation.id,
                                subject="Dispute", description="Private", category="delivery_dispute")
        self.db.add(ticket)
        self.db.flush()
        self.assertIn("unresolved_disputes", self.codes())
        ticket.status = "resolved"
        self.db.flush()
        self.assertEqual(self.codes(), set())

    def test_payment_local_expiry_never_means_upstream_closed(self):
        payment = PaymentOrder(order_no="LATE", user_id=self.user.id, provider="qixiangpay", amount_cny=1,
                               card_hours=1, card_hour_rate=1, checkout_token_hash="l" * 64,
                               expires_at=self.now - timedelta(days=20), status="expired")
        self.db.add(payment)
        self.db.flush()
        self.assertNotIn("unsettled_payments", self.codes())
        for field, value in (("checkout_started_at", self.now), ("provider_checkout_url", "https://pay.invalid/old"),
                             ("provider_trade_no", "upstream-1")):
            with self.subTest(artifact=field):
                setattr(payment, field, value)
                for status in ("expired", "failed", "canceled"):
                    payment.status = status
                    self.db.flush()
                    self.assertIn("unsettled_payments", self.codes())
                setattr(payment, field, None)
        # Even an unpaid query does not close an order at Qixiang.
        payment.provider_status = "0"
        self.db.flush()
        self.assertIn("unsettled_payments", self.codes())
        payment.provider_status = "CREATE_FAILED"
        self.db.flush()
        self.assertNotIn("unsettled_payments", self.codes())
        # MaPay's old browser form did not persist checkout_started_at.
        payment.provider = "mapay"
        payment.provider_status = None
        self.db.flush()
        self.assertIn("unsettled_payments", self.codes())
        for provider_status in ("TRADE_CLOSED", "TRADE_FAILED", "PAYERROR"):
            payment.provider_status = provider_status
            self.db.flush()
            self.assertNotIn("unsettled_payments", self.codes())
        # Unknown provider/status is not proof of a safely closed payment.
        payment.provider = "unknown"
        self.db.flush()
        self.assertIn("unsettled_payments", self.codes())
        # A credited history row is idempotent, irrespective of artefacts,
        # age, or the old provider. It must never block deletion indefinitely.
        payment.status = "paid"
        payment.credited_at = self.now
        payment.provider_checkout_url = "https://pay.invalid/old"
        self.db.flush()
        self.assertNotIn("unsettled_payments", self.codes())

    def test_withdrawal_settlement_and_legacy_obligations_block(self):
        card = BankCard(user_id=self.user.id, bank_name="Bank", card_number="secret", holder="Holder")
        self.db.add(card)
        self.db.flush()
        withdrawal = WithdrawalOrder(order_no="PENDING", user_id=self.user.id, wallet_id=self.wallet.id,
                                     bank_card_id=card.id, client_request_id="w1", amount_card_hours=1,
                                     locked_rate_cny=1, gross_amount_cny=1, net_amount_cny=1,
                                     bank_name_snapshot="Bank", card_last4_snapshot="1234", holder_snapshot="Holder")
        order = self.order()
        settlement = MerchantSettlement(event_key="s", policy_version="test", source_type="order", source_id=order.id,
                                        order_id=order.id, buyer_user_id=self.other.id, supplier_id=self.supplier.id,
                                        supplier_user_id=self.user.id, wallet_id=self.wallet.id, gross_amount=1,
                                        service_fee_bps=20, service_fee_amount=Decimal("0.002"), net_amount=Decimal("0.998"),
                                        policy_snapshot={}, status="settled", settled_at=self.now)
        asset = Asset(user_id=self.user.id, product_id=self.product.id, status="expired", rebate_status="pending")
        invite = InviteRecord(inviter_id=self.other.id, invitee_id=self.user.id, invitee_phone="masked", status="ordered")
        offline = OfflinePurchase(user_id=self.user.id, device_model="H100", contact="Private", phone="13900000000", status="contacted")
        self.db.add_all([withdrawal, settlement, asset, invite, offline])
        self.db.flush()
        self.assertTrue({"unsettled_withdrawals", "unsettled_merchant_sales", "legacy_pending_rewards",
                         "legacy_invite_rewards", "offline_cooperation"}.issubset(self.codes()))
        self.assertIn("unsettled_merchant_sales", self.codes(self.other))
        self.assertEqual(settlement.net_amount, Decimal("0.998"))

    def test_unused_bank_card_and_intake_details_are_scrubbed(self):
        card = BankCard(user_id=self.user.id, bank_name="Bank", card_number="secret", holder="Holder")
        offline = OfflinePurchase(user_id=self.user.id, device_model="H100", contact="Private", phone="13900000000", remark="private")
        onboarding = ComputeOnboarding(user_id=self.user.id, contact="Private", phone="13900000000", device_model="H100", location="Private address", remark="Private")
        coupon = Coupon(user_id=self.user.id, name="Promo", amount=10, status="available")
        invite = InviteRecord(inviter_id=self.other.id, invitee_id=self.user.id, invitee_phone="139****0001")
        self.other.invited_by = self.user.id
        self.db.add_all([card, offline, onboarding, coupon, invite])
        self.db.commit()
        self.assertEqual(self.codes(), set())
        self.assertTrue(any("优惠券" in action for action in get_automatic_actions(self.db, self.user)))
        scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertEqual(self.db.query(BankCard).count(), 0)
        self.assertEqual(offline.phone, "")
        self.assertIsNone(offline.remark)
        self.assertEqual(offline.status, "rejected")
        self.assertIsNone(onboarding.location)
        self.assertEqual(coupon.status, "expired")
        self.assertEqual(coupon.amount, Decimal(10))
        self.assertIsNone(self.other.invited_by)
        self.assertEqual(invite.invitee_phone, DELETED_LABEL)
        self.assertEqual(invite.inviter_id, self.other.id)

    def test_supplier_withdrawal_preserves_buyer_counteroffer_text(self):
        request = BuyRequest(user_id=self.other.id, request_type="online", gpu_model="H100", status="quoting")
        self.db.add(request)
        self.db.flush()
        quote = BuyRequestQuote(buy_request_id=request.id, supplier_id=self.supplier.id, total_price=10, status="active")
        self.db.add(quote)
        self.db.flush()
        revision = BuyRequestQuoteRevision(quote_id=quote.id, buy_request_id=request.id, supplier_id=self.supplier.id,
                                           revision_number=1, proposer_role="buyer", proposer_user_id=self.other.id,
                                           total_price=9, message="Other author's terms", status="active")
        self.db.add(revision)
        self.db.commit()
        scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertEqual(request.status, "published")
        self.assertEqual(quote.status, "withdrawn")
        self.assertEqual(revision.status, "withdrawn")
        self.assertEqual(revision.message, "Other author's terms")

    def test_personal_data_erasure_keeps_financial_rows_and_foreign_keys(self):
        self.user.avatar = f"/user/avatars/avatar_{self.user.id}.png?v=1"
        card = BankCard(user_id=self.user.id, bank_name="Private Bank", card_number="encrypted-card",
                        holder="Private Holder", phone="encrypted-phone", card_fingerprint="fp")
        self.db.add(card)
        self.db.flush()
        withdrawal = WithdrawalOrder(order_no="WITHDRAWAL", user_id=self.user.id, wallet_id=self.wallet.id,
                                     bank_card_id=card.id, client_request_id="withdraw1", status="paid",
                                     amount_card_hours=1, locked_rate_cny=1, gross_amount_cny=1, net_amount_cny=1,
                                     bank_name_snapshot="Bank", card_last4_snapshot="1234", holder_snapshot="Holder")
        ledger = Ledger(user_id=self.user.id, wallet_id=self.wallet.id, type="historical", direction="in", amount=12, remark="retained audit")
        self.db.add_all([withdrawal, ledger,
            Verification(user_id=self.user.id, real_name="Private", id_card="secret", front_photo="private.png", ocr_input_token="old"),
            Address(user_id=self.user.id, name="Name", phone="13900000000", province="A", city="B", district="C", detail="Private"),
            ExternalIdentity(user_id=self.user.id, issuer="issuer", subject="subject", email="private@example.invalid"),
            ExternalAuthTicket(user_id=self.user.id, ticket_hash="t" * 64, expires_at=self.now),
            ExternalAuthFlow(user_id=self.user.id, state_hash="s" * 64, code_verifier="secret", nonce="nonce", return_url="/", expires_at=self.now),
            ExternalAuthBindTicket(user_id=self.user.id, ticket_hash="b" * 64, issuer="issuer", subject="subject", expires_at=self.now),
            AuthSession(id="session", user_id=self.user.id, auth_method="password", expires_at=self.now + timedelta(days=1)),
            InviteCode(user_id=self.user.id, code="PRIVATECODE"),
            Notification(user_id=self.user.id, title="Private"),
            NotificationPreference(user_id=self.user.id),
        ])
        self.db.commit()
        with patch("pathlib.Path.unlink", side_effect=AssertionError("must not unlink")):
            files = scrub_account_data(self.db, self.user)
            self.db.commit()
            again = scrub_account_data(self.db, self.user)
            self.db.commit()
        self.assertEqual(files, again)
        self.assertIn(f"avatars/avatar_{self.user.id}.png", files)
        self.assertEqual(len(files), 9)
        self.assertEqual(self.user.username, DELETED_LABEL)
        self.assertFalse(self.user.phone.isdigit())
        self.assertLessEqual(len(self.user.phone), 20)
        self.assertEqual(card.card_number, "")
        self.assertEqual(withdrawal.holder_snapshot, DELETED_LABEL)
        self.assertEqual(self.db.get(Ledger, ledger.id).amount, Decimal(12))
        self.assertEqual(self.wallet.balance, Decimal(0))
        self.assertIsNotNone(self.db.get(AuthSession, "session").revoked_at)
        for model in (Verification, Address, ExternalIdentity, ExternalAuthTicket, ExternalAuthBindTicket, ExternalAuthFlow, InviteCode, Notification, NotificationPreference):
            self.assertEqual(self.db.query(model).count(), 0, model.__name__)
        self.assertEqual(self.db.execute(text("PRAGMA foreign_key_check")).all(), [])
        self.assertEqual(self.other.username, "Other Person")
        self.assertEqual(self.db.query(WithdrawalOrder).count(), 1)

    def test_cleanup_is_transactional_not_committed_by_helper(self):
        scrub_account_data(self.db, self.user)
        self.db.rollback()
        self.db.refresh(self.user)
        self.db.refresh(self.product)
        self.assertEqual(self.user.username, "Private Name")
        self.assertEqual(self.product.status, "on")

    def test_community_tombstone_preserves_other_authors_and_counts(self):
        owned_url = f"/uploads/community/{self.user.id}/{'a' * 32}.png"
        other_url = f"/uploads/community/{self.other.id}/{'b' * 32}.png"
        post = Post(user_id=self.user.id, content="private", images=json.dumps([owned_url, other_url, "https://other.example/private.png"]), comments=2, likes=2)
        other_post = Post(user_id=self.other.id, content="keep me", comments=2, likes=1)
        self.db.add_all([post, other_post])
        self.db.flush()
        other_comment = Comment(post_id=post.id, user_id=self.other.id, content="do not erase")
        self.db.add_all([other_comment, Comment(post_id=post.id, user_id=self.user.id, content="private"),
                         Comment(post_id=other_post.id, user_id=self.user.id, content="private"),
                         Comment(post_id=other_post.id, user_id=self.other.id, content="stay"),
                         Like(post_id=post.id, user_id=self.user.id), Like(post_id=post.id, user_id=self.other.id),
                         Like(post_id=other_post.id, user_id=self.user.id),
                         Follow(follower_id=self.user.id, following_id=self.other.id)])
        self.db.commit()
        files = scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertIn(f"community/{self.user.id}/{'a' * 32}.png", files)
        self.assertFalse(any(f"community/{self.other.id}/" in file for file in files))
        self.assertEqual(post.content, "[内容已删除]")
        self.assertIsNone(post.images)
        self.assertEqual(other_comment.content, "do not erase")
        self.assertEqual((post.comments, post.likes), (1, 1))
        self.assertEqual(other_post.content, "keep me")
        self.assertEqual((other_post.comments, other_post.likes), (1, 0))
        scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertEqual((post.comments, post.likes, other_post.comments), (1, 1, 1))

    def test_unaccepted_requests_and_quotes_are_closed_without_changing_prices(self):
        request = BuyRequest(user_id=self.user.id, request_type="online", gpu_model="H100", status="quoting", contact="Private", phone="13900000000", requirements={"wechat": "private"})
        self.db.add(request)
        self.db.flush()
        quote = BuyRequestQuote(buy_request_id=request.id, supplier_id=self.supplier.id, total_price=123, status="active", message="private")
        self.db.add(quote)
        self.db.flush()
        self.assertEqual(self.codes(), set())
        scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertEqual(request.status, "closed")
        self.assertIsNone(request.requirements)
        self.assertEqual(quote.status, "withdrawn")
        self.assertEqual(quote.total_price, Decimal(123))
        self.assertEqual(self.product.price, Decimal(1))
        self.assertEqual(self.product.status, "off")

    def test_completed_delivery_credentials_removed_but_audit_rows_remain(self):
        deal = self.deal()
        credential = BuyRequestCredential(deal_id=deal.id, protected_payload="encrypted-secret", payload_fingerprint="hash",
                                          envelope_namespace="test", submitted_by=self.user.id, status="released")
        order = self.order()
        order.ssh_info = "encrypted-ssh"
        renewal = OrderRenewal(order_id=order.id, user_id=self.other.id, client_request_id="history", amount=1,
                               new_end_at=self.now - timedelta(days=1), total_amount_after=11,
                               response_payload={"ssh_info": "plaintext secret", "amount": 11})
        self.db.add_all([credential, renewal])
        self.db.commit()
        scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertEqual(credential.protected_payload, "")
        self.assertEqual(credential.status, "deleted")
        self.assertEqual(self.db.get(BuyRequestDeal, deal.id).status, "completed")
        self.assertIsNone(order.ssh_info)
        self.assertEqual(renewal.response_payload, {})
        self.assertEqual(renewal.amount, Decimal(1))
        self.assertEqual(self.db.execute(text("PRAGMA foreign_key_check")).all(), [])

    def test_support_self_references_cleanup_and_other_chat_preserved(self):
        own = SupportConversation(user_id=self.user.id)
        other = SupportConversation(user_id=self.other.id)
        self.db.add_all([own, other])
        self.db.flush()
        question = SupportMessage(conversation_id=own.id, user_id=self.user.id, role="user", content="Private")
        self.db.add(question)
        self.db.flush()
        answer = SupportMessage(conversation_id=own.id, user_id=self.user.id, role="assistant", content="Private echoed", reply_to_id=question.id)
        other_message = SupportMessage(conversation_id=other.id, user_id=self.other.id, role="user", content="keep")
        ticket = SupportTicket(ticket_no="TICKET", user_id=self.user.id, conversation_id=own.id,
                                source_message_id=question.id, subject="Private", description="Private")
        self.db.add_all([answer, other_message, ticket])
        self.db.commit()
        scrub_account_data(self.db, self.user)
        self.db.commit()
        self.assertEqual(self.db.query(SupportMessage).count(), 1)
        self.assertEqual(other_message.content, "keep")
        self.assertEqual(ticket.description, "[内容已删除]")
        self.assertIsNone(ticket.source_message_id)
        self.assertEqual(self.db.execute(text("PRAGMA foreign_key_check")).all(), [])


if __name__ == "__main__":
    unittest.main()
