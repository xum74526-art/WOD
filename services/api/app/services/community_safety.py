"""Small, deterministic first-line filter for publicly submitted community text.

This is deliberately conservative and is only one layer of the UGC safety
system. User reports, account blocks, and the administrator queue handle
contextual abuse that a text filter cannot determine safely.
"""

from __future__ import annotations

import re
import unicodedata

from app.utils.response import BizError


_PROHIBITED_PATTERNS = (
    re.compile(r"(?:裸聊|约炮|强奸|儿童色情|博彩平台|代办假证|出售毒品|买卖毒品)"),
    re.compile(r"\b(?:child\s*porn|rape\s*video|sell\s*drugs|buy\s*drugs)\b", re.I),
    re.compile(r"\b(?:kill\s+yourself|go\s+kill\s+yourself)\b", re.I),
)
_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I,
)
_LONG_SENSITIVE_NUMBER = re.compile(r"(?<!\d)\d{15,19}(?!\d)")


def validate_public_community_text(value: str, *, field_name: str = "内容") -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise BizError(f"{field_name}不能为空")
    if _PRIVATE_KEY_PATTERN.search(normalized):
        raise BizError("请勿在社区发布私钥或其他登录凭据")
    if _LONG_SENSITIVE_NUMBER.search(normalized):
        raise BizError("请勿在社区发布身份证号、银行卡号或其他敏感号码")
    if any(pattern.search(normalized) for pattern in _PROHIBITED_PATTERNS):
        raise BizError("内容包含不适合公开发布的信息，请修改后重试")
    return normalized


def validate_public_display_name(value: str) -> str:
    normalized = validate_public_community_text(value, field_name="用户名")
    if not 2 <= len(normalized) <= 64:
        raise BizError("用户名长度必须为 2 到 64 个字符")
    return normalized


def safe_public_display_name(value: str | None) -> str:
    """Return a review-safe name for legacy rows that predate write filtering."""

    if not value:
        return "社区用户"
    try:
        return validate_public_display_name(value)
    except BizError:
        return "社区用户"
