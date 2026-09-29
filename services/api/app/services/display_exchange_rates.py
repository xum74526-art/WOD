"""Daily CNY display-currency reference rates shared by every client.

The business ledger and payment provider settle in CNY.  This module fetches
the ECB's dated EUR reference rates, derives CNY -> HKD/USD cross-rates, and
stores them durably for presentation only.  User requests never call the
upstream; they receive the last complete database snapshot through platform
capabilities.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from threading import Lock
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.display_exchange_rate import DisplayExchangeRate


SOURCE = "ECB"
SOURCE_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
BASE_CURRENCY = "CNY"
QUOTE_CURRENCIES = ("HKD", "USD")

# Bootstrap values are the official ECB 2026-09-28 cross-rates.  They are used
# only before the first successful scheduled fetch and are explicitly marked
# stale.  Once fetched, the durable latest snapshot survives API restarts.
_BOOTSTRAP_REFERENCE_DATE = date(2026, 9, 28)
_BOOTSTRAP_RATES = {
    "HKD": Decimal("1.169032900251"),
    "USD": Decimal("0.149020326907"),
}

_SYNC_LOCK = Lock()
_CONFIG_LOCK = Lock()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _public_config(
    rates: dict[str, Decimal],
    *,
    source: str,
    reference_date: date,
    force_stale: bool = False,
) -> dict:
    stale_after_days = max(int(settings.DISPLAY_FX_STALE_AFTER_DAYS), 1)
    return {
        "base_currency": BASE_CURRENCY,
        "settlement_currency": BASE_CURRENCY,
        "fraction_digits": 3,
        # Historical API/DB field names still exist, but their numeric value is
        # now direct CNY money rather than a second account unit.
        "card_hour_cny_rate": 1.0,
        "rates": {
            "CNY": 1.0,
            "HKD": float(rates["HKD"]),
            "USD": float(rates["USD"]),
        },
        "rate_mode": "daily_reference",
        "rate_source": source,
        "rate_date": reference_date.isoformat(),
        "rates_stale": force_stale or (_today() - reference_date).days > stale_after_days,
        "conversion_scope": "display_only",
    }


_CURRENT_CONFIG = _public_config(
    _BOOTSTRAP_RATES,
    source="ECB_BOOTSTRAP",
    reference_date=_BOOTSTRAP_REFERENCE_DATE,
    force_stale=True,
)


def _copy_config(config: dict) -> dict:
    return {**config, "rates": dict(config["rates"])}


def current_display_currency_config() -> dict:
    with _CONFIG_LOCK:
        return _copy_config(_CURRENT_CONFIG)


def _publish(config: dict) -> dict:
    global _CURRENT_CONFIG
    with _CONFIG_LOCK:
        _CURRENT_CONFIG = _copy_config(config)
        return _copy_config(_CURRENT_CONFIG)


def _positive_decimal(value: str | None) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid_rate") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("invalid_rate")
    return parsed


def parse_ecb_daily_rates(payload: bytes, *, today: date | None = None) -> tuple[date, dict[str, Decimal]]:
    """Parse one bounded ECB daily XML response and derive CNY cross-rates."""

    if not payload or len(payload) > max(int(settings.DISPLAY_FX_MAX_RESPONSE_BYTES), 1024):
        raise ValueError("invalid_response_size")
    # The ECB feed needs no DTD or custom entity. Reject both before parsing so
    # a compromised upstream response cannot use entity expansion or external
    # entity resolution against the API host.
    lowered_payload = payload.lower()
    if b"<!doctype" in lowered_payload or b"<!entity" in lowered_payload:
        raise ValueError("unsafe_xml")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("invalid_xml") from exc

    reference_date: date | None = None
    euro_rates: dict[str, Decimal] = {}
    for element in root.iter():
        if reference_date is None and element.attrib.get("time"):
            try:
                reference_date = date.fromisoformat(element.attrib["time"])
            except ValueError as exc:
                raise ValueError("invalid_reference_date") from exc
        currency = str(element.attrib.get("currency") or "").upper()
        if currency in {BASE_CURRENCY, *QUOTE_CURRENCIES}:
            euro_rates[currency] = _positive_decimal(element.attrib.get("rate"))

    if reference_date is None or any(code not in euro_rates for code in (BASE_CURRENCY, *QUOTE_CURRENCIES)):
        raise ValueError("missing_required_rate")

    current_date = today or _today()
    age_days = (current_date - reference_date).days
    if age_days < 0 or age_days > max(int(settings.DISPLAY_FX_MAX_REFERENCE_AGE_DAYS), 1):
        raise ValueError("reference_date_out_of_range")

    cny_per_eur = euro_rates[BASE_CURRENCY]
    rates = {
        code: (euro_rates[code] / cny_per_eur).quantize(Decimal("0.000000000001"))
        for code in QUOTE_CURRENCIES
    }
    # Wide sanity bounds reject unit inversions and malformed source data while
    # allowing normal long-term market movement without code releases.
    if not Decimal("0.1") <= rates["HKD"] <= Decimal("10"):
        raise ValueError("implausible_hkd_rate")
    if not Decimal("0.01") <= rates["USD"] <= Decimal("2"):
        raise ValueError("implausible_usd_rate")
    return reference_date, rates


def _fetch_rates() -> tuple[date, dict[str, Decimal]]:
    timeout = max(float(settings.DISPLAY_FX_HTTP_TIMEOUT_SECONDS), 1.0)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        headers={"Accept": "application/xml,text/xml", "User-Agent": "KAI-Star-FX/1.0"},
    ) as client:
        response = client.get(SOURCE_URL)
        response.raise_for_status()
        payload = response.content
    return parse_ecb_daily_rates(payload)


def _latest_complete_config(db) -> dict | None:
    complete_date_row = (
        db.query(DisplayExchangeRate.reference_date)
        .filter(
            DisplayExchangeRate.base_currency == BASE_CURRENCY,
            DisplayExchangeRate.quote_currency.in_(QUOTE_CURRENCIES),
        )
        .group_by(DisplayExchangeRate.reference_date)
        .having(func.count(func.distinct(DisplayExchangeRate.quote_currency)) == len(QUOTE_CURRENCIES))
        .order_by(DisplayExchangeRate.reference_date.desc())
        .first()
    )
    if complete_date_row is None:
        return None
    reference_date = complete_date_row[0]
    rows = db.query(DisplayExchangeRate).filter(
        DisplayExchangeRate.base_currency == BASE_CURRENCY,
        DisplayExchangeRate.reference_date == reference_date,
        DisplayExchangeRate.quote_currency.in_(QUOTE_CURRENCIES),
    ).all()
    rates = {row.quote_currency: Decimal(row.rate_per_base) for row in rows}
    if any(code not in rates for code in QUOTE_CURRENCIES):
        return None
    if not Decimal("0.1") <= rates["HKD"] <= Decimal("10"):
        raise ValueError("implausible_cached_hkd_rate")
    if not Decimal("0.01") <= rates["USD"] <= Decimal("2"):
        raise ValueError("implausible_cached_usd_rate")
    source = rows[0].source if rows else SOURCE
    return _public_config(rates, source=source, reference_date=reference_date)


def load_cached_display_exchange_rates() -> dict:
    """Load the last complete database snapshot without doing network I/O."""

    db = SessionLocal()
    try:
        config = _latest_complete_config(db)
        return _publish(config) if config is not None else current_display_currency_config()
    except (SQLAlchemyError, InvalidOperation, ValueError):
        db.rollback()
        return current_display_currency_config()
    finally:
        db.close()


def _store_snapshot(reference_date: date, rates: dict[str, Decimal]) -> dict:
    db = SessionLocal()
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        for quote_currency in QUOTE_CURRENCIES:
            row = db.query(DisplayExchangeRate).filter(
                DisplayExchangeRate.base_currency == BASE_CURRENCY,
                DisplayExchangeRate.quote_currency == quote_currency,
                DisplayExchangeRate.reference_date == reference_date,
            ).one_or_none()
            if row is None:
                row = DisplayExchangeRate(
                    base_currency=BASE_CURRENCY,
                    quote_currency=quote_currency,
                    reference_date=reference_date,
                    rate_per_base=rates[quote_currency],
                    source=SOURCE,
                    fetched_at=fetched_at,
                )
                db.add(row)
            else:
                row.rate_per_base = rates[quote_currency]
                row.source = SOURCE
                row.fetched_at = fetched_at

        retention_days = max(int(settings.DISPLAY_FX_RETENTION_DAYS), 30)
        db.query(DisplayExchangeRate).filter(
            DisplayExchangeRate.reference_date < _today() - timedelta(days=retention_days)
        ).delete(synchronize_session=False)
        db.commit()
        config = _latest_complete_config(db)
        if config is None:
            raise RuntimeError("stored_snapshot_incomplete")
        return config
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "upstream_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "upstream_http_error"
    if isinstance(exc, ValueError):
        return str(exc)[:64] or "invalid_response"
    if isinstance(exc, SQLAlchemyError):
        return "storage_error"
    return "sync_failed"


def sync_display_exchange_rates() -> dict:
    """Refresh once, retaining the last successful snapshot on any failure."""

    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "already_running", "source": SOURCE}
    try:
        reference_date, rates = _fetch_rates()
        config = _publish(_store_snapshot(reference_date, rates))
        return {
            "status": "ok",
            "source": SOURCE,
            "reference_date": config["rate_date"],
        }
    except Exception as exc:  # noqa: BLE001 - scheduled job must preserve cached availability
        load_cached_display_exchange_rates()
        return {"status": "error", "source": SOURCE, "error_code": _error_code(exc)}
    finally:
        _SYNC_LOCK.release()
