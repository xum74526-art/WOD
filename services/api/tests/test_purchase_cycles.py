import unittest
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.routers.order import _calc_kai_hour_amount, _calc_legacy_day_amount
from app.schemas.order import OrderCreateIn
from app.services.purchase_cycles import PURCHASE_CYCLE_DAYS, available_purchase_cycles


class PurchaseCycleTests(unittest.TestCase):
    def test_default_purchase_cycles_include_long_terms(self):
        self.assertEqual(available_purchase_cycles(), list(PURCHASE_CYCLE_DAYS))

    def test_purchase_cycles_preserve_valid_custom_values(self):
        self.assertEqual(
            available_purchase_cycles([30, "45", 0, None, "invalid"]),
            [1, 7, 30, 45, 90, 180, 365],
        )

    def test_order_amount_multiplies_quantity(self):
        product = SimpleNamespace(price=Decimal("1.98"))
        self.assertEqual(_calc_legacy_day_amount(product, 30, 3), Decimal("4276.8000"))

    def test_kai_hour_amount_converts_cny_to_wallet_card_hours(self):
        product = SimpleNamespace(price=Decimal("1.002"))
        self.assertEqual(_calc_kai_hour_amount(product, 6, 2), Decimal("12.0000"))

    def test_order_hours_are_integer_and_bounded(self):
        self.assertEqual(OrderCreateIn(product_id=1, hours=24).hours, 24)
        with self.assertRaises(ValidationError):
            OrderCreateIn(product_id=1, hours=0)
        with self.assertRaises(ValidationError):
            OrderCreateIn(product_id=1, hours=721)

    def test_order_quantity_is_bounded(self):
        with self.assertRaises(ValidationError):
            OrderCreateIn(product_id=1, quantity=0)
        with self.assertRaises(ValidationError):
            OrderCreateIn(product_id=1, quantity=100)


if __name__ == "__main__":
    unittest.main()
