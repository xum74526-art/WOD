import hashlib
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import PaymentOrder, User, Wallet  # noqa: F401
from app.services.qixiangpay import (
    canonicalize,
    create_recharge_order,
    handle_notification,
    provider_configured,
    public_config,
    sign_params,
    verify_params,
)


class QiXiangPayPaymentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(phone="13900000911", username="七象支付测试", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.wallet = Wallet(user_id=self.user.id, balance=Decimal("10"), frozen=Decimal("0"))
        self.db.add(self.wallet)
        self.db.commit()
        names = (
            "PAYMENT_SERVICE_ENABLED", "QIXIANGPAY_ENABLED", "QIXIANGPAY_BASE_URL",
            "QIXIANGPAY_PID", "QIXIANGPAY_KEY", "QIXIANGPAY_NOTIFY_URL",
            "QIXIANGPAY_RETURN_URL", "QIXIANGPAY_PAYMENT_TYPES", "QIXIANGPAY_DEVICE",
            "QIXIANGPAY_HTTP_TIMEOUT", "QIXIANGPAY_CHECKOUT_TTL_SECONDS",
            "QIXIANGPAY_MIN_AMOUNT_CNY", "QIXIANGPAY_MAX_AMOUNT_CNY",
            "CARD_HOUR_RMB_RATE",
        )
        self.original = {name: getattr(settings, name) for name in names}
        settings.PAYMENT_SERVICE_ENABLED = True
        settings.QIXIANGPAY_ENABLED = True
        settings.QIXIANGPAY_BASE_URL = "https://api.payqixiang.cn"
        settings.QIXIANGPAY_PID = "4611"
        settings.QIXIANGPAY_KEY = "test-merchant-key"
        settings.QIXIANGPAY_NOTIFY_URL = "https://api.example.test/api/payments/qixiangpay/notify"
        settings.QIXIANGPAY_RETURN_URL = "https://app.example.test/account/wallet"
        settings.QIXIANGPAY_PAYMENT_TYPES = "alipay,wxpay"
        settings.QIXIANGPAY_DEVICE = "jump"
        settings.QIXIANGPAY_HTTP_TIMEOUT = 10
        settings.QIXIANGPAY_CHECKOUT_TTL_SECONDS = 300
        settings.QIXIANGPAY_MIN_AMOUNT_CNY = 0.01
        settings.QIXIANGPAY_MAX_AMOUNT_CNY = 50000
        settings.CARD_HOUR_RMB_RATE = 1.002

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()

    @staticmethod
    def _response(payload: dict) -> Mock:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def _create_order(self, trade_no: str = "QX-TEST-0001") -> dict:
        response = self._response({
            "code": 1,
            "msg": "success",
            "trade_no": trade_no,
            "payurl": "https://api.payqixiang.cn/pay/submit/test-order/",
        })
        with patch("app.services.qixiangpay.httpx.post", return_value=response) as provider_post:
            output = create_recharge_order(
                self.db,
                self.user.id,
                Decimal("0.01"),
                payment_type="alipay",
            )
        sent = provider_post.call_args.kwargs["data"]
        self.assertTrue(verify_params(sent))
        self.assertNotIn(settings.QIXIANGPAY_KEY, str(sent))
        return output

    def test_md5_signature_uses_ascii_sorted_nonempty_fields(self):
        params = {"z": "2", "a": "1", "empty": "", "sign_type": "MD5"}
        self.assertEqual(canonicalize(params), "a=1&z=2")
        expected = hashlib.md5(b"a=1&z=2test-merchant-key").hexdigest()
        self.assertEqual(sign_params(params), expected)
        params["sign"] = expected
        self.assertTrue(verify_params(params))
        params["z"] = "3"
        self.assertFalse(verify_params(params))

    def test_provider_requires_https_callbacks_and_exposes_no_key(self):
        self.assertTrue(provider_configured())
        config = public_config()
        self.assertEqual(config["provider"], "qixiangpay")
        self.assertEqual(config["sign_version"], "MD5")
        self.assertNotIn("key", config)
        settings.QIXIANGPAY_NOTIFY_URL = "http://api.example.test/notify"
        self.assertFalse(provider_configured())

    def test_checkout_and_signed_notification_credit_exactly_once(self):
        output = self._create_order()
        self.assertEqual(output["provider"], "qixiangpay")
        self.assertEqual(output["checkout_url"], "https://api.payqixiang.cn/pay/submit/test-order/")
        order = self.db.query(PaymentOrder).filter(PaymentOrder.order_no == output["order_no"]).one()
        params = {
            "pid": settings.QIXIANGPAY_PID,
            "trade_no": "QX-TEST-0001",
            "out_trade_no": order.order_no,
            "type": "alipay",
            "name": "KAI钱包卡时充值",
            "money": "0.01",
            "trade_status": "TRADE_SUCCESS",
            "param": order.order_no,
            "sign_type": "MD5",
        }
        params["sign"] = sign_params(params)
        self.assertTrue(handle_notification(self.db, params))
        self.assertTrue(handle_notification(self.db, params))
        self.db.refresh(self.wallet)
        self.assertEqual(Decimal(self.wallet.balance), Decimal("10.009980"))
        self.assertEqual(self.db.query(PaymentOrder).filter(PaymentOrder.credited_at.is_not(None)).count(), 1)

    def test_tampered_notification_never_credits_wallet(self):
        output = self._create_order("QX-TEST-0002")
        order = self.db.query(PaymentOrder).filter(PaymentOrder.order_no == output["order_no"]).one()
        params = {
            "pid": settings.QIXIANGPAY_PID,
            "trade_no": "QX-TEST-0002",
            "out_trade_no": order.order_no,
            "type": "alipay",
            "money": "0.01",
            "trade_status": "TRADE_SUCCESS",
            "param": order.order_no,
            "sign_type": "MD5",
        }
        params["sign"] = sign_params(params)
        params["money"] = "100.00"
        self.assertFalse(verify_params(params))
        with self.assertRaisesRegex(Exception, "签名无效"):
            handle_notification(self.db, params)
        self.db.refresh(self.wallet)
        self.assertEqual(Decimal(self.wallet.balance), Decimal("10.000000"))


if __name__ == "__main__":
    unittest.main()
