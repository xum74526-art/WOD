from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping


class ProviderUnavailable(RuntimeError):
    def __init__(self, kind: str, provider: str, reason: str = "not_configured"):
        super().__init__(f"{kind} provider {provider} is unavailable: {reason}")
        self.kind = kind
        self.provider = provider
        self.reason = reason


@dataclass(frozen=True)
class ProviderDescriptor:
    kind: str
    provider: str
    status: str
    configured: bool
    capabilities: tuple[str, ...] = ()
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "provider": self.provider,
            "status": self.status,
            "configured": self.configured,
            "capabilities": list(self.capabilities),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PaymentRequest:
    payment_no: str
    user_id: int
    amount: Decimal
    currency: str
    purpose: str
    return_url: str
    idempotency_key: str
    client_ip: str = "127.0.0.1"
    channel: str | None = None


@dataclass(frozen=True)
class PaymentSession:
    provider_reference: str
    checkout_url: str
    expires_at: datetime | None = None
    client_payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundSession:
    provider_reference: str
    status: str


@dataclass(frozen=True)
class PaymentNotification:
    event_type: str
    event_id: str
    payment_no: str
    provider_reference: str
    amount: Decimal
    currency: str
    succeeded: bool
    raw_status: str
    refund_reference: str | None = None


class PaymentProvider(ABC):
    descriptor: ProviderDescriptor

    @abstractmethod
    def create_checkout(self, request: PaymentRequest) -> PaymentSession:
        raise NotImplementedError

    @abstractmethod
    def verify_notification(self, raw_body: bytes, signature: str) -> PaymentNotification:
        raise NotImplementedError

    @abstractmethod
    def query_payment(self, provider_reference: str) -> PaymentNotification:
        """Query the provider directly for a payment's authoritative state."""
        raise NotImplementedError

    @abstractmethod
    def create_refund(
        self,
        *,
        provider_reference: str,
        refund_no: str,
        amount: Decimal,
        reason: str,
    ) -> RefundSession:
        raise NotImplementedError


@dataclass(frozen=True)
class KycRequest:
    application_id: int
    user_id: int
    verification_type: str
    country_code: str
    return_url: str


@dataclass(frozen=True)
class KycSession:
    provider_reference: str
    verification_url: str
    expires_at: datetime | None = None


class KycProvider(ABC):
    descriptor: ProviderDescriptor

    @abstractmethod
    def start_verification(self, request: KycRequest) -> KycSession:
        raise NotImplementedError


@dataclass(frozen=True)
class UploadRequest:
    upload_id: str
    object_no: str
    user_id: int
    category: str
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str | None


@dataclass(frozen=True)
class UploadTarget:
    provider_reference: str
    bucket: str
    object_key: str
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)
    expires_at: datetime | None = None


class StorageProvider(ABC):
    descriptor: ProviderDescriptor

    @abstractmethod
    def create_upload(self, request: UploadRequest) -> UploadTarget:
        raise NotImplementedError

    @abstractmethod
    def complete_upload(self, provider_reference: str, object_key: str, etag: str | None) -> None:
        raise NotImplementedError


class DisabledPaymentProvider(PaymentProvider):
    def __init__(self, requested: str, reason: str):
        self.descriptor = ProviderDescriptor(
            kind="payment",
            provider=requested,
            status="disabled" if requested == "disabled" else "adapter_missing",
            configured=False,
            capabilities=("checkout", "webhook", "refund", "payout", "double_entry_ledger"),
            reason=reason,
        )

    def create_checkout(self, request: PaymentRequest) -> PaymentSession:
        raise ProviderUnavailable("payment", self.descriptor.provider, self.descriptor.reason or "not_configured")

    def verify_notification(self, raw_body: bytes, signature: str) -> PaymentNotification:
        raise ProviderUnavailable("payment", self.descriptor.provider, self.descriptor.reason or "not_configured")

    def query_payment(self, provider_reference: str) -> PaymentNotification:
        raise ProviderUnavailable("payment", self.descriptor.provider, self.descriptor.reason or "not_configured")

    def create_refund(
        self,
        *,
        provider_reference: str,
        refund_no: str,
        amount: Decimal,
        reason: str,
    ) -> RefundSession:
        raise ProviderUnavailable("payment", self.descriptor.provider, self.descriptor.reason or "not_configured")


class DisabledKycProvider(KycProvider):
    def __init__(self, requested: str, reason: str):
        self.descriptor = ProviderDescriptor(
            kind="kyc",
            provider=requested,
            status="disabled" if requested == "disabled" else "adapter_missing",
            configured=False,
            capabilities=("hosted_verification", "status_callback", "manual_review"),
            reason=reason,
        )

    def start_verification(self, request: KycRequest) -> KycSession:
        raise ProviderUnavailable("kyc", self.descriptor.provider, self.descriptor.reason or "not_configured")


class DisabledStorageProvider(StorageProvider):
    def __init__(self, requested: str, reason: str):
        self.descriptor = ProviderDescriptor(
            kind="object_storage",
            provider=requested,
            status="disabled" if requested == "disabled" else "adapter_missing",
            configured=False,
            capabilities=("private_direct_upload", "signed_download", "quarantine", "delete"),
            reason=reason,
        )

    def create_upload(self, request: UploadRequest) -> UploadTarget:
        raise ProviderUnavailable(
            "object_storage", self.descriptor.provider, self.descriptor.reason or "not_configured"
        )

    def complete_upload(self, provider_reference: str, object_key: str, etag: str | None) -> None:
        raise ProviderUnavailable(
            "object_storage", self.descriptor.provider, self.descriptor.reason or "not_configured"
        )
