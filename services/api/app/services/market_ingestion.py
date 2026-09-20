"""Validate and atomically persist normalized collector batches."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.vast_market import MarketIngestionBatch, VastOffer, VastPriceSnapshot, VastSyncStatus
from app.schemas.ingestion import MarketOfferBatchIn, MarketOfferBatchResult, MarketOfferRecord


class IngestionConflict(RuntimeError):
    pass


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _percentile(values: list[Decimal], ratio: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _payload_hash(batch: MarketOfferBatchIn) -> str:
    payload = batch.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _record_hash(record: MarketOfferRecord) -> str:
    return hashlib.sha256(
        json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _offer_values(record: MarketOfferRecord, billing_mode: str, observed_at: datetime) -> dict[str, Any]:
    return {
        "external_offer_id": record.external_id,
        "billing_mode": billing_mode,
        "gpu_name": record.gpu_name,
        "gpu_model": record.gpu_model,
        "gpu_variant": record.gpu_variant,
        "num_gpus": record.gpu_count,
        "gpu_ram_mb": record.gpu_ram_mb,
        "gpu_total_ram_mb": record.gpu_total_ram_mb,
        "compute_capability": record.compute_capability,
        "cuda_version": record.cuda_version,
        "gpu_memory_bandwidth": record.gpu_memory_bandwidth,
        "nvlink_bandwidth": record.nvlink_bandwidth,
        "total_flops": record.total_flops,
        "cpu_name": record.cpu_name,
        "cpu_arch": record.cpu_arch,
        "cpu_cores": record.cpu_cores,
        "cpu_ram_mb": record.cpu_ram_mb,
        "disk_space_gb": record.disk_space_gb,
        "disk_bandwidth_mbps": record.disk_bandwidth_mbps,
        "internet_down_mbps": record.internet_down_mbps,
        "internet_up_mbps": record.internet_up_mbps,
        "geolocation": record.region,
        "hosting_type": record.hosting_type,
        "verification": record.verification,
        "reliability": record.reliability,
        "duration_days": record.duration_days,
        "currency": record.currency,
        "compute_price_hourly": record.compute_price_hourly,
        "total_price_hourly": record.total_price_hourly,
        "per_gpu_compute_price_hourly": record.per_gpu_compute_price_hourly,
        "per_gpu_total_price_hourly": record.per_gpu_total_price_hourly,
        "minimum_bid_hourly": record.minimum_bid_hourly,
        "storage_price_gb_month": record.storage_price_gb_month,
        "internet_down_price_tb": record.internet_down_price_tb,
        "internet_up_price_tb": record.internet_up_price_tb,
        "discount_rate": record.discount_rate,
        "rentable": record.rentable,
        "rented": record.rented,
        "active": True,
        "raw_hash": _record_hash(record),
        "last_seen_at": observed_at,
        "fetched_at": observed_at,
    }


def _snapshot_signature(payload: dict[str, Any]) -> str:
    stable = {
        key: value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, Decimal) else value
        for key, value in payload.items()
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _store_snapshots(db: Session, rows: Iterable[dict[str, Any]], observed_at: datetime) -> int:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["gpu_model"], row["gpu_variant"], row["billing_mode"])].append(row)
    inserted = 0
    bucket = observed_at.replace(second=0, microsecond=0)
    for (model, variant, billing_mode), offers in grouped.items():
        compute = [item["per_gpu_compute_price_hourly"] for item in offers]
        total = [item["per_gpu_total_price_hourly"] for item in offers]
        payload = {
            "gpu_model": model,
            "gpu_variant": variant,
            "billing_mode": billing_mode,
            "currency": "USD",
            "min_compute_price": min(compute).quantize(Decimal("0.00000001")),
            "median_compute_price": _percentile(compute, Decimal("0.5")).quantize(Decimal("0.00000001")),
            "max_compute_price": max(compute).quantize(Decimal("0.00000001")),
            "min_total_price": min(total).quantize(Decimal("0.00000001")),
            "median_total_price": _percentile(total, Decimal("0.5")).quantize(Decimal("0.00000001")),
            "max_total_price": max(total).quantize(Decimal("0.00000001")),
            "sample_count": len(offers),
            "available_gpu_count": sum(item["num_gpus"] for item in offers),
            "observed_at": bucket,
        }
        payload["signature"] = _snapshot_signature(payload)
        if not db.query(VastPriceSnapshot.id).filter(VastPriceSnapshot.signature == payload["signature"]).first():
            db.add(VastPriceSnapshot(**payload))
            inserted += 1
    return inserted


def _stored_result(batch: MarketIngestionBatch, duplicate: bool) -> MarketOfferBatchResult:
    return MarketOfferBatchResult(
        batch_id=batch.batch_id,
        duplicate=duplicate,
        received=batch.received_count,
        accepted=batch.accepted_count,
        inserted=batch.inserted_count,
        updated=batch.updated_count,
        rejected=batch.rejected_count,
        stale=batch.stale_count,
        deleted=batch.deleted_count,
        snapshots=batch.snapshot_count,
    )


def ingest_market_offer_batch(db: Session, payload: MarketOfferBatchIn) -> MarketOfferBatchResult:
    """Persist one batch in a single transaction, with durable idempotency."""

    digest = _payload_hash(payload)
    existing_batch = db.query(MarketIngestionBatch).filter(
        MarketIngestionBatch.source == payload.source,
        MarketIngestionBatch.dataset == payload.dataset,
        MarketIngestionBatch.batch_id == payload.batch_id,
    ).one_or_none()
    if existing_batch:
        if existing_batch.payload_hash != digest:
            raise IngestionConflict("batch_id_conflict")
        return _stored_result(existing_batch, duplicate=True)

    observed_at = _utc_naive(payload.observed_at)
    batch = MarketIngestionBatch(
        source=payload.source,
        dataset=payload.dataset,
        batch_id=payload.batch_id,
        schema_version=payload.schema_version,
        billing_mode=payload.billing_mode,
        sync_mode=payload.sync_mode,
        payload_hash=digest,
        status="running",
        received_count=len(payload.records),
        observed_at=observed_at,
    )
    db.add(batch)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent retry may have committed the same idempotency key after
        # our initial lookup. Re-read it instead of surfacing a transient 500.
        db.rollback()
        concurrent = db.query(MarketIngestionBatch).filter(
            MarketIngestionBatch.source == payload.source,
            MarketIngestionBatch.dataset == payload.dataset,
            MarketIngestionBatch.batch_id == payload.batch_id,
        ).one_or_none()
        if concurrent is None:
            raise
        if concurrent.payload_hash != digest:
            raise IngestionConflict("batch_id_conflict")
        return _stored_result(concurrent, duplicate=True)

    existing_offers = {
        row.external_offer_id: row
        for row in db.query(VastOffer).filter(VastOffer.billing_mode == payload.billing_mode).all()
    }
    normalized = [_offer_values(record, payload.billing_mode, observed_at) for record in payload.records]
    incoming_ids: set[int] = set()
    inserted = 0
    updated = 0
    for values in normalized:
        external_id = values["external_offer_id"]
        incoming_ids.add(external_id)
        row = existing_offers.get(external_id)
        if row is None:
            db.add(VastOffer(first_seen_at=observed_at, **values))
            inserted += 1
        else:
            for key, value in values.items():
                setattr(row, key, value)
            updated += 1

    if payload.sync_mode == "snapshot":
        stale_query = db.query(VastOffer).filter(
            VastOffer.billing_mode == payload.billing_mode,
            VastOffer.active.is_(True),
        )
        if incoming_ids:
            stale_query = stale_query.filter(VastOffer.external_offer_id.notin_(incoming_ids))
    else:
        stale_cutoff = observed_at - timedelta(seconds=max(settings.VAST_STALE_SECONDS, payload.refresh_seconds))
        stale_query = db.query(VastOffer).filter(
            VastOffer.billing_mode == payload.billing_mode,
            VastOffer.active.is_(True),
            VastOffer.last_seen_at < stale_cutoff,
        )
    stale = stale_query.update({VastOffer.active: False}, synchronize_session=False)
    delete_cutoff = observed_at - timedelta(hours=max(settings.VAST_DELETE_AFTER_HOURS, 1))
    deleted = db.query(VastOffer).filter(
        VastOffer.active.is_(False), VastOffer.last_seen_at < delete_cutoff,
    ).delete(synchronize_session=False)
    snapshots = _store_snapshots(db, normalized, observed_at)
    history_cutoff = observed_at - timedelta(days=max(settings.VAST_HISTORY_DAYS, 1))
    db.query(VastPriceSnapshot).filter(VastPriceSnapshot.observed_at < history_cutoff).delete(synchronize_session=False)
    db.flush()

    status = db.get(VastSyncStatus, payload.billing_mode)
    if status is None:
        status = VastSyncStatus(billing_mode=payload.billing_mode)
        db.add(status)
    status.status = "ok"
    status.refresh_seconds = payload.refresh_seconds
    status.offer_count = len(normalized)
    status.active_offer_count = db.query(VastOffer).filter(
        VastOffer.billing_mode == payload.billing_mode, VastOffer.active.is_(True),
    ).count()
    status.last_attempt_at = observed_at
    status.last_success_at = observed_at
    status.last_error = None
    status.rate_limit = payload.upstream_rate_limit
    status.rate_limit_remaining = payload.upstream_rate_limit_remaining
    status.rate_limit_reset_at = (
        _utc_naive(payload.upstream_rate_limit_reset_at)
        if payload.upstream_rate_limit_reset_at else None
    )

    batch.status = "ok"
    batch.accepted_count = len(normalized)
    batch.inserted_count = inserted
    batch.updated_count = updated
    batch.rejected_count = 0
    batch.stale_count = stale
    batch.deleted_count = deleted
    batch.snapshot_count = snapshots
    batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return _stored_result(batch, duplicate=False)
