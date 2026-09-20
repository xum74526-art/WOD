import unittest
from types import SimpleNamespace

from app.core.config import Settings, settings
from app.routers.asset import sell_asset
from app.routers.order import create_order, renew_order
from app.schemas.order import OrderCreateIn, OrderRenewIn
from app.services.trade_mode import INQUIRY_ONLY_MESSAGE
from app.utils.response import BizError


class _FailIfDatabaseIsTouched:
    def __getattr__(self, name: str):
        raise AssertionError(f"database access must not occur while direct trade is disabled: {name}")


class DirectTradeModeTests(unittest.TestCase):
    def setUp(self):
        self.original_direct_trade = settings.DIRECT_TRADE_ENABLED
        settings.DIRECT_TRADE_ENABLED = False
        self.user = SimpleNamespace(id=1)
        self.db = _FailIfDatabaseIsTouched()

    def tearDown(self):
        settings.DIRECT_TRADE_ENABLED = self.original_direct_trade

    def _assert_inquiry_only(self, action) -> None:
        with self.assertRaises(BizError) as blocked:
            action()
        self.assertEqual(blocked.exception.status_code, 409)
        self.assertEqual(blocked.exception.msg, INQUIRY_ONLY_MESSAGE)

    def test_direct_trade_defaults_to_disabled(self):
        self.assertIs(Settings.model_fields["DIRECT_TRADE_ENABLED"].default, False)

    def test_all_transaction_commitment_boundaries_fail_closed(self):
        actions = {
            "create order": lambda: create_order(
                OrderCreateIn(
                    product_id=1,
                    quantity=1,
                    hours=1,
                    client_request_id="inquiry-order-0001",
                ),
                self.user,
                self.db,
                "web",
            ),
            "renew order": lambda: renew_order(
                1,
                OrderRenewIn(hours=1, client_request_id="inquiry-renew-0001"),
                self.user,
                self.db,
                "web",
            ),
            "sell asset": lambda: sell_asset(1, self.user, self.db),
        }
        for label, action in actions.items():
            with self.subTest(label=label):
                self._assert_inquiry_only(action)
