from collections.abc import Mapping
from types import MappingProxyType


BUY_REQUEST_STATUSES = frozenset({
    "draft",
    "reviewing",
    "published",
    "negotiating",
    "matched",
    "completed",
    "rejected",
    "closed",
    "expired",
})
BUY_REQUEST_TRANSITIONS: Mapping[str, frozenset[str]] = MappingProxyType({
    "draft": frozenset({"reviewing", "published", "closed"}),
    "reviewing": frozenset({"published", "rejected", "closed"}),
    "published": frozenset({"negotiating", "matched", "closed", "expired"}),
    "negotiating": frozenset({"matched", "closed", "expired"}),
    "matched": frozenset({"completed", "closed"}),
    "completed": frozenset(),
    "rejected": frozenset(),
    "closed": frozenset(),
    "expired": frozenset(),
})

QUOTE_STATUSES = frozenset({
    "draft",
    "submitted",
    "shortlisted",
    "accepted",
    "rejected",
    "withdrawn",
    "expired",
})
QUOTE_TRANSITIONS: Mapping[str, frozenset[str]] = MappingProxyType({
    "draft": frozenset({"submitted", "withdrawn"}),
    "submitted": frozenset({"shortlisted", "rejected", "withdrawn", "expired"}),
    "shortlisted": frozenset({"accepted", "rejected", "withdrawn", "expired"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
    "expired": frozenset(),
})

ORDER_STATUSES = frozenset({
    "pending_confirmation",
    "confirmed",
    "delivering",
    "delivered",
    "completed",
    "cancelled",
})
ORDER_TRANSITIONS: Mapping[str, frozenset[str]] = MappingProxyType({
    "pending_confirmation": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"delivering", "cancelled"}),
    "delivering": frozenset({"delivered"}),
    "delivered": frozenset({"completed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
})


def can_transition(transitions: Mapping[str, frozenset[str]], current: str, target: str) -> bool:
    return target in transitions.get(current, frozenset())
