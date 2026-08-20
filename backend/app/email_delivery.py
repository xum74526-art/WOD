import smtplib
from email.message import EmailMessage

from app.config import settings


class EmailDeliveryError(Exception):
    pass


def password_reset_email_configured() -> bool:
    return email_configured()


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


def _send(message: EmailMessage) -> None:
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("email delivery failed") from exc


def send_password_reset_email(destination: str, reset_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "重置你的 KAI 密码"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = destination
    message.set_content(
        "我们收到了你的 KAI 密码重置请求。\n\n"
        f"请在 {settings.PASSWORD_RESET_TTL_MINUTES} 分钟内打开：\n{reset_url}\n\n"
        "如果不是你发起的请求，可以忽略这封邮件。"
    )
    _send(message)


def send_verification_email(destination: str, verification_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "验证你的 KAI 邮箱"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = destination
    message.set_content(
        "请验证你的 KAI 登录邮箱。\n\n"
        f"请在 {settings.EMAIL_VERIFICATION_TTL_HOURS} 小时内打开：\n{verification_url}\n\n"
        "如果不是你创建的账户，可以忽略这封邮件。"
    )
    _send(message)


def send_notification_email(destination: str, subject: str, text_body: str, action_url: str | None) -> None:
    message = EmailMessage()
    message["Subject"] = f"KAI · {subject}"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = destination
    content = text_body
    if action_url:
        content += f"\n\n查看详情：\n{action_url}"
    content += "\n\n这是一封由 KAI 业务状态变化自动触发的通知。"
    message.set_content(content)
    _send(message)
