"""SMTP delivery for 算力星图-owned email verification and password recovery."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Literal
from urllib.parse import urlsplit

from app.core.config import settings
from app.utils.email_address import normalize_email
from app.utils.response import BizError


RecoveryEmailKind = Literal["verify_email", "password_reset_email"]


def email_delivery_configured() -> bool:
    if not settings.ACCOUNT_RECOVERY_EMAIL_ENABLED:
        return False
    if not settings.ACCOUNT_RECOVERY_SMTP_HOST.strip():
        return False
    if not (1 <= settings.ACCOUNT_RECOVERY_SMTP_PORT <= 65535):
        return False
    if settings.ACCOUNT_RECOVERY_SMTP_SSL == settings.ACCOUNT_RECOVERY_SMTP_STARTTLS:
        return False
    username = settings.ACCOUNT_RECOVERY_SMTP_USERNAME.strip()
    password = settings.ACCOUNT_RECOVERY_SMTP_PASSWORD
    if bool(username) != bool(password):
        return False
    try:
        normalize_email(settings.ACCOUNT_RECOVERY_SMTP_FROM)
    except ValueError:
        return False
    parsed = urlsplit(settings.ACCOUNT_RECOVERY_PUBLIC_WEB_ORIGIN.strip())
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )


def require_email_delivery() -> None:
    if not email_delivery_configured():
        raise BizError("邮箱服务尚未配置", code=50320, status_code=503)


def _link(kind: RecoveryEmailKind, token: str) -> str:
    origin = settings.ACCOUNT_RECOVERY_PUBLIC_WEB_ORIGIN.strip().rstrip("/")
    path = "/verify-email" if kind == "verify_email" else "/reset-password"
    # Fragments are not sent in HTTP requests, nginx access logs or Referer.
    return f"{origin}{path}#token={token}"


def _deliver(message: EmailMessage) -> None:
    host = settings.ACCOUNT_RECOVERY_SMTP_HOST.strip()
    port = settings.ACCOUNT_RECOVERY_SMTP_PORT
    timeout = max(1.0, settings.ACCOUNT_RECOVERY_SMTP_TIMEOUT_SECONDS)
    context = ssl.create_default_context()
    if settings.ACCOUNT_RECOVERY_SMTP_SSL:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    with smtp:
        smtp.ehlo()
        if settings.ACCOUNT_RECOVERY_SMTP_STARTTLS:
            smtp.starttls(context=context)
            smtp.ehlo()
        username = settings.ACCOUNT_RECOVERY_SMTP_USERNAME.strip()
        if username:
            smtp.login(username, settings.ACCOUNT_RECOVERY_SMTP_PASSWORD)
        smtp.send_message(message)


def _message(recipient: str, subject: str) -> EmailMessage:
    require_email_delivery()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = normalize_email(settings.ACCOUNT_RECOVERY_SMTP_FROM)
    message["To"] = normalize_email(recipient)
    return message


def send_account_recovery_email(kind: RecoveryEmailKind, recipient: str, token: str) -> None:
    """Send one recovery message; callers must never log its arguments."""

    if kind == "verify_email":
        subject = "验证你的算力星图绑定邮箱"
        intro = "你正在为算力星图账号绑定或更换邮箱。"
        action = "完成邮箱绑定"
    else:
        subject = "重置你的算力星图密码"
        intro = "我们收到了你的算力星图密码重置请求。"
        action = "设置新密码"
    message = _message(recipient, subject)
    if kind == "password_reset_email":
        message.set_content(
            f"{intro}\n\n在算力星图 App 的“忘记密码”页面输入以下重置码：\n{token}\n\n"
            f"也可以使用网页版{action}：\n{_link(kind, token)}\n\n"
            "重置码和链接只能使用一次并会在短时间后失效。如果不是你本人操作，请忽略本邮件。"
        )
    else:
        message.set_content(
            f"{intro}\n\n请点击以下链接{action}：\n{_link(kind, token)}\n\n"
            "链接只能使用一次并会在短时间后失效。如果不是你本人操作，请忽略本邮件。"
        )
    _deliver(message)


def send_password_changed_notice(recipient: str) -> None:
    """Notify a verified recovery address without including any secret link."""

    message = _message(recipient, "你的算力星图密码已更新")
    message.set_content(
        "你的算力星图账号密码刚刚完成重置，全部旧登录会话已退出。\n\n"
        "如果这不是你本人操作，请立即联系算力星图客服。"
    )
    _deliver(message)
