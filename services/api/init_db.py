"""建表脚本：兼容旧库自动补列。"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.models import *  # noqa: F401,F403,E402
from app.models.market_price import MarketPriceCandle  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.sensitive import assert_sensitive_storage_secure  # noqa: E402

# 需要确保存在的列（兼容旧 wod.db）
_ENSURE = {
    "users": [
        "role", "supplier_status", "phone_bound", "created_platform",
        "account_status", "deleted_at", "password_set", "recovery_email",
        "recovery_email_fingerprint", "recovery_email_verified_at", "auth_version",
    ],
    "assets": ["end_at", "start_at", "purchase_type", "sell_price"],
    "orders": [
        "purchase_type", "ssh_info", "quantity", "client_request_id",
        "purchase_hours", "created_platform", "last_modified_platform", "lifecycle_policy_version",
        "delivery_due_at", "delivered_at", "confirmation_due_at", "confirmed_at",
        "canceled_at", "stock_released_at", "disputed_at", "dispute_due_at", "dispute_reason",
        "dispute_resolution", "dispute_resolution_note", "dispute_resolved_at",
        "dispute_resolved_by", "product_snapshot", "coupon_id", "coupon_discount",
    ],
    "buy_requests": ["client_request_id"],
    "order_renewals": ["created_platform"],
    "products": [
        "image_url", "region_code", "region_name", "country_code", "city",
        "market_source", "external_product_id", "stock_semantics",
        "source_max_configurable_quantity", "platform_stock_cap",
        "source_price", "source_currency", "exchange_rate", "price_updated_at",
        "stock", "version", "reliability", "supplier_id",
        "client_request_id", "create_request_hash",
    ],
    "posts": [
        "content_en", "topic_en", "origin", "content_type", "source_key",
        "source_name", "source_url", "source_item_id", "source_author",
        "source_published_at", "summary", "rights_status", "rights_checked_at",
        "video_provider", "video_id", "video_url", "embed_url", "thumbnail_url",
        "canonical_url", "content_hash", "ingested_at", "publish_batch", "video_duration",
        "created_platform", "last_modified_platform", "moderation_status",
        "moderation_reason", "moderated_by", "moderated_at",
    ],
    "comments": [
        "created_platform", "client_request_id", "moderation_status",
        "moderation_reason", "moderated_by", "moderated_at",
    ],
    "likes": ["created_platform"],
    "follows": ["created_platform"],
    "notifications": [
        "title_en", "content_en", "action_url", "dedupe_key",
        "expires_at", "deleted_at",
    ],
    "notification_broadcasts": [
        "expires_at", "revoked_at", "revoked_by_user_id", "revoke_reason",
    ],
    "verifications": [
        "ocr_status", "ocr_summary", "ocr_error_code", "ocr_updated_at",
        "ocr_input_token", "consent_at", "created_platform", "last_modified_platform",
    ],
    "wallets": [
        "withdrawable_balance", "withdraw_frozen",
        "promotional_balance", "promotional_frozen",
    ],
    "bank_cards": [
        "card_fingerprint", "status", "verification_mode", "review_reason",
        "reviewed_by", "reviewed_at", "consent_at", "consent_version",
        "updated_at", "created_platform", "last_modified_platform",
    ],
    "ledger": [
        "ref_payment_order_id", "ref_order_renewal_id", "ref_reward_accrual_id",
        "ref_merchant_settlement_id", "ref_payment_refund_id", "event_key",
    ],
    "payment_orders": [
        "provider_checkout_url", "checkout_started_at", "created_platform",
        "last_modified_platform", "client_request_id", "create_request_hash",
        "last_reconciled_at", "reconcile_attempts",
    ],
    "withdrawal_orders": [
        "created_platform", "last_modified_platform", "payout_actor_id",
    ],
    "invite_records": [
        "created_platform", "last_modified_platform", "qualification_status",
        "qualification_policy_version", "identity_verified_at", "qualified_at",
        "qualification_day", "daily_slot", "qualification_order_id",
        "qualification_reason", "fixed_reward_accrual_id",
    ],
    "external_auth_flows": ["user_id", "inviter_id", "platform", "client_id", "terms_accepted"],
    "external_auth_tickets": ["platform", "client_id"],
    "compute_onboardings": [
        "review_note", "reviewed_by", "reviewed_at", "updated_at",
        "created_platform", "last_modified_platform", "version",
    ],
    "coupons": [
        "campaign_id", "product_id", "redeemed_at", "used_at", "used_order_id",
        "created_platform", "last_modified_platform", "version",
    ],
    "coupon_campaigns": ["last_modified_by"],
}

_DATETIME_COLS = {
    "deleted_at",
    "end_at", "start_at", "price_updated_at", "source_published_at",
    "rights_checked_at", "ingested_at", "reviewed_at", "updated_at",
    "ocr_updated_at", "moderated_at",
    "consent_at",
    "checkout_started_at",
    "last_reconciled_at",
    "delivery_due_at", "delivered_at", "confirmation_due_at", "confirmed_at",
    "canceled_at", "stock_released_at", "disputed_at", "dispute_due_at", "dispute_resolved_at",
    "identity_verified_at", "qualified_at",
    "recovery_email_verified_at",
    "expires_at", "revoked_at",
    "redeemed_at", "used_at",
}
_DATE_COLS = {"qualification_day"}
_INTEGER_COLS = {
    "quantity", "purchase_hours", "video_duration", "stock", "supplier_id",
    "ref_payment_order_id", "ref_order_renewal_id", "ref_reward_accrual_id",
    "ref_merchant_settlement_id", "ref_payment_refund_id", "reviewed_by", "payout_actor_id",
    "dispute_resolved_by", "user_id", "inviter_id",
    "source_max_configurable_quantity", "platform_stock_cap",
    "daily_slot", "qualification_order_id", "fixed_reward_accrual_id",
    "auth_version", "moderated_by", "reconcile_attempts", "revoked_by_user_id",
    "coupon_id", "campaign_id", "product_id", "used_order_id", "last_modified_by", "version",
}
_NUMERIC_COLS = {
    "sell_price", "source_price", "exchange_rate", "reliability",
    "withdrawable_balance", "withdraw_frozen", "promotional_balance",
    "promotional_frozen",
    "coupon_discount",
}
_BOOLEAN_COLS = {"phone_bound", "password_set", "terms_accepted"}
_JSON_COLS = {"product_snapshot"}

def _ensure_columns(db_engine=None):
    target_engine = db_engine or engine
    insp = inspect(target_engine)
    for table, cols in _ENSURE.items():
        if table not in insp.get_table_names():
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col not in existing:
                if col == "account_status":
                    col_type = "VARCHAR(16) NOT NULL DEFAULT 'active'"
                elif col == "moderation_status":
                    col_type = "VARCHAR(24) NOT NULL DEFAULT 'visible'"
                elif col == "auth_version":
                    col_type = "INTEGER NOT NULL DEFAULT 0"
                elif col == "password_set":
                    col_type = "BOOLEAN NOT NULL DEFAULT TRUE"
                elif col == "reconcile_attempts":
                    col_type = "INTEGER NOT NULL DEFAULT 0"
                elif table == "products" and col == "version":
                    col_type = "INTEGER NOT NULL DEFAULT 1"
                elif table == "compute_onboardings" and col == "version":
                    col_type = "INTEGER NOT NULL DEFAULT 1"
                elif table == "coupons" and col == "version":
                    col_type = "INTEGER NOT NULL DEFAULT 1"
                elif table == "orders" and col == "coupon_discount":
                    col_type = "NUMERIC NOT NULL DEFAULT 0"
                elif col in {
                    "client_request_id", "create_request_hash", "consent_version",
                }:
                    col_type = "VARCHAR(64)"
                elif col in _DATETIME_COLS:
                    col_type = (
                        "TIMESTAMP WITHOUT TIME ZONE"
                        if target_engine.dialect.name == "postgresql"
                        else "DATETIME"
                    )
                elif col in _DATE_COLS:
                    col_type = "DATE"
                elif col in _INTEGER_COLS:
                    col_type = "INTEGER"
                elif col in _NUMERIC_COLS:
                    col_type = "NUMERIC"
                elif col in _BOOLEAN_COLS:
                    col_type = "BOOLEAN DEFAULT FALSE"
                elif col in _JSON_COLS:
                    col_type = "JSON"
                else:
                    col_type = "TEXT"
                with target_engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                print(f"[init_db] 补列: {table}.{col}")
    if "orders" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text("UPDATE orders SET quantity = 1 WHERE quantity IS NULL OR quantity < 1"))
            conn.execute(text(
                "UPDATE orders SET created_platform = 'legacy' "
                "WHERE created_platform IS NULL OR TRIM(created_platform) = ''"
            ))
            conn.execute(text(
                "UPDATE orders SET last_modified_platform = 'legacy' "
                "WHERE last_modified_platform IS NULL OR TRIM(last_modified_platform) = ''"
            ))
            conn.execute(text(
                "UPDATE orders SET coupon_discount = 0 WHERE coupon_discount IS NULL"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_orders_coupon_id ON orders (coupon_id)"
            ))
    if "users" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text("UPDATE users SET auth_version = 0 WHERE auth_version IS NULL"))
            conn.execute(text("UPDATE users SET password_set = TRUE WHERE password_set IS NULL"))
    if "payment_orders" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text(
                "UPDATE payment_orders SET reconcile_attempts = 0 "
                "WHERE reconcile_attempts IS NULL"
            ))
    if "compute_onboardings" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text(
                "UPDATE compute_onboardings SET version = 1 "
                "WHERE version IS NULL OR version < 1"
            ))
            conn.execute(text(
                "UPDATE compute_onboardings SET created_platform = 'legacy' "
                "WHERE created_platform IS NULL OR TRIM(created_platform) = ''"
            ))
            conn.execute(text(
                "UPDATE compute_onboardings SET last_modified_platform = created_platform "
                "WHERE last_modified_platform IS NULL OR TRIM(last_modified_platform) = ''"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_compute_onboardings_status "
                "ON compute_onboardings (status)"
            ))
    if "coupons" in insp.get_table_names():
        with target_engine.begin() as conn:
            if target_engine.dialect.name == "postgresql":
                conn.execute(text(
                    "ALTER TABLE coupons ALTER COLUMN amount TYPE NUMERIC(18, 6) "
                    "USING amount::numeric"
                ))
                conn.execute(text(
                    "ALTER TABLE coupons ALTER COLUMN min_amount TYPE NUMERIC(18, 6) "
                    "USING min_amount::numeric"
                ))
            conn.execute(text(
                "UPDATE coupons SET version = 1 WHERE version IS NULL OR version < 1"
            ))
            conn.execute(text(
                "UPDATE coupons SET created_platform = 'legacy' "
                "WHERE created_platform IS NULL OR TRIM(created_platform) = ''"
            ))
            conn.execute(text(
                "UPDATE coupons SET last_modified_platform = created_platform "
                "WHERE last_modified_platform IS NULL OR TRIM(last_modified_platform) = ''"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_coupons_user_campaign "
                "ON coupons (user_id, campaign_id) WHERE campaign_id IS NOT NULL"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_coupons_status ON coupons (status)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_coupons_used_order_id ON coupons (used_order_id)"
            ))
    if "coupon_campaigns" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text(
                "UPDATE coupon_campaigns SET last_modified_by = created_by "
                "WHERE last_modified_by IS NULL"
            ))
    for table in ("posts", "comments"):
        if table in insp.get_table_names():
            with target_engine.begin() as conn:
                conn.execute(text(
                    f"UPDATE {table} SET moderation_status = 'visible' "
                    "WHERE moderation_status IS NULL OR TRIM(moderation_status) = ''"
                ))
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_moderation_status "
                    f"ON {table} (moderation_status)"
                ))
    if "order_renewals" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text(
                "UPDATE order_renewals SET created_platform = 'legacy' "
                "WHERE created_platform IS NULL OR TRIM(created_platform) = ''"
            ))
    if "verifications" in insp.get_table_names():
        with target_engine.begin() as conn:
            conn.execute(text(
                "UPDATE verifications SET ocr_status = 'not_started' "
                "WHERE ocr_status IS NULL OR ocr_status = ''"
            ))
    attribution_columns = {
        "users": ("created_platform",),
        "payment_orders": ("created_platform", "last_modified_platform"),
        "verifications": ("created_platform", "last_modified_platform"),
        "bank_cards": ("created_platform", "last_modified_platform"),
        "withdrawal_orders": ("created_platform", "last_modified_platform"),
        "posts": ("created_platform", "last_modified_platform"),
        "comments": ("created_platform",),
        "likes": ("created_platform",),
        "follows": ("created_platform",),
        "community_blocks": ("created_platform",),
        "community_reports": ("created_platform",),
        "invite_records": ("created_platform", "last_modified_platform"),
        "compute_onboardings": ("created_platform", "last_modified_platform"),
    }
    table_names = set(insp.get_table_names())
    for table, columns in attribution_columns.items():
        if table not in table_names:
            continue
        with target_engine.begin() as conn:
            for column in columns:
                conn.execute(text(
                    f"UPDATE {table} SET {column} = 'legacy' "
                    f"WHERE {column} IS NULL OR TRIM({column}) = ''"
                ))
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_created_platform "
                f"ON {table} (created_platform)"
            ))


def _migrate_market_candle_resolutions(db_engine=None) -> int:
    """Copy legacy daily candles into the additive resolution-aware table.

    The legacy table and its restrictive UNIQUE constraint are intentionally
    left untouched. This makes the migration reversible and avoids an in-place
    SQLite table rebuild while the new table can safely store 1h/4h/1d rows
    sharing the same start timestamp.
    """

    target_engine = db_engine or engine
    MarketPriceCandle.__table__.create(bind=target_engine, checkfirst=True)
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    legacy_table = "market_price_candles"
    target_table = MarketPriceCandle.__tablename__
    if legacy_table not in tables or target_table not in tables:
        return 0

    legacy_columns = {
        item["name"] for item in inspector.get_columns(legacy_table)
    }
    copied_columns = [
        column for column in MarketPriceCandle.__table__.columns
        if column.name not in {"id", "interval_seconds"}
        and column.name in legacy_columns
    ]
    missing_required = [
        column.name for column in MarketPriceCandle.__table__.columns
        if column.name not in {"id", "interval_seconds"}
        and column.name not in legacy_columns
        and not column.nullable
        and column.server_default is None
    ]
    if missing_required:
        raise RuntimeError(
            "legacy market_price_candles is missing required columns: "
            + ", ".join(sorted(missing_required))
        )

    interval_from_duration: str
    if target_engine.dialect.name == "sqlite":
        interval_from_duration = (
            "CASE WHEN end_time IS NOT NULL AND start_time IS NOT NULL "
            "AND julianday(end_time) > julianday(start_time) "
            "THEN MAX(CAST(ROUND((julianday(end_time) - julianday(start_time)) * 86400) AS INTEGER), 1) "
            "ELSE 86400 END"
        )
    elif target_engine.dialect.name == "postgresql":
        interval_from_duration = (
            "CASE WHEN end_time IS NOT NULL AND start_time IS NOT NULL AND end_time > start_time "
            "THEN GREATEST(ROUND(EXTRACT(EPOCH FROM (end_time - start_time)))::INTEGER, 1) "
            "ELSE 86400 END"
        )
    else:
        raise RuntimeError(
            "market candle resolution migration supports only SQLite and PostgreSQL"
        )
    interval_expression = interval_from_duration
    if "interval_seconds" in legacy_columns:
        interval_expression = (
            "CASE WHEN CAST(interval_seconds AS INTEGER) > 0 "
            f"THEN CAST(interval_seconds AS INTEGER) ELSE {interval_from_duration} END"
        )

    insert_names = [column.name for column in copied_columns] + ["interval_seconds"]
    quoted_insert_names = ", ".join(f'"{name}"' for name in insert_names)
    qualified_interval_expression = interval_expression
    for column_name in ("interval_seconds", "end_time", "start_time"):
        qualified_interval_expression = qualified_interval_expression.replace(
            column_name, f'legacy."{column_name}"',
        )
    select_values = ", ".join(
        [f'legacy."{column.name}"' for column in copied_columns]
        + [qualified_interval_expression]
    )
    identity = (
        "source, gpu_model, gpu_variant, billing_mode, interval_seconds, start_time"
    )
    if target_engine.dialect.name == "sqlite":
        statement = (
            f'INSERT OR IGNORE INTO "{target_table}" ({quoted_insert_names}) '
            f'SELECT {select_values} FROM "{legacy_table}" AS legacy'
        )
    else:
        statement = (
            f'INSERT INTO "{target_table}" ({quoted_insert_names}) '
            f'SELECT {select_values} FROM "{legacy_table}" AS legacy '
            f"ON CONFLICT ({identity}) DO NOTHING"
        )
    with target_engine.begin() as conn:
        result = conn.execute(text(statement))
        missing = conn.execute(text(
            f'SELECT COUNT(*) FROM "{legacy_table}" AS legacy '
            f'WHERE NOT EXISTS (SELECT 1 FROM "{target_table}" AS current '
            'WHERE current.source = legacy.source '
            'AND current.gpu_model = legacy.gpu_model '
            'AND current.gpu_variant = legacy.gpu_variant '
            'AND current.billing_mode = legacy.billing_mode '
            f'AND current.interval_seconds = {qualified_interval_expression} '
            'AND current.start_time = legacy.start_time)'
        )).scalar_one()
        if int(missing or 0):
            raise RuntimeError(
                f"market candle resolution migration left {int(missing)} legacy rows uncopied"
            )
    copied = max(int(result.rowcount or 0), 0)
    if copied:
        print(f"[init_db] 行情K线分辨率迁移: 安全复制 {copied} 条，旧表保留")
    return copied


def _migrate_product_market_sources(db_engine=None):
    """Persist provider identity and retire non-KAI product cards safely.

    Historical products and snapshots stay in place for order/audit lookup;
    only their sale status is disabled.  This migration is deliberately
    idempotent and refuses to guess between duplicate upstream identities.
    """

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    if "products" not in tables:
        return
    product_columns = {item["name"] for item in inspector.get_columns("products")}
    with target_engine.begin() as conn:
        conn.execute(text(
            "UPDATE products SET market_source = CASE "
            "WHEN source_price IS NULL THEN 'wod' "
            "WHEN UPPER(COALESCE(source_currency, '')) = 'USD' THEN 'vast' "
            "ELSE 'autodl' END, version = version + 1 "
            "WHERE market_source IS NULL OR TRIM(market_source) = ''"
        ))
        conn.execute(text(
            "UPDATE products SET stock_semantics = CASE "
            "WHEN market_source = 'kai' THEN 'platform_closed_test_manual_fulfillment_allocation' "
            "WHEN market_source IN ('autodl', 'vast') THEN 'reported_available_units' "
            "ELSE 'supplier_reported_inventory' END, version = version + 1 "
            "WHERE stock_semantics IS NULL OR TRIM(stock_semantics) = ''"
        ))
        initial_kai_cap = max(int(settings.KAI_CLOSED_TEST_INITIAL_STOCK), 0)
        conn.execute(text(
            "UPDATE products SET source_max_configurable_quantity = "
            "CASE WHEN stock > 0 THEN stock ELSE 0 END, version = version + 1 "
            "WHERE market_source = 'kai' AND source_max_configurable_quantity IS NULL"
        ))
        conn.execute(text(
            "UPDATE products SET platform_stock_cap = "
            "CASE WHEN source_max_configurable_quantity < :initial_cap "
            "THEN source_max_configurable_quantity ELSE :initial_cap END, "
            "version = version + 1 "
            "WHERE market_source = 'kai' AND platform_stock_cap IS NULL"
        ), {"initial_cap": initial_kai_cap})
        conn.execute(text(
            "UPDATE products SET stock = CASE "
            "WHEN stock < 0 THEN 0 "
            "WHEN platform_stock_cap IS NOT NULL AND stock > platform_stock_cap "
            "THEN platform_stock_cap ELSE stock END, "
            "stock_semantics = 'platform_closed_test_manual_fulfillment_allocation', "
            "version = version + 1 "
            "WHERE market_source = 'kai' AND ("
            "stock < 0 OR (platform_stock_cap IS NOT NULL AND stock > platform_stock_cap) OR "
            "stock_semantics IS NULL OR "
            "stock_semantics <> 'platform_closed_test_manual_fulfillment_allocation')"
        ))
        if "cycle" in product_columns:
            conn.execute(text(
                "UPDATE products SET cycle = '[]', version = version + 1 "
                "WHERE market_source = 'kai' AND (cycle IS NULL OR CAST(cycle AS TEXT) <> '[]')"
            ))
        conn.execute(text(
            "UPDATE products SET status = 'off', stock = 0, version = version + 1 "
            "WHERE market_source IN ('autodl', 'vast') AND ("
            "status IS NULL OR status <> 'off' OR stock IS NULL OR stock <> 0)"
        ))
        if "market_source_status" in tables:
            conn.execute(text(
                "UPDATE market_source_status SET enabled = FALSE, status = 'disabled' "
                "WHERE source <> 'kai'"
            ))
        if "market_history_source_status" in tables:
            conn.execute(text(
                "UPDATE market_history_source_status SET enabled = FALSE, status = 'disabled' "
                "WHERE enabled = TRUE"
            ))
        duplicate_identity = conn.execute(text(
            "SELECT 1 FROM products "
            "WHERE external_product_id IS NOT NULL "
            "GROUP BY market_source, external_product_id HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicate_identity:
            raise RuntimeError(
                "duplicate product market identities detected; resolve before startup"
            )
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_products_market_external "
            "ON products (market_source, external_product_id) "
            "WHERE external_product_id IS NOT NULL"
        ))


def _migrate_product_create_idempotency(db_engine=None) -> None:
    """Add durable per-supplier idempotency for manually listed products."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    if "products" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("products")}
    missing_columns = {
        "client_request_id": "VARCHAR(64)",
        "create_request_hash": "VARCHAR(64)",
    }
    for column, column_type in missing_columns.items():
        if column in columns:
            continue
        with target_engine.begin() as conn:
            conn.execute(text(
                f"ALTER TABLE products ADD COLUMN {column} {column_type}"
            ))
        print(f"[init_db] 补列: products.{column}")

    with target_engine.connect() as conn:
        duplicate = conn.execute(text(
            "SELECT supplier_id, client_request_id FROM products "
            "WHERE supplier_id IS NOT NULL AND client_request_id IS NOT NULL "
            "GROUP BY supplier_id, client_request_id HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
    if duplicate:
        raise RuntimeError(
            "duplicate per-supplier product request ids detected; resolve before startup"
        )

    inspector = inspect(target_engine)
    indexes = inspector.get_indexes("products")
    constraints = inspector.get_unique_constraints("products")
    expected_columns = ["supplier_id", "client_request_id"]
    has_scoped_unique = any(
        item.get("unique") and item.get("column_names") == expected_columns
        for item in indexes
    ) or any(
        item.get("column_names") == expected_columns
        for item in constraints
    )
    if has_scoped_unique:
        return

    index_name = "uq_products_supplier_client_request"
    if any(item.get("name") == index_name for item in indexes + constraints):
        raise RuntimeError(f"{index_name} exists with an incompatible definition")
    with target_engine.begin() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_products_supplier_client_request "
            "ON products (supplier_id, client_request_id) "
            "WHERE client_request_id IS NOT NULL"
        ))


def _reconcile_supplier_completed_order_counts(db_engine=None):
    """Backfill the public merchant completed-sale count from settlement facts."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    if not {"suppliers", "merchant_settlements"}.issubset(tables):
        return
    supplier_columns = {item["name"] for item in inspector.get_columns("suppliers")}
    if "order_count" not in supplier_columns:
        return
    with target_engine.begin() as conn:
        conn.execute(text(
            "UPDATE suppliers SET order_count = ("
            "SELECT COUNT(*) FROM merchant_settlements "
            "WHERE merchant_settlements.supplier_id = suppliers.id "
            "AND merchant_settlements.source_type = 'order' "
            "AND merchant_settlements.status = 'settled'"
            ")"
        ))


def _migrate_buy_request_idempotency(db_engine=None) -> None:
    """Add durable per-user request idempotency without rewriting legacy rows."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    if "buy_requests" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("buy_requests")}
    if "client_request_id" not in columns:
        with target_engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE buy_requests ADD COLUMN client_request_id VARCHAR(64)"
            ))
        print("[init_db] 补列: buy_requests.client_request_id")

    with target_engine.connect() as conn:
        duplicate = conn.execute(text(
            "SELECT user_id, client_request_id FROM buy_requests "
            "WHERE client_request_id IS NOT NULL "
            "GROUP BY user_id, client_request_id HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
    if duplicate:
        raise RuntimeError(
            "duplicate per-user buy request ids detected; resolve before startup"
        )

    inspector = inspect(target_engine)
    indexes = inspector.get_indexes("buy_requests")
    constraints = inspector.get_unique_constraints("buy_requests")
    expected_columns = ["user_id", "client_request_id"]
    has_scoped_unique = any(
        item.get("unique") and item.get("column_names") == expected_columns
        for item in indexes
    ) or any(
        item.get("column_names") == expected_columns
        for item in constraints
    )
    if has_scoped_unique:
        return

    index_name = "uq_buy_requests_user_client_request"
    name_collision = any(
        item.get("name") == index_name
        for item in indexes + constraints
    )
    if name_collision:
        raise RuntimeError(
            f"{index_name} exists with an incompatible definition"
        )
    with target_engine.begin() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_buy_requests_user_client_request "
            "ON buy_requests (user_id, client_request_id) "
            "WHERE client_request_id IS NOT NULL"
        ))


def _migrate_community_like_idempotency(db_engine=None) -> dict[str, int | bool]:
    """Deduplicate likes, repair cached counts, and enforce one like per user."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    if not {"likes", "posts"}.issubset(tables):
        return {"duplicates_removed": 0, "index_created": False}

    indexes = inspector.get_indexes("likes")
    constraints = inspector.get_unique_constraints("likes")
    expected_columns = ["post_id", "user_id"]
    has_scoped_unique = any(
        item.get("unique")
        and list(item.get("column_names") or []) == expected_columns
        for item in indexes
    ) or any(
        list(item.get("column_names") or []) == expected_columns
        for item in constraints
    )
    index_name = "uq_likes_post_user"
    if not has_scoped_unique and any(
        item.get("name") == index_name for item in indexes + constraints
    ):
        raise RuntimeError(f"{index_name} exists with an incompatible definition")

    with target_engine.begin() as conn:
        removed = conn.execute(text(
            "DELETE FROM likes WHERE id NOT IN ("
            "SELECT keep_id FROM ("
            "SELECT MIN(id) AS keep_id FROM likes GROUP BY post_id, user_id"
            ") AS retained_likes)"
        )).rowcount or 0
        conn.execute(text(
            "UPDATE posts SET likes = ("
            "SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id"
            ")"
        ))
        if not has_scoped_unique:
            conn.execute(text(
                "CREATE UNIQUE INDEX uq_likes_post_user "
                "ON likes (post_id, user_id)"
            ))

    if removed:
        print(f"[init_db] 社区点赞去重: 删除 {removed} 条重复记录")
    return {
        "duplicates_removed": max(0, int(removed)),
        "index_created": not has_scoped_unique,
    }


def _migrate_community_comment_idempotency(db_engine=None) -> dict[str, int | bool]:
    """Deduplicate keyed comments, repair cached counts, and scope keys per user."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    if not {"comments", "posts"}.issubset(tables):
        return {
            "duplicates_removed": 0,
            "counts_repaired": 0,
            "index_created": False,
        }

    columns = {item["name"] for item in inspector.get_columns("comments")}
    if "client_request_id" not in columns:
        with target_engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE comments ADD COLUMN client_request_id VARCHAR(64)"
            ))
        print("[init_db] 补列: comments.client_request_id")

    # Normal startup calls ``_ensure_columns`` first, so moderation_status is
    # present and legacy rows have already been backfilled to ``visible``. Keep
    # the standalone migration compatible with older test/repair databases
    # that predate moderation while never counting hidden rows when the status
    # column exists.
    visible_comment_filter = (
        " AND stored_comments.moderation_status = 'visible'"
        if "moderation_status" in columns else ""
    )

    inspector = inspect(target_engine)
    indexes = inspector.get_indexes("comments")
    constraints = inspector.get_unique_constraints("comments")
    expected_columns = ["user_id", "client_request_id"]
    has_scoped_unique = any(
        item.get("unique")
        and list(item.get("column_names") or []) == expected_columns
        for item in indexes
    ) or any(
        list(item.get("column_names") or []) == expected_columns
        for item in constraints
    )
    index_name = "uq_comments_user_client_request"
    if not has_scoped_unique and any(
        item.get("name") == index_name for item in indexes + constraints
    ):
        raise RuntimeError(f"{index_name} exists with an incompatible definition")

    with target_engine.begin() as conn:
        conn.execute(text(
            "UPDATE comments SET client_request_id = NULL "
            "WHERE client_request_id IS NOT NULL AND TRIM(client_request_id) = ''"
        ))
        conflicting_intent = conn.execute(text(
            "SELECT first.user_id, first.client_request_id "
            "FROM comments AS first JOIN comments AS other "
            "ON first.user_id = other.user_id "
            "AND first.client_request_id = other.client_request_id "
            "AND first.id < other.id "
            "WHERE first.client_request_id IS NOT NULL "
            "AND (first.post_id != other.post_id OR first.content != other.content) "
            "LIMIT 1"
        )).first()
        if conflicting_intent:
            raise RuntimeError(
                "conflicting per-user community comment request ids detected; "
                "resolve before startup"
            )
        removed = conn.execute(text(
            "DELETE FROM comments WHERE client_request_id IS NOT NULL AND id NOT IN ("
            "SELECT keep_id FROM ("
            "SELECT MIN(id) AS keep_id FROM comments "
            "WHERE client_request_id IS NOT NULL "
            "GROUP BY user_id, client_request_id"
            ") AS retained_comments)"
        )).rowcount or 0
        repaired = conn.execute(text(
            "UPDATE posts SET comments = ("
            "SELECT COUNT(*) FROM comments AS stored_comments "
            "WHERE stored_comments.post_id = posts.id"
            f"{visible_comment_filter}"
            ") WHERE COALESCE(posts.comments, -1) != ("
            "SELECT COUNT(*) FROM comments AS stored_comments "
            "WHERE stored_comments.post_id = posts.id"
            f"{visible_comment_filter}"
            ")"
        )).rowcount or 0
        if not has_scoped_unique:
            conn.execute(text(
                "CREATE UNIQUE INDEX uq_comments_user_client_request "
                "ON comments (user_id, client_request_id) "
                "WHERE client_request_id IS NOT NULL"
            ))

    if removed:
        print(f"[init_db] 社区评论去重: 删除 {removed} 条重复记录")
    if repaired:
        print(f"[init_db] 社区评论计数修复: 更新 {repaired} 条动态")
    return {
        "duplicates_removed": max(0, int(removed)),
        "counts_repaired": max(0, int(repaired)),
        "index_created": not has_scoped_unique,
    }


def _migrate_community_follow_idempotency(db_engine=None) -> dict[str, int | bool]:
    """Deduplicate follows and enforce one relationship per user pair."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    if "follows" not in set(inspector.get_table_names()):
        return {"duplicates_removed": 0, "index_created": False}

    indexes = inspector.get_indexes("follows")
    constraints = inspector.get_unique_constraints("follows")
    expected_columns = ["follower_id", "following_id"]
    has_scoped_unique = any(
        item.get("unique")
        and list(item.get("column_names") or []) == expected_columns
        for item in indexes
    ) or any(
        list(item.get("column_names") or []) == expected_columns
        for item in constraints
    )
    index_name = "uq_follows_follower_following"
    if not has_scoped_unique and any(
        item.get("name") == index_name for item in indexes + constraints
    ):
        raise RuntimeError(f"{index_name} exists with an incompatible definition")

    with target_engine.begin() as conn:
        removed = conn.execute(text(
            "DELETE FROM follows WHERE id NOT IN ("
            "SELECT keep_id FROM ("
            "SELECT MIN(id) AS keep_id FROM follows GROUP BY follower_id, following_id"
            ") AS retained_follows)"
        )).rowcount or 0
        if not has_scoped_unique:
            conn.execute(text(
                "CREATE UNIQUE INDEX uq_follows_follower_following "
                "ON follows (follower_id, following_id)"
            ))

    if removed:
        print(f"[init_db] 社区关注去重: 删除 {removed} 条重复记录")
    return {
        "duplicates_removed": max(0, int(removed)),
        "index_created": not has_scoped_unique,
    }


def _sqlite_rebuild_orders_without_global_request_unique(target_engine) -> None:
    """Remove the legacy SQLite UNIQUE(client_request_id) constraint."""

    raw = target_engine.raw_connection()
    cursor = raw.cursor()
    try:
        schema_row = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'orders'"
        ).fetchone()
        if not schema_row or not schema_row[0]:
            return
        schema = schema_row[0]
        index_rows = cursor.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'orders' AND sql IS NOT NULL"
        ).fetchall()
        rebuilt = re.sub(
            r",\s*(?:CONSTRAINT\s+[^\s]+\s+)?UNIQUE\s*\(\s*[\"`\[]?client_request_id[\"`\]]?\s*\)",
            "",
            schema,
            flags=re.IGNORECASE,
        )
        rebuilt = re.sub(
            r"(\bclient_request_id\b\s+[^,\n]+?)\s+UNIQUE\b",
            r"\1",
            rebuilt,
            flags=re.IGNORECASE,
        )
        if rebuilt == schema:
            raise RuntimeError("unable to remove legacy global order request uniqueness")
        for original in ('CREATE TABLE "orders"', "CREATE TABLE orders", "CREATE TABLE `orders`"):
            if original in rebuilt:
                rebuilt = rebuilt.replace(
                    original,
                    'CREATE TABLE "orders__request_scope_migration"',
                    1,
                )
                break
        else:
            raise RuntimeError("unable to prepare SQLite orders request-scope migration")
        columns = [row[1] for row in cursor.execute("PRAGMA table_info('orders')").fetchall()]
        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("DROP TABLE IF EXISTS orders__request_scope_migration")
        cursor.execute(rebuilt)
        cursor.execute(
            f'INSERT INTO "orders__request_scope_migration" ({quoted_columns}) '
            f'SELECT {quoted_columns} FROM "orders"'
        )
        cursor.execute('DROP TABLE "orders"')
        cursor.execute('ALTER TABLE "orders__request_scope_migration" RENAME TO "orders"')
        for _name, sql in index_rows:
            if not sql:
                continue
            normalized = re.sub(r"[\s\"`\[\]]+", "", sql).lower()
            if "uniqueindex" in normalized and "(client_request_id)" in normalized:
                continue
            cursor.execute(sql)
        violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("foreign-key violation after order request-scope migration")
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        raw.rollback()
        raise
    finally:
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
            raw.close()


def _migrate_order_request_scope(db_engine=None) -> None:
    """Replace global order idempotency with per-user idempotency."""

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    if "orders" not in inspector.get_table_names():
        return
    with target_engine.connect() as conn:
        duplicate = conn.execute(text(
            "SELECT user_id, client_request_id FROM orders "
            "WHERE client_request_id IS NOT NULL "
            "GROUP BY user_id, client_request_id HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
    if duplicate:
        raise RuntimeError("duplicate per-user order request ids detected; resolve before startup")

    exact = ["client_request_id"]
    global_indexes = [
        item for item in inspector.get_indexes("orders")
        if item.get("unique") and item.get("column_names") == exact
    ]
    global_constraints = [
        item for item in inspector.get_unique_constraints("orders")
        if item.get("column_names") == exact
    ]
    if target_engine.dialect.name == "sqlite" and global_constraints:
        _sqlite_rebuild_orders_without_global_request_unique(target_engine)
    else:
        preparer = target_engine.dialect.identifier_preparer
        with target_engine.begin() as conn:
            constraint_names = {
                item.get("name") for item in global_constraints if item.get("name")
            }
            if target_engine.dialect.name == "postgresql":
                for item in global_constraints:
                    name = item.get("name")
                    if name:
                        conn.execute(text(
                            f"ALTER TABLE orders DROP CONSTRAINT IF EXISTS {preparer.quote(name)}"
                        ))
            for item in global_indexes:
                name = item.get("name")
                if name and name not in constraint_names:
                    conn.execute(text(f"DROP INDEX IF EXISTS {preparer.quote(name)}"))

    inspector = inspect(target_engine)
    has_scoped = any(
        item.get("unique")
        and item.get("column_names") == ["user_id", "client_request_id"]
        for item in inspector.get_indexes("orders")
        + inspector.get_unique_constraints("orders")
    )
    with target_engine.begin() as conn:
        if not has_scoped:
            conn.execute(text(
                "CREATE UNIQUE INDEX uq_orders_user_client_request "
                "ON orders (user_id, client_request_id) "
                "WHERE client_request_id IS NOT NULL"
            ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_orders_client_request_id "
            "ON orders (client_request_id)"
        ))


def _migrate_unverified_phone_flags(db_engine=None):
    """One-time truth migration for numbers never verified by an SMS flow.

    ZTW has not had a real phone-ownership verification service. Historical
    ``phone_bound=true`` values therefore came only from an unsafe default.
    A durable marker makes this demotion idempotent and prevents a future,
    genuinely verified flag from being reset on every startup.
    """
    target_engine = db_engine or engine
    marker = "20260817_phone_binding_requires_verification"
    with target_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS app_migrations ("
            "name VARCHAR(128) PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))
        already_applied = conn.execute(
            text("SELECT name FROM app_migrations WHERE name = :name"),
            {"name": marker},
        ).first()
        if already_applied:
            return False
        conn.execute(text("UPDATE users SET phone_bound = FALSE"))
        conn.execute(
            text("INSERT INTO app_migrations (name) VALUES (:name)"),
            {"name": marker},
        )
    print("[init_db] 已将无短信验证证据的历史手机号标记为未绑定")
    return True


def _normalize_kai_identity_issuers(db_engine=None):
    """Rewrite the historical endpoint-base issuer to KAI's canonical issuer."""

    from app.services.kai_auth import identity_issuer_urls, issuer_url

    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    if "external_identities" not in inspector.get_table_names():
        return False
    canonical = issuer_url()
    legacy_values = [
        value for value in identity_issuer_urls()
        if value and value != canonical
    ]
    if not canonical or not legacy_values:
        return False
    parameters = {"canonical": canonical}
    legacy_conditions = []
    for index, value in enumerate(legacy_values):
        key = f"legacy_{index}"
        parameters[key] = value
        legacy_conditions.append(f"issuer = :{key}")
    legacy_where = " OR ".join(legacy_conditions)
    all_where = f"issuer = :canonical OR {legacy_where}"
    with target_engine.begin() as conn:
        conflict = conn.execute(text(
            "SELECT subject, COUNT(*) AS identity_count "
            "FROM external_identities "
            f"WHERE provider = 'kai' AND ({all_where}) "
            "GROUP BY subject HAVING COUNT(*) > 1 LIMIT 1"
        ), parameters).first()
        if conflict:
            raise RuntimeError(
                "Kai issuer migration conflict must be resolved before migration: "
                f"subject={conflict.subject}"
            )
        result = conn.execute(text(
            "UPDATE external_identities SET issuer = :canonical "
            f"WHERE provider = 'kai' AND ({legacy_where})"
        ), parameters)
    changed = bool(result.rowcount)
    if changed:
        print("[init_db] 已将历史 Kai 身份签发方归一为 OIDC canonical issuer")
    return changed


def _ensure_auth_identity_constraints(db_engine=None):
    """Make both local-user and issuer-subject identity keys unique."""
    target_engine = db_engine or engine
    inspector = inspect(target_engine)
    if "external_identities" not in inspector.get_table_names():
        return False
    with target_engine.begin() as conn:
        duplicate_user = conn.execute(text(
            "SELECT user_id, provider, COUNT(*) AS identity_count "
            "FROM external_identities GROUP BY user_id, provider "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicate_user:
            raise RuntimeError(
                "external identity conflict must be resolved before migration: "
                f"user_id={duplicate_user.user_id}, provider={duplicate_user.provider}"
            )
        duplicate_subject = conn.execute(text(
            "SELECT issuer, subject, COUNT(*) AS identity_count "
            "FROM external_identities GROUP BY issuer, subject "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicate_subject:
            raise RuntimeError(
                "external identity subject conflict must be resolved before migration: "
                f"issuer={duplicate_subject.issuer}, subject={duplicate_subject.subject}"
            )

        refreshed = inspect(target_engine)
        indexes = refreshed.get_indexes("external_identities")
        constraints = refreshed.get_unique_constraints("external_identities")

        def has_unique(columns):
            expected = list(columns)
            return any(
                item.get("unique") and item.get("column_names") == expected
                for item in indexes
            ) or any(
                item.get("column_names") == expected
                for item in constraints
            )

        changed = False
        if not has_unique(("user_id", "provider")):
            conn.execute(text(
                "CREATE UNIQUE INDEX ix_external_identity_user_provider "
                "ON external_identities (user_id, provider)"
            ))
            changed = True
        if not has_unique(("issuer", "subject")):
            conn.execute(text(
                "CREATE UNIQUE INDEX ix_external_identity_issuer_subject_unique "
                "ON external_identities (issuer, subject)"
            ))
            changed = True
    if changed:
        print("[init_db] 已确保本地账号与 Kai 签发方主体标识均唯一")
    return changed


def _migrate_offline_purchases():
    """Keep legacy records visible in the new unified buy-request flow."""
    from datetime import timedelta

    from app.models.buy_request import BuyRequest
    from app.models.offline_purchase import OfflinePurchase

    status_map = {
        "submitted": "published",
        "contacted": "processing",
        "done": "completed",
        "rejected": "rejected",
    }
    db = SessionLocal()
    try:
        migrated = 0
        for legacy in db.query(OfflinePurchase).all():
            exists = db.query(BuyRequest).filter(
                BuyRequest.legacy_offline_purchase_id == legacy.id
            ).first()
            if exists:
                continue
            created_at = legacy.created_at
            db.add(BuyRequest(
                user_id=legacy.user_id,
                request_type="offline",
                gpu_model=legacy.device_model,
                quantity=legacy.quantity,
                budget=legacy.budget,
                currency="CNY",
                requirements={"legacy_remark": legacy.remark or ""},
                contact=legacy.contact,
                phone=legacy.phone,
                status=status_map.get(legacy.status, "published"),
                expires_at=created_at + timedelta(days=30) if created_at else None,
                legacy_offline_purchase_id=legacy.id,
                created_at=created_at,
                updated_at=created_at,
            ))
            migrated += 1
        db.commit()
        if migrated:
            print(f"[init_db] 迁移旧线下采购记录: {migrated} 条")
    finally:
        db.close()


def _migrate_legacy_market_history():
    """Reuse real AutoDL snapshots already collected by the previous synchronizer."""
    from collections import defaultdict
    from decimal import Decimal
    import hashlib

    from app.models.market_price import MarketPriceSnapshot
    from app.models.price_history import PriceHistory
    from app.models.product import Product
    from app.services.gpu_catalog import canonicalize_gpu, memory_variant_from_text

    db = SessionLocal()
    try:
        groups = defaultdict(list)
        rows = db.query(PriceHistory, Product).join(Product, Product.id == PriceHistory.product_id).filter(
            Product.source_price.isnot(None),
            Product.source_currency == "CNY",
        ).all()
        for history, product in rows:
            model = canonicalize_gpu(history.gpu_model) or canonicalize_gpu(product.name)
            if not model or not history.recorded_at or history.price <= 0:
                continue
            key = (history.recorded_at, model, memory_variant_from_text(product.memory))
            groups[key].append(Decimal(str(history.price)))
        migrated = 0
        for (observed_at, model, variant), prices in groups.items():
            if db.query(MarketPriceSnapshot).filter(
                MarketPriceSnapshot.source == "autodl",
                MarketPriceSnapshot.gpu_model == model,
                MarketPriceSnapshot.gpu_variant == variant,
                MarketPriceSnapshot.observed_at == observed_at,
            ).first():
                continue
            unique_prices = sorted(set(prices))
            middle = unique_prices[len(unique_prices) // 2]
            signature = hashlib.sha256(
                f"legacy|{observed_at.isoformat()}|{model}|{variant}|{middle}".encode("utf-8")
            ).hexdigest()
            db.add(MarketPriceSnapshot(
                source="autodl",
                gpu_model=model,
                gpu_variant=variant,
                billing_mode="ondemand",
                currency="CNY",
                min_price=min(unique_prices),
                p25_price=middle,
                median_price=middle,
                p75_price=middle,
                max_price=max(unique_prices),
                min_price_cny=min(unique_prices),
                median_price_cny=middle,
                max_price_cny=max(unique_prices),
                sample_count=len(unique_prices),
                available_gpu_count=0,
                fx_rate=Decimal("1"),
                fx_source="CNY native",
                fx_date=observed_at.date().isoformat(),
                data_quality="legacy_verified",
                signature=signature,
                observed_at=observed_at,
                fetched_at=observed_at,
            ))
            migrated += 1
        db.commit()
        if migrated:
            print(f"[init_db] 迁移历史真实行情: {migrated} 条")
    finally:
        db.close()


def _migrate_sensitive_fields(db_session=None):
    """Encrypt legacy plaintext values without changing their visible meaning."""
    # This helper is imported directly by tests and maintenance tooling, so it
    # must defend itself rather than relying only on init() or service startup.
    assert_sensitive_storage_secure()

    from app.core.sensitive import fingerprint, protect, reveal
    from app.models.account_recovery import AccountRecoveryToken
    from app.models.account_recovery_mail import AccountRecoveryMailOutbox
    from app.models.bank_card import BankCard
    from app.models.buy_request import BuyRequestCredential
    from app.models.order import Order
    from app.models.user import User
    from app.models.verification import Verification

    owns_session = db_session is None
    db = db_session or SessionLocal()
    try:
        migrated = 0

        def migrate_value(row, attribute: str) -> str | None:
            nonlocal migrated
            current = getattr(row, attribute)
            encrypted = protect(current)
            if encrypted != current:
                setattr(row, attribute, encrypted)
                migrated += 1
            return encrypted

        for row in db.query(Verification).all():
            migrate_value(row, "id_card")
            migrate_value(row, "ocr_summary")
        for row in db.query(BankCard).all():
            encrypted_number = migrate_value(row, "card_number")
            migrate_value(row, "phone")
            if row.card_fingerprint is not None and encrypted_number:
                normalized_number = "".join(reveal(encrypted_number).split())
                current_fingerprint = fingerprint(normalized_number)
                if row.card_fingerprint != current_fingerprint:
                    row.card_fingerprint = current_fingerprint
                    migrated += 1
        for row in db.query(Order).filter(Order.ssh_info.isnot(None)).all():
            migrate_value(row, "ssh_info")
        for row in db.query(User).filter(User.recovery_email.isnot(None)).all():
            encrypted_email = migrate_value(row, "recovery_email")
            if encrypted_email:
                current_fingerprint = fingerprint(reveal(encrypted_email))
                if row.recovery_email_fingerprint != current_fingerprint:
                    row.recovery_email_fingerprint = current_fingerprint
                    migrated += 1
        for row in db.query(AccountRecoveryToken).filter(
            AccountRecoveryToken.target_email.isnot(None)
        ).all():
            encrypted_email = migrate_value(row, "target_email")
            if encrypted_email:
                current_fingerprint = fingerprint(reveal(encrypted_email))
                if row.target_email_fingerprint != current_fingerprint:
                    row.target_email_fingerprint = current_fingerprint
                    migrated += 1
        for row in db.query(AccountRecoveryMailOutbox).all():
            migrate_value(row, "recipient_payload")
            migrate_value(row, "token_payload")
        for row in db.query(BuyRequestCredential).all():
            encrypted_payload = migrate_value(row, "protected_payload")
            if encrypted_payload:
                current_fingerprint = fingerprint(reveal(encrypted_payload))
                if row.payload_fingerprint != current_fingerprint:
                    row.payload_fingerprint = current_fingerprint
                    migrated += 1
        db.commit()
        if migrated:
            print(f"[init_db] 已加密历史敏感字段: {migrated} 条")
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _migrate_buy_request_quote_revisions(db_session=None):
    """Backfill one immutable revision for quotes created before negotiation V2."""
    from app.models.buy_request import BuyRequestQuote, BuyRequestQuoteRevision
    from app.models.supplier import Supplier

    owns_session = db_session is None
    db = db_session or SessionLocal()
    try:
        migrated = 0
        quotes = db.query(BuyRequestQuote).all()
        for quote in quotes:
            exists = db.query(BuyRequestQuoteRevision.id).filter(
                BuyRequestQuoteRevision.quote_id == quote.id,
            ).first()
            if exists:
                continue
            supplier = db.query(Supplier).filter(Supplier.id == quote.supplier_id).first()
            if not supplier:
                continue
            db.add(BuyRequestQuoteRevision(
                quote_id=quote.id,
                buy_request_id=quote.buy_request_id,
                supplier_id=quote.supplier_id,
                revision_number=1,
                proposer_role="supplier",
                proposer_user_id=supplier.user_id,
                unit_price=quote.unit_price,
                total_price=quote.total_price,
                currency=quote.currency,
                available_at=quote.available_at,
                message=quote.message,
                expires_at=quote.expires_at,
                status=quote.status,
            ))
            migrated += 1
        db.commit()
        if migrated:
            print(f"[init_db] 补齐求购报价历史: {migrated} 条")
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _ensure_user_wallets(db_session=None):
    """Give every existing account its required zero-value wallet.

    Older test databases may contain accounts created before wallet creation was
    made transactional.  Creating a missing wallet with zero balances restores
    API compatibility without inventing spendable credit.
    """
    from decimal import Decimal

    from app.models.user import User
    from app.models.wallet import Wallet

    owns_session = db_session is None
    db = db_session or SessionLocal()
    try:
        missing_user_ids = [
            user_id for (user_id,) in db.query(User.id).outerjoin(
                Wallet, Wallet.user_id == User.id
            ).filter(Wallet.id.is_(None)).all()
        ]
        for user_id in missing_user_ids:
            db.add(Wallet(
                user_id=user_id,
                balance=Decimal("0"),
                frozen=Decimal("0"),
                withdrawable_balance=Decimal("0"),
                withdraw_frozen=Decimal("0"),
                promotional_balance=Decimal("0"),
                promotional_frozen=Decimal("0"),
            ))
        db.commit()
        if missing_user_ids:
            print(f"[init_db] 补齐零余额钱包: {len(missing_user_ids)} 个")
        return len(missing_user_ids)
    finally:
        if owns_session:
            db.close()


def _migrate_payment_precision_and_pending_deadlines(
    db_engine=None,
    db_session=None,
):
    """Upgrade card-hour precision and normalize legacy payment state.

    SQLite applies Numeric scale in SQLAlchemy rather than storage, so the new
    model declaration is sufficient there. PostgreSQL requires an explicit,
    lossless type alteration. Historical MaPay credits made by the old code
    stored CNY in a CH wallet; they are corrected once and every later ledger
    balance_after receives the same conservation delta.
    """
    from datetime import timedelta
    from decimal import Decimal

    from app.models.ledger import Ledger
    from app.models.payment import PaymentOrder
    from app.models.wallet import Wallet
    from app.services.mapay import checkout_ttl_seconds, utc_now

    target_engine = db_engine or engine
    if target_engine.dialect.name == "postgresql":
        target_inspector = inspect(target_engine)
        precision_columns = (
            ("wallets", "balance"),
            ("wallets", "frozen"),
            ("wallets", "withdrawable_balance"),
            ("wallets", "withdraw_frozen"),
            ("wallets", "promotional_balance"),
            ("wallets", "promotional_frozen"),
            ("ledger", "amount"),
            ("ledger", "balance_after"),
        )
        current_scales = {
            (table, column["name"]): getattr(column["type"], "scale", None)
            for table, _ in precision_columns
            for column in target_inspector.get_columns(table)
        }
        with target_engine.begin() as conn:
            for table, column in precision_columns:
                if (current_scales.get((table, column)) or 0) >= 6:
                    continue
                conn.execute(text(
                    f"ALTER TABLE {table} ALTER COLUMN {column} "
                    f"TYPE NUMERIC(18, 6) USING {column}::numeric(18, 6)"
                ))

    owns_session = db_session is None
    db = db_session or Session(bind=target_engine)
    marker = "20260820_payment_card_hour_precision_v1"
    try:
        # Claim the migration by inserting its unique marker at the start of
        # the *same* transaction as the wallet/ledger repair. ON CONFLICT makes
        # concurrent startup workers serialize without both applying a delta;
        # any repair failure rolls the marker back with the money changes.
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS app_migrations ("
            "name VARCHAR(128) PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))
        claim = db.execute(
            text(
                "INSERT INTO app_migrations (name) VALUES (:name) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"name": marker},
        )
        owns_precision_migration = claim.rowcount == 1
        corrected = 0
        if owns_precision_migration:
            linked_credits = db.query(PaymentOrder, Ledger).join(
                Ledger,
                Ledger.ref_payment_order_id == PaymentOrder.id,
            ).filter(
                PaymentOrder.credited_at.isnot(None),
                Ledger.type == "recharge",
                Ledger.direction == "in",
            ).order_by(Ledger.id.asc()).all()
            for payment, credit_ledger in linked_credits:
                expected = Decimal(payment.card_hours).quantize(Decimal("0.000001"))
                recorded = Decimal(credit_ledger.amount).quantize(Decimal("0.000001"))
                delta = expected - recorded
                if delta == 0:
                    continue
                wallet_updated = db.query(Wallet).filter(
                    Wallet.id == credit_ledger.wallet_id,
                ).update({
                    Wallet.balance: Wallet.balance + delta,
                }, synchronize_session=False)
                if wallet_updated != 1:
                    continue
                db.query(Ledger).filter(
                    Ledger.user_id == credit_ledger.user_id,
                    Ledger.id >= credit_ledger.id,
                ).update({
                    Ledger.balance_after: Ledger.balance_after + delta,
                }, synchronize_session=False)
                amount_updated = db.query(Ledger).filter(
                    Ledger.id == credit_ledger.id,
                    Ledger.amount == recorded,
                ).update({Ledger.amount: expected}, synchronize_session=False)
                if amount_updated != 1:
                    raise RuntimeError("legacy payment credit changed during precision migration")
                corrected += 1
            db.commit()
            db.expire_all()
        else:
            # End the no-op claim transaction before normal deadline cleanup.
            db.commit()

        ttl_seconds = checkout_ttl_seconds()
        now = utc_now()
        normalized = 0
        expired = 0
        pending_orders = db.query(PaymentOrder).filter(
            PaymentOrder.status == "pending",
            PaymentOrder.credited_at.is_(None),
        ).all()
        for payment in pending_orders:
            if payment.created_at:
                expected_deadline = payment.created_at + timedelta(seconds=ttl_seconds)
                if (
                    payment.expires_at is None
                    or payment.expires_at > expected_deadline + timedelta(seconds=1)
                ):
                    payment.expires_at = expected_deadline
                    normalized += 1
            if payment.expires_at and payment.expires_at <= now:
                payment.status = "expired"
                payment.failure_reason = "支付时限已结束；如已付款请查询支付平台状态"
                expired += 1
        db.commit()
        if corrected or normalized or expired:
            print(
                "[init_db] 支付迁移: "
                f"历史卡时入账修正 {corrected} / 截止时间归一 {normalized} / 过期 {expired}"
            )
        return {
            "corrected_credits": corrected,
            "normalized_deadlines": normalized,
            "expired_orders": expired,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _migrate_manual_payout_fields(db_engine=None, db_session=None):
    """Initialize the manual-payout schema without inventing withdrawable funds."""
    # This migration reads encrypted bank-card data and can also be invoked on
    # its own. Refuse all writes before opening a transaction unless the
    # independent storage key is valid.
    assert_sensitive_storage_secure()

    from app.core.sensitive import fingerprint, reveal
    from app.models.bank_card import BankCard
    from app.models.withdrawal import PaymentInstructionGrant, WithdrawalOrder
    from app.utils.bank_util import luhn_check

    target_engine = db_engine or engine
    owns_session = db_session is None
    db = db_session or Session(bind=target_engine)
    try:
        # Historical/recharge/reward/revenue rows are deliberately ignored.
        # The only safe migration value is zero until a future auditable source
        # explicitly credits withdrawable_balance.
        # Keep these updates in the same transaction as card normalization. If
        # any ciphertext cannot be authenticated, rollback leaves the complete
        # database unchanged instead of silently disabling or rewriting cards.
        db.execute(text(
            "UPDATE wallets SET withdrawable_balance = 0 "
            "WHERE withdrawable_balance IS NULL"
        ))
        db.execute(text(
            "UPDATE wallets SET withdraw_frozen = 0 "
            "WHERE withdraw_frozen IS NULL"
        ))

        # A pre-upgrade operator who already revealed full payment details must
        # remain the only person allowed to execute that transfer. Backfill a
        # unique historical grant holder, but refuse to start when more than
        # one administrator has already seen an active request: automatically
        # choosing either one could permit a real-world double payment.
        payout_assignments = 0
        active_payouts = db.query(WithdrawalOrder).filter(
            WithdrawalOrder.status == "manual_payment_pending"
        ).all()
        for order in active_payouts:
            if order.reviewed_by is None:
                raise RuntimeError(
                    f"manual payout {order.id} is pending without an approval actor"
                )
            grant_actor_ids = {
                int(actor_id)
                for (actor_id,) in db.query(PaymentInstructionGrant.actor_user_id).filter(
                    PaymentInstructionGrant.withdrawal_id == order.id
                ).distinct().all()
            }
            if order.payout_actor_id is not None:
                grant_actor_ids.add(int(order.payout_actor_id))
            if len(grant_actor_ids) > 1:
                raise RuntimeError(
                    f"manual payout {order.id} has multiple historical payout operators; "
                    "audit and close the request before deployment"
                )
            if grant_actor_ids:
                payout_actor_id = next(iter(grant_actor_ids))
                if payout_actor_id == int(order.reviewed_by):
                    raise RuntimeError(
                        f"manual payout {order.id} has the same approval and payout actor; "
                        "audit and close the request before deployment"
                    )
                if order.payout_actor_id is None:
                    order.payout_actor_id = payout_actor_id
                    payout_assignments += 1

        # Completed historical payouts have no remaining transfer risk. Keep
        # the actual confirmer as their assignment for audit consistency.
        for order in db.query(WithdrawalOrder).filter(
            WithdrawalOrder.status == "paid",
            WithdrawalOrder.payout_actor_id.is_(None),
            WithdrawalOrder.paid_by.isnot(None),
        ).all():
            order.payout_actor_id = order.paid_by
            payout_assignments += 1

        seen: set[tuple[int, str]] = set()
        default_seen: set[int] = set()
        changed = 0
        cards = db.query(BankCard).order_by(BankCard.user_id.asc(), BankCard.id.asc()).all()
        for card in cards:
            plain = "".join(reveal(card.card_number).split())
            strict_format_valid = (
                plain.isdigit()
                and 12 <= len(plain) <= 19
                and luhn_check(plain)
            )
            registration_candidate = not card.status or card.status in {
                "registered", "pending_review", "active",
            }
            if not strict_format_valid:
                if card.status != "disabled":
                    card.status = "disabled"
                    changed += 1
                if card.verification_mode != "legacy_unvalidated":
                    card.verification_mode = "legacy_unvalidated"
                    changed += 1
                if card.is_default:
                    card.is_default = False
                    changed += 1
                if card.card_fingerprint is not None:
                    card.card_fingerprint = None
                    changed += 1
                reason = "历史卡号未通过严格数字格式或 Luhn 校验，已停用，请重新登记"
                if card.review_reason != reason:
                    card.review_reason = reason
                    changed += 1
                continue
            if registration_candidate:
                if card.status != "registered":
                    card.status = "registered"
                    changed += 1
                if card.verification_mode != "format_only":
                    card.verification_mode = "format_only"
                    changed += 1
            card_key = fingerprint(plain)
            if card_key and (card.user_id, card_key) in seen:
                # Preserve the encrypted historical row for audit, but do not
                # allow duplicate review or default-card selection.
                card.card_fingerprint = None
                card.status = "disabled"
                card.is_default = False
                card.review_reason = "历史重复卡号已停用"
                changed += 1
                continue
            seen.add((card.user_id, card_key))
            if card.card_fingerprint != card_key:
                card.card_fingerprint = card_key
                changed += 1
            if card.status != "registered" and card.is_default:
                card.is_default = False
                changed += 1
            elif card.status == "registered" and card.is_default and card.user_id in default_seen:
                card.is_default = False
                changed += 1
            elif card.status == "registered" and card.is_default:
                default_seen.add(card.user_id)
        db.commit()

        if target_engine.dialect.name == "postgresql":
            with target_engine.begin() as conn:
                conn.execute(text("ALTER TABLE ledger ALTER COLUMN type TYPE VARCHAR(32)"))
                conn.execute(text("ALTER TABLE bank_cards ALTER COLUMN phone TYPE TEXT"))
        with target_engine.begin() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_ledger_event_key "
                "ON ledger (event_key) WHERE event_key IS NOT NULL"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_bank_card_user_fingerprint "
                "ON bank_cards (user_id, card_fingerprint) WHERE card_fingerprint IS NOT NULL"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_withdrawal_bank_reference "
                "ON withdrawal_orders (bank_reference) WHERE bank_reference IS NOT NULL"
            ))
        if changed:
            print(f"[init_db] 人工提现字段归一: 银行卡 {changed} 项；历史可提现余额保持 0")
        if payout_assignments:
            print(f"[init_db] 人工提现付款经办人回填: {payout_assignments} 条")
        return changed
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _migrate_invite_v2_funding_fields(db_engine=None, db_session=None):
    """Conservatively classify historical balances before Invitation V2.

    Historical wallet history cannot prove which reward card-hours were spent.
    The safe migration therefore marks up to the current consumable balance as
    promotional using all reward credits as an upper bound. This may
    understate cash-backed consumption but can never overstate it. Historical
    frozen funds are entirely promotional until each old order claims an
    auditable allocation during capture/refund.
    """

    from decimal import Decimal

    from sqlalchemy import func

    from app.models.ledger import Ledger
    from app.models.wallet import Wallet
    from app.services.wallet_balance import spendable_wallet_balance

    target_engine = db_engine or engine
    target_inspector = inspect(target_engine)
    tables = set(target_inspector.get_table_names())
    if "wallets" not in tables:
        return {"wallets_backfilled": 0}

    owns_session = db_session is None
    db = db_session or Session(bind=target_engine)
    marker = "20260826_invite_v2_promotional_funding_v1"
    reward_types = (
        "rebate",
        "supplier_rebate",
        "invite_reward",
        "test_rebate",
        "test_supplier",
        "test_invite",
        "consumer_purchase_rebate",
        "supplier_sales_rebate",
        "invite_first_order_reward",
        "invite_qualification_bonus",
        "invite_consumption_commission",
    )
    try:
        if "invite_records" in tables:
            duplicates = db.execute(text(
                "SELECT invitee_id, COUNT(*) AS duplicate_count "
                "FROM invite_records GROUP BY invitee_id HAVING COUNT(*) > 1 "
                "ORDER BY invitee_id LIMIT 10"
            )).all()
            if duplicates:
                ids = ", ".join(str(row[0]) for row in duplicates)
                raise RuntimeError(
                    "duplicate invite relationships require manual audit before V2; "
                    f"invitee_id sample: {ids}"
                )

        db.execute(text(
            "CREATE TABLE IF NOT EXISTS app_migrations ("
            "name VARCHAR(128) PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))
        claim = db.execute(
            text(
                "INSERT INTO app_migrations (name) VALUES (:name) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"name": marker},
        )
        owns_migration = claim.rowcount == 1
        changed = 0
        if owns_migration:
            wallets = db.query(Wallet).with_for_update().order_by(Wallet.id.asc()).all()
            for wallet in wallets:
                current_spendable = max(
                    Decimal("0"), Decimal(str(spendable_wallet_balance(wallet, db)))
                )
                reward_credits = db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(
                    Ledger.user_id == wallet.user_id,
                    Ledger.direction == "in",
                    Ledger.type.in_(reward_types),
                ).scalar()
                reward_upper_bound = max(Decimal("0"), Decimal(str(reward_credits or 0)))
                existing_promotional = max(
                    Decimal("0"), Decimal(str(wallet.promotional_balance or 0))
                )
                wallet.promotional_balance = min(
                    current_spendable,
                    max(existing_promotional, reward_upper_bound),
                )
                # No historical per-order split exists. Marking all frozen
                # funds promotional is the only non-inflating cash policy.
                wallet.promotional_frozen = max(
                    Decimal("0"), Decimal(str(wallet.frozen or 0))
                )
                changed += 1
        # Validate on every run so a future writer cannot silently turn a
        # promotional reward into a cash-backed commission base.
        wallets = db.query(Wallet).order_by(Wallet.id.asc()).all()
        for wallet in wallets:
            promotional = Decimal(str(wallet.promotional_balance or 0))
            promotional_frozen = Decimal(str(wallet.promotional_frozen or 0))
            spendable = Decimal(str(spendable_wallet_balance(wallet, db)))
            frozen = Decimal(str(wallet.frozen or 0))
            if (
                promotional < 0
                or promotional_frozen < 0
                or promotional > spendable
                or promotional_frozen > frozen
            ):
                raise RuntimeError(
                    f"wallet promotional invariant failed for wallet_id={wallet.id}"
                )

        db.commit()
        if "invite_records" in tables:
            with target_engine.begin() as conn:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_invite_records_invitee_unique "
                    "ON invite_records (invitee_id)"
                ))
        if changed:
            print(f"[init_db] 邀请V2资金分层: 保守归类钱包 {changed} 个")
        return {"wallets_backfilled": changed}
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _migrate_legacy_card_hours_to_cny(db_engine=None, db_session=None):
    """Convert the complete legacy card-hour ledger into direct CNY money.

    The retired accounting unit had the immutable production conversion
    ``1 card hour = CNY 1.002``.  This migration is intentionally separate
    from display FX: CNY remains the canonical settlement currency, while
    HKD/USD are presentation-only conversions fetched from the daily FX
    table.

    A marker is claimed in the same transaction as every balance change.  A
    concurrent or repeated startup therefore cannot apply the factor twice.
    Source-market CNY prices and provider CNY payment/refund/payout amounts
    are not scaled.  Their legacy companion ``card_hours`` fields are instead
    normalized to the already authoritative CNY amount and a 1:1 rate.
    """
    import copy
    import json
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

    from app.models.order import Order
    from app.models.order_renewal import OrderRenewal

    target_engine = db_engine or engine
    owns_session = db_session is None
    db = db_session or Session(bind=target_engine)
    marker = "20260929_legacy_card_hours_to_direct_cny_v1"
    factor = Decimal("1.002")
    quantum = Decimal("0.000001")

    inspector = inspect(target_engine)
    table_columns = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }

    def has_columns(table: str, *columns: str) -> bool:
        return table in table_columns and set(columns).issubset(table_columns[table])

    def touched(result) -> int:
        return max(int(result.rowcount or 0), 0)

    def scale_columns(table: str, columns: tuple[str, ...], where: str | None = None) -> int:
        existing = tuple(column for column in columns if has_columns(table, column))
        if not existing:
            return 0
        assignments = ", ".join(
            f'"{column}" = "{column}" * 1.002' for column in existing
        )
        predicate = f" WHERE {where}" if where else ""
        return touched(db.execute(text(
            f'UPDATE "{table}" SET {assignments}{predicate}'
        )))

    money_keys = {
        "amount",
        "amount_card_hours",
        "coupon_discount",
        "payable_amount_card_hours",
        "renewal_amount_card_hours",
        "historical_test_revenue",
        "accumulated_revenue",
    }

    def scaled_json(value):
        """Scale known money keys without reinterpreting unrelated numbers."""
        if isinstance(value, dict):
            changed = False
            result = {}
            for key, item in value.items():
                if key in money_keys and item is not None and not isinstance(item, bool):
                    try:
                        converted = (
                            Decimal(str(item)) * factor
                        ).quantize(quantum, rounding=ROUND_HALF_UP)
                    except (InvalidOperation, ValueError, TypeError):
                        result[key] = item
                    else:
                        result[key] = float(converted)
                        changed = changed or result[key] != item
                else:
                    result[key], item_changed = scaled_json(item)
                    changed = changed or item_changed
            return result, changed
        if isinstance(value, list):
            changed = False
            result = []
            for item in value:
                converted, item_changed = scaled_json(item)
                result.append(converted)
                changed = changed or item_changed
            return result, changed
        return value, False

    counts: dict[str, int] = {}
    try:
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS app_migrations ("
            "name VARCHAR(128) PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS app_migration_audits ("
            "name VARCHAR(128) PRIMARY KEY, "
            "from_unit VARCHAR(32) NOT NULL, "
            "to_unit VARCHAR(32) NOT NULL, "
            "conversion_factor VARCHAR(32) NOT NULL, "
            "details TEXT NOT NULL, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))
        claim = db.execute(
            text(
                "INSERT INTO app_migrations (name) VALUES (:name) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"name": marker},
        )
        if claim.rowcount != 1:
            db.commit()
            return {"applied": False, "factor": str(factor), "rows": {}}

        scalable_columns = {
            "wallets": (
                "balance", "frozen", "withdrawable_balance", "withdraw_frozen",
                "promotional_balance", "promotional_frozen",
            ),
            "ledger": ("amount", "balance_after"),
            "orders": ("amount", "coupon_discount"),
            "order_renewals": ("amount", "total_amount_after"),
            "assets": ("value", "sell_price", "rebate_amount"),
            "revenues": ("amount",),
            "reward_accruals": ("base_amount", "reward_amount"),
            "invite_records": ("reward_amount",),
            "coupon_campaigns": ("amount", "min_amount"),
            "coupons": ("amount", "min_amount"),
        }
        for table, columns in scalable_columns.items():
            count = scale_columns(table, columns)
            if count:
                counts[table] = count

        # Preserve exact conservation constraints after rounding each CNY
        # component to the six-decimal ledger scale.
        if has_columns(
            "order_funding_allocations",
            "gross_amount", "cash_amount", "promotional_amount",
        ):
            result = db.execute(text(
                "UPDATE order_funding_allocations SET "
                "cash_amount = ROUND(cash_amount * 1.002, 6), "
                "promotional_amount = ROUND(promotional_amount * 1.002, 6), "
                "gross_amount = ROUND(cash_amount * 1.002, 6) + "
                "ROUND(promotional_amount * 1.002, 6)"
            ))
            if touched(result):
                counts["order_funding_allocations"] = touched(result)

        if has_columns(
            "merchant_settlements",
            "gross_amount", "service_fee_amount", "net_amount",
        ):
            result = db.execute(text(
                "UPDATE merchant_settlements SET "
                "service_fee_amount = ROUND(service_fee_amount * 1.002, 6), "
                "net_amount = ROUND(net_amount * 1.002, 6), "
                "gross_amount = ROUND(service_fee_amount * 1.002, 6) + "
                "ROUND(net_amount * 1.002, 6)"
            ))
            if touched(result):
                counts["merchant_settlements"] = touched(result)

        if has_columns(
            "holding_asset_sales",
            "unit_price_cny_per_gpu_hour",
            "unit_price_card_hours_per_gpu_hour",
            "buy_value_card_hours",
            "sell_value_card_hours",
            "pnl_card_hours",
            "cash_value_card_hours",
            "promotional_value_card_hours",
        ):
            result = db.execute(text(
                "UPDATE holding_asset_sales SET "
                "unit_price_card_hours_per_gpu_hour = unit_price_cny_per_gpu_hour, "
                "buy_value_card_hours = ROUND(buy_value_card_hours * 1.002, 6), "
                "cash_value_card_hours = ROUND(cash_value_card_hours * 1.002, 6), "
                "promotional_value_card_hours = ROUND(promotional_value_card_hours * 1.002, 6), "
                "sell_value_card_hours = ROUND(cash_value_card_hours * 1.002, 6) + "
                "ROUND(promotional_value_card_hours * 1.002, 6), "
                "pnl_card_hours = ROUND(cash_value_card_hours * 1.002, 6) + "
                "ROUND(promotional_value_card_hours * 1.002, 6) - "
                "ROUND(buy_value_card_hours * 1.002, 6)"
            ))
            if touched(result):
                counts["holding_asset_sales"] = touched(result)

        # KAI stores its upstream quote directly in CNY. Historical supplier
        # and retired external catalogue rows stored their charge in card
        # hours, so only non-KAI product prices are converted.
        if has_columns("products", "price", "market_source"):
            version_assignment = (
                ", version = version + 1" if has_columns("products", "version") else ""
            )
            result = db.execute(text(
                "UPDATE products SET price = price * 1.002"
                f"{version_assignment} "
                "WHERE LOWER(COALESCE(market_source, 'wod')) <> 'kai'"
            ))
            if touched(result):
                counts["products"] = touched(result)
        if has_columns("price_history", "price", "product_id") and has_columns(
            "products", "id", "market_source"
        ):
            result = db.execute(text(
                "UPDATE price_history SET price = price * 1.002 "
                "WHERE EXISTS (SELECT 1 FROM products "
                "WHERE products.id = price_history.product_id "
                "AND LOWER(COALESCE(products.market_source, 'wod')) <> 'kai')"
            ))
            if touched(result):
                counts["price_history"] = touched(result)

        # Negotiation rows already declared as CNY stay unchanged. This branch
        # only handles databases that explicitly persisted the retired unit.
        for table, columns in (
            ("buy_requests", ("max_unit_price", "budget")),
            ("buy_request_quotes", ("unit_price", "total_price")),
            ("buy_request_quote_revisions", ("unit_price", "total_price")),
        ):
            if not has_columns(table, "currency"):
                continue
            count = scale_columns(
                table,
                columns,
                "UPPER(TRIM(currency)) IN ('CARD_HOUR', 'CARD_HOURS', 'CH')",
            )
            if count:
                db.execute(text(
                    f'UPDATE "{table}" SET currency = \'CNY\' '
                    "WHERE UPPER(TRIM(currency)) IN ('CARD_HOUR', 'CARD_HOURS', 'CH')"
                ))
                counts[table] = count

        # Provider CNY is authoritative for these records; assigning rather
        # than multiplying also eliminates historical rounding residue.
        for table in ("payment_orders", "payment_refunds", "payment_refund_requests"):
            if not has_columns(table, "amount_cny", "card_hours"):
                continue
            assignments = "card_hours = amount_cny"
            if table == "payment_orders" and has_columns(table, "card_hour_rate"):
                assignments += ", card_hour_rate = 1"
            result = db.execute(text(f'UPDATE "{table}" SET {assignments}'))
            if touched(result):
                counts[table] = touched(result)

        if has_columns(
            "withdrawal_orders", "amount_card_hours", "locked_rate_cny", "gross_amount_cny"
        ):
            result = db.execute(text(
                "UPDATE withdrawal_orders SET "
                "amount_card_hours = gross_amount_cny, locked_rate_cny = 1"
            ))
            if touched(result):
                counts["withdrawal_orders"] = touched(result)

        # Historical idempotency responses and immutable order snapshots are
        # still served to clients, so their compatibility money fields must
        # describe the same newly converted values as the relational columns.
        if has_columns("orders", "product_snapshot"):
            snapshots_changed = 0
            for order in db.query(Order).filter(Order.product_snapshot.isnot(None)).all():
                snapshot = copy.deepcopy(order.product_snapshot)
                if not isinstance(snapshot, dict):
                    continue
                unit_keys = (
                    "confirmed_unit_price_card_hours",
                    "unit_price_card_hours",
                )
                converted_any = False
                for unit_key in unit_keys:
                    raw_unit = snapshot.get(unit_key)
                    if raw_unit is None:
                        continue
                    try:
                        converted = (Decimal(str(raw_unit)) * factor).quantize(
                            quantum, rounding=ROUND_HALF_UP
                        )
                    except (InvalidOperation, ValueError, TypeError):
                        continue
                    snapshot[unit_key] = format(converted, "f")
                    converted_any = True
                if not converted_any:
                    continue
                snapshot["settlement_currency"] = "CNY"
                snapshot["legacy_card_hour_conversion_factor"] = str(factor)
                order.product_snapshot = snapshot
                snapshots_changed += 1
            if snapshots_changed:
                counts["order_product_snapshots"] = snapshots_changed

        if has_columns("order_renewals", "response_payload"):
            payloads_changed = 0
            for renewal in db.query(OrderRenewal).filter(
                OrderRenewal.response_payload.isnot(None)
            ).all():
                payload, changed = scaled_json(copy.deepcopy(renewal.response_payload))
                if changed:
                    renewal.response_payload = payload
                    payloads_changed += 1
            if payloads_changed:
                counts["order_renewal_payloads"] = payloads_changed

        db.flush()
        conservation_checks = []
        if has_columns(
            "order_funding_allocations",
            "gross_amount", "cash_amount", "promotional_amount",
        ):
            conservation_checks.append((
                "order funding",
                "SELECT COUNT(*) FROM order_funding_allocations "
                "WHERE ABS(gross_amount - cash_amount - promotional_amount) > 0.000001",
            ))
        if has_columns(
            "merchant_settlements",
            "gross_amount", "service_fee_amount", "net_amount",
        ):
            conservation_checks.append((
                "merchant settlement",
                "SELECT COUNT(*) FROM merchant_settlements "
                "WHERE ABS(gross_amount - service_fee_amount - net_amount) > 0.000001",
            ))
        if has_columns(
            "holding_asset_sales",
            "buy_value_card_hours", "sell_value_card_hours", "pnl_card_hours",
            "cash_value_card_hours", "promotional_value_card_hours",
        ):
            conservation_checks.extend((
                (
                    "holding sale funding",
                    "SELECT COUNT(*) FROM holding_asset_sales "
                    "WHERE ABS(sell_value_card_hours - cash_value_card_hours - "
                    "promotional_value_card_hours) > 0.000001",
                ),
                (
                    "holding sale P&L",
                    "SELECT COUNT(*) FROM holding_asset_sales "
                    "WHERE ABS(pnl_card_hours - sell_value_card_hours + "
                    "buy_value_card_hours) > 0.000001",
                ),
            ))
        for label, statement in conservation_checks:
            invalid = int(db.execute(text(statement)).scalar_one() or 0)
            if invalid:
                raise RuntimeError(
                    f"direct CNY migration violated {label} conservation for {invalid} rows"
                )

        db.execute(text(
            "INSERT INTO app_migration_audits "
            "(name, from_unit, to_unit, conversion_factor, details) "
            "VALUES (:name, :from_unit, :to_unit, :factor, :details)"
        ), {
            "name": marker,
            "from_unit": "CARD_HOUR",
            "to_unit": "CNY",
            "factor": str(factor),
            "details": json.dumps(counts, ensure_ascii=False, sort_keys=True),
        })
        db.commit()
        if counts:
            print(
                "[init_db] 历史卡时直转人民币: "
                f"倍率 {factor}, 迁移记录 {sum(counts.values())} 条"
            )
        return {"applied": True, "factor": str(factor), "rows": counts}
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def init():
    # This must be the first executable statement: create_all and every helper
    # below can write. Deployment preflight runs earlier too, but init_db must
    # remain fail-closed when invoked manually.
    assert_sensitive_storage_secure()
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _migrate_community_comment_idempotency()
    _migrate_community_like_idempotency()
    _migrate_community_follow_idempotency()
    _migrate_buy_request_idempotency()
    _migrate_market_candle_resolutions()
    _migrate_order_request_scope()
    _migrate_product_market_sources()
    _migrate_product_create_idempotency()
    _reconcile_supplier_completed_order_counts()
    _normalize_kai_identity_issuers()
    _ensure_auth_identity_constraints()
    _migrate_unverified_phone_flags()
    _migrate_payment_precision_and_pending_deadlines()
    _migrate_manual_payout_fields()
    _migrate_invite_v2_funding_fields()
    _migrate_legacy_card_hours_to_cny()
    if engine.dialect.name == "sqlite":
        # WAL permits App reads to continue while independent market-source
        # collectors persist fresh snapshots.  The setting is durable for the
        # database file and is safe to re-assert on every container startup.
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_recovery_email_fingerprint "
            "ON users (recovery_email_fingerprint) "
            "WHERE recovery_email_fingerprint IS NOT NULL"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_publish_batch ON posts (publish_batch)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_content_type ON posts (content_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_source_item_id ON posts (source_item_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_content_hash ON posts (content_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_market_snapshot_lookup ON market_price_snapshots (gpu_model, gpu_variant, source, observed_at)"))
        # Latest-price queries group by this exact source-series identity.  The
        # original lookup index starts with gpu_model and forces SQLite to build
        # a temporary grouping tree as history grows.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_market_snapshot_latest "
            "ON market_price_snapshots (source, gpu_model, gpu_variant, billing_mode, observed_at DESC)"
        ))
        # Seven-day metrics filter by source and observation time before grouping
        # in Python, so keep that access path independent from product lookups.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_market_snapshot_history "
            "ON market_price_snapshots (source, observed_at, gpu_model, gpu_variant, billing_mode)"
        ))
        # OHLC requests select one exact model/variant/billing series, then scan
        # only the requested sources and range in chronological order.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_market_snapshot_candles "
            "ON market_price_snapshots (gpu_model, gpu_variant, billing_mode, source, observed_at)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_market_history_selection "
            "ON market_history_points (upstream_provider, gpu_model, gpu_variant, billing_mode, dataset_source, observed_at)"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_buy_request_owner_type ON buy_requests (user_id, request_type, status)"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_buy_request_deals_active_slot "
            "ON buy_request_deals (active_slot)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_buy_request_quote_revision "
            "ON buy_request_quote_revisions (quote_id, revision_number)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_buy_request_deals_request_created "
            "ON buy_request_deals (buy_request_id, created_at)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_buy_request_events_request_created "
            "ON buy_request_events (buy_request_id, created_at)"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_created_platform ON orders (created_platform)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_last_modified_platform ON orders (last_modified_platform)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_order_renewals_created_platform ON order_renewals (created_platform)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_created ON notifications (user_id, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications (user_id, is_read, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_user_visibility ON notifications (user_id, deleted_at, expires_at, is_read, created_at DESC)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_notifications_user_dedupe ON notifications (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notification_broadcast_visibility ON notification_broadcasts (notification_type, status, expires_at, created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notification_broadcasts_revoked_by_user_id ON notification_broadcasts (revoked_by_user_id)"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ledger_payment_credit "
            "ON ledger (ref_payment_order_id) WHERE ref_payment_order_id IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ledger_payment_refund "
            "ON ledger (ref_payment_refund_id) WHERE ref_payment_refund_id IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_payment_order_user_provider_request "
            "ON payment_orders (user_id, provider, client_request_id)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ledger_order_renewal "
            "ON ledger (ref_order_renewal_id) WHERE ref_order_renewal_id IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ledger_reward_accrual "
            "ON ledger (ref_reward_accrual_id) WHERE ref_reward_accrual_id IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ledger_merchant_settlement "
            "ON ledger (ref_merchant_settlement_id) WHERE ref_merchant_settlement_id IS NOT NULL"
        ))
    _migrate_offline_purchases()
    _migrate_buy_request_quote_revisions()
    _migrate_legacy_market_history()
    _migrate_sensitive_fields()
    _ensure_user_wallets()
    print("[init_db] 表已创建/确认存在")


if __name__ == "__main__":
    init()
