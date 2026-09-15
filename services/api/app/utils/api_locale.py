"""Locale-aware copy for user-visible API boundary messages.

Business services intentionally keep their existing exception text and error
codes.  Translation happens only when an HTTP response is serialized, which
keeps database state and business decisions independent from presentation.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Request


ApiLocale = Literal["zh-Hant", "zh-Hans", "en"]
DEFAULT_API_LOCALE: ApiLocale = "zh-Hant"


_MESSAGES: dict[str, dict[ApiLocale, str]] = {
    "请求过于频繁，请稍后再试": {
        "zh-Hant": "請求過於頻繁，請稍後再試",
        "zh-Hans": "请求过于频繁，请稍后再试",
        "en": "Too many requests. Please try again later.",
    },
    "验证码错误或已过期": {
        "zh-Hant": "驗證碼錯誤或已過期",
        "zh-Hans": "验证码错误或已过期",
        "en": "The verification code is invalid or has expired.",
    },
    "该手机号已注册": {
        "zh-Hant": "此手機號碼已註冊",
        "zh-Hans": "该手机号已注册",
        "en": "This phone number is already registered.",
    },
    "手机号或密码错误": {
        "zh-Hant": "手機號碼或密碼錯誤",
        "zh-Hans": "手机号或密码错误",
        "en": "The phone number or password is incorrect.",
    },
    "未登录": {
        "zh-Hant": "尚未登入",
        "zh-Hans": "未登录",
        "en": "You are not signed in.",
    },
    "token 无效或已过期": {
        "zh-Hant": "Token 無效或已過期",
        "zh-Hans": "Token 无效或已过期",
        "en": "The token is invalid or has expired.",
    },
    "用户不存在": {
        "zh-Hant": "使用者不存在",
        "zh-Hans": "用户不存在",
        "en": "The user does not exist.",
    },
    "会话无效或已过期": {
        "zh-Hant": "工作階段無效或已過期",
        "zh-Hans": "会话无效或已过期",
        "en": "The session is invalid or has expired.",
    },
    "请求错误": {
        "zh-Hant": "請求錯誤",
        "zh-Hans": "请求错误",
        "en": "Invalid request.",
    },
    "注册信息过长，请缩短后重试": {
        "zh-Hant": "註冊資料過長，請縮短後再試",
        "zh-Hans": "注册信息过长，请缩短后重试",
        "en": "The registration details are too long. Shorten them and try again.",
    },
    "邀请码无效，请检查后重试": {
        "zh-Hant": "邀請碼無效，請檢查後重試",
        "zh-Hans": "邀请码无效，请检查后重试",
        "en": "The invitation code is invalid. Check it and try again.",
    },
    "找回请求参数无效，请检查后重试": {
        "zh-Hant": "帳號找回請求參數無效，請檢查後重試",
        "zh-Hans": "找回请求参数无效，请检查后重试",
        "en": "The account recovery request is invalid. Check it and try again.",
    },
    "邮箱服务尚未配置": {
        "zh-Hant": "電子郵件服務尚未設定",
        "zh-Hans": "邮箱服务尚未配置",
        "en": "The email service is not configured.",
    },
    "当前密码错误": {
        "zh-Hant": "目前密碼錯誤",
        "zh-Hans": "当前密码错误",
        "en": "The current password is incorrect.",
    },
    "原密码错误": {
        "zh-Hant": "原密碼錯誤",
        "zh-Hans": "原密码错误",
        "en": "The current password is incorrect.",
    },
    "链接无效或已过期，请重新申请": {
        "zh-Hant": "連結無效或已過期，請重新申請",
        "zh-Hans": "链接无效或已过期，请重新申请",
        "en": "The link is invalid or has expired. Request a new one.",
    },
    "该邮箱已被其他账号使用": {
        "zh-Hant": "此電子郵件已由其他帳號使用",
        "zh-Hans": "该邮箱已被其他账号使用",
        "en": "This email address is already used by another account.",
    },
    "如果该邮箱已绑定，重置邮件会在几分钟内送达": {
        "zh-Hant": "若此電子郵件已綁定，重設郵件將在數分鐘內送達",
        "zh-Hans": "如果该邮箱已绑定，重置邮件会在几分钟内送达",
        "en": "If this email address is linked to an account, a reset email will arrive within a few minutes.",
    },
}


def normalize_api_locale(value: str | None) -> ApiLocale | None:
    """Normalize one BCP-47-ish language tag used by the three clients."""

    tag = (value or "").strip().lower().replace("_", "-")
    if not tag or tag == "*":
        return None
    if tag == "en" or tag.startswith("en-"):
        return "en"
    if tag == "zh" or tag.startswith("zh-"):
        parts = set(tag.split("-"))
        if parts.intersection({"hans", "cn", "sg"}):
            return "zh-Hans"
        if parts.intersection({"hant", "tw", "hk", "mo"}):
            return "zh-Hant"
        return DEFAULT_API_LOCALE
    return None


def resolve_accept_language(value: str | None) -> ApiLocale:
    """Resolve the highest-priority supported language from a request header."""

    candidates: list[tuple[float, int, ApiLocale]] = []
    for index, item in enumerate((value or "").split(",")):
        parts = [part.strip() for part in item.split(";")]
        locale = normalize_api_locale(parts[0] if parts else "")
        if locale is None:
            continue
        quality = 1.0
        for parameter in parts[1:]:
            name, separator, raw_value = parameter.partition("=")
            if separator and name.strip().lower() == "q":
                try:
                    quality = float(raw_value.strip())
                except ValueError:
                    quality = 0.0
                break
        if quality > 0:
            candidates.append((min(1.0, quality), -index, locale))
    if not candidates:
        return DEFAULT_API_LOCALE
    return max(candidates)[2]


def resolve_request_locale(request: Request) -> ApiLocale:
    return resolve_accept_language(request.headers.get("accept-language"))


def localize_api_message(message: str, locale: ApiLocale) -> str:
    """Translate a known boundary message and preserve unknown business copy."""

    translations = _MESSAGES.get(message)
    if translations is None:
        return message
    return translations[locale]
