import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.display_exchange_rate import DisplayExchangeRate
from app.services import display_exchange_rates as fx


ECB_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<gesmes:Envelope xmlns:gesmes='http://www.gesmes.org/xml/2002-08-01'
 xmlns='http://www.ecb.int/vocabulary/2002-08-01/eurofxref'>
  <Cube><Cube time='2026-09-28'>
    <Cube currency='USD' rate='1.1378'/>
    <Cube currency='CNY' rate='7.6352'/>
    <Cube currency='HKD' rate='8.9258'/>
  </Cube></Cube>
</gesmes:Envelope>"""


class DisplayExchangeRateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        DisplayExchangeRate.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def tearDown(self):
        self.engine.dispose()

    def test_ecb_eur_quotes_are_derived_into_cny_cross_rates(self):
        reference_date, rates = fx.parse_ecb_daily_rates(
            ECB_XML,
            today=date(2026, 9, 29),
        )

        self.assertEqual(reference_date, date(2026, 9, 28))
        self.assertEqual(rates["HKD"], Decimal("1.169032900251"))
        self.assertEqual(rates["USD"], Decimal("0.149020326907"))
        self.assertEqual((Decimal("100") * rates["HKD"]).quantize(Decimal("0.001")), Decimal("116.903"))
        self.assertEqual((Decimal("100") * rates["USD"]).quantize(Decimal("0.001")), Decimal("14.902"))

    def test_malformed_or_incomplete_reference_payload_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing_required_rate"):
            fx.parse_ecb_daily_rates(
                ECB_XML.replace(b"currency='HKD'", b"currency='GBP'"),
                today=date(2026, 9, 29),
            )

    def test_dtd_and_entity_declarations_are_rejected_before_xml_parsing(self):
        with self.assertRaisesRegex(ValueError, "unsafe_xml"):
            fx.parse_ecb_daily_rates(
                b"<!DOCTYPE rates [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><rates>&xxe;</rates>",
                today=date(2026, 9, 29),
            )

    def test_refresh_is_idempotent_and_keeps_last_success_on_outage(self):
        bootstrap = fx._public_config(  # noqa: SLF001 - isolates module cache in this unit test
            fx._BOOTSTRAP_RATES,
            source="TEST_BOOTSTRAP",
            reference_date=date(2026, 9, 28),
            force_stale=True,
        )
        parsed = fx.parse_ecb_daily_rates(ECB_XML, today=date(2026, 9, 29))
        with (
            patch.object(fx, "SessionLocal", self.sessions),
            patch.object(fx, "_CURRENT_CONFIG", bootstrap),
            patch.object(fx, "_fetch_rates", return_value=parsed),
        ):
            first = fx.sync_display_exchange_rates()
            second = fx.sync_display_exchange_rates()
            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["status"], "ok")
            with self.sessions() as db:
                self.assertEqual(db.query(DisplayExchangeRate).count(), 2)

            current = fx.current_display_currency_config()
            self.assertEqual(current["rates"]["HKD"], 1.169032900251)
            self.assertEqual(current["rates"]["USD"], 0.149020326907)
            self.assertEqual(current["rate_date"], "2026-09-28")
            self.assertEqual(current["settlement_currency"], "CNY")
            self.assertEqual(current["conversion_scope"], "display_only")

            with patch.object(fx, "_fetch_rates", side_effect=httpx.TimeoutException("timeout")):
                failed = fx.sync_display_exchange_rates()
            self.assertEqual(failed, {
                "status": "error",
                "source": "ECB",
                "error_code": "upstream_timeout",
            })
            self.assertEqual(
                fx.current_display_currency_config()["rates"],
                current["rates"],
            )


if __name__ == "__main__":
    unittest.main()
