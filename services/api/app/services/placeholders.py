from dataclasses import dataclass

from app.security import ApiError


@dataclass(frozen=True)
class ModuleDescriptor:
    key: str
    title: str
    capabilities: tuple[str, ...]
    dependency: str

    def as_dict(self) -> dict:
        ready = self.key in READY_MODULES
        return {
            "key": self.key,
            "title": self.title,
            "status": "ready" if ready else "scaffolded",
            "configured": ready,
            "write_enabled": ready,
            "data_source": "database" if ready else "pending",
            "dependency": self.dependency,
            "reason": None if ready else "not_configured",
            "capabilities": list(self.capabilities),
            "api_version": "v1",
        }


MODULES = {
    "assets": ModuleDescriptor(
        "assets", "资产与设备托管", ("asset_list", "hosting_request", "maintenance_status"), "asset_registry"
    ),
    "revenue": ModuleDescriptor(
        "revenue", "收益与提现", ("revenue_summary", "settlement_list", "withdrawal"), "settlement_worker"
    ),
    "referrals": ModuleDescriptor(
        "referrals", "邀请与返佣", ("invitation", "relation_list", "reward_progress"), "risk_and_rewards"
    ),
    "coupons": ModuleDescriptor(
        "coupons", "优惠券", ("coupon_list", "redeem", "order_validation"), "promotion_engine"
    ),
    "bank_accounts": ModuleDescriptor(
        "bank_accounts", "银行卡", ("tokenized_binding", "masked_list", "unbind"), "payment_provider"
    ),
    "addresses": ModuleDescriptor(
        "addresses", "地址管理", ("create", "update", "delete", "set_default"), "address_repository"
    ),
    "notifications": ModuleDescriptor(
        "notifications", "通知中心", ("inbox", "unread_count", "mark_read", "channel_delivery"), "notification_worker"
    ),
    "disputes": ModuleDescriptor(
        "disputes", "争议与仲裁", ("case_create", "evidence", "timeline", "resolution"), "dispute_workflow"
    ),
    "supplier_revenue": ModuleDescriptor(
        "supplier_revenue", "商家收益", ("balance", "settlements", "withdrawal"), "settlement_worker"
    ),
    "supplier_analytics": ModuleDescriptor(
        "supplier_analytics", "经营统计", ("utilization", "orders", "revenue_series"), "analytics_pipeline"
    ),
    "supplier_rebates": ModuleDescriptor(
        "supplier_rebates", "商家返佣", ("tier", "progress", "settlement_list"), "rebate_engine"
    ),
    "supplier_settings": ModuleDescriptor(
        "supplier_settings", "商家设置", ("store_profile", "contacts", "service_regions"), "supplier_profile_repository"
    ),
    "provisioning": ModuleDescriptor(
        "provisioning", "自动开通", ("start", "status", "retry", "deprovision"), "provisioning_adapter"
    ),
    "credential_vault": ModuleDescriptor(
        "credential_vault", "凭据保险库", ("issue", "rotate", "revoke", "audit"), "kms_and_secret_store"
    ),
    "metering": ModuleDescriptor(
        "metering", "用量计量与续费", ("usage_sync", "billing_period", "renewal", "expiry"), "metering_worker"
    ),
    "teams": ModuleDescriptor(
        "teams", "团队管理", ("team_create", "members", "roles", "invitations"), "team_repository"
    ),
    "api_keys": ModuleDescriptor(
        "api_keys", "API Key", ("create", "scopes", "rotate", "revoke"), "api_key_vault"
    ),
}

READY_MODULES = {
    "addresses",
    "notifications",
    "disputes",
    "supplier_revenue",
    "supplier_settings",
    "teams",
    "api_keys",
}


ACCOUNT_MODULE_KEYS = (
    "assets", "revenue", "referrals", "coupons", "bank_accounts", "addresses",
    "notifications", "disputes", "teams", "api_keys",
)
SUPPLIER_MODULE_KEYS = (
    "supplier_revenue", "supplier_analytics", "supplier_rebates", "supplier_settings",
    "provisioning", "credential_vault", "metering",
)


def descriptor(key: str) -> dict:
    return MODULES[key].as_dict()


def catalog(keys: tuple[str, ...]) -> dict:
    return {key: descriptor(key) for key in keys}


def unavailable(key: str) -> None:
    module = MODULES[key]
    raise ApiError("FEATURE_NOT_CONFIGURED", f"{module.title}功能已预留，真实服务尚未接入", 503)


def empty_collection(key: str, field: str) -> dict:
    return {field: [], "module": descriptor(key)}


def revenue_snapshot(key: str) -> dict:
    return {
        "currency": "CNY",
        "available": "0",
        "pending": "0",
        "settled": "0",
        "records": [],
        "module": descriptor(key),
    }
