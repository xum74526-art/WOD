import logging
import threading
from datetime import datetime, timedelta, timezone

from app import email_delivery
from app.config import settings
from app.db import SessionLocal
from app.models import EmailOutbox


logger = logging.getLogger(__name__)


def deliver_pending(limit: int = 20) -> int:
    db = SessionLocal()
    delivered = 0
    try:
        now = datetime.now(timezone.utc)
        rows = db.query(EmailOutbox).filter(
            EmailOutbox.status.in_(("pending", "failed")),
            EmailOutbox.next_attempt_at <= now,
            EmailOutbox.attempts < settings.EMAIL_OUTBOX_MAX_ATTEMPTS,
        ).order_by(EmailOutbox.created_at.asc()).limit(limit).all()
        for row in rows:
            row.status = "sending"
            row.attempts += 1
            db.commit()
            try:
                email_delivery.send_notification_email(
                    row.destination, row.subject, row.text_body, row.action_url
                )
            except email_delivery.EmailDeliveryError as exc:
                row.status = "failed"
                row.last_error = str(exc)[:500]
                row.next_attempt_at = now + timedelta(minutes=min(60, 2 ** row.attempts))
                db.commit()
                logger.warning("email outbox delivery failed", extra={"outbox_id": row.id})
            else:
                row.status = "sent"
                row.sent_at = datetime.now(timezone.utc)
                row.last_error = None
                db.commit()
                delivered += 1
        return delivered
    except Exception:
        db.rollback()
        logger.exception("email outbox worker failed")
        return delivered
    finally:
        db.close()


class EmailScheduler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        with self._lock:
            if not settings.EMAIL_NOTIFICATION_ENABLED or not email_delivery.email_configured() or (self._thread and self._thread.is_alive()):
                return False
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._worker, name="kai-email-outbox", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 10) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return True
            self._stop_event.set()
        thread.join(timeout)
        stopped = not thread.is_alive()
        if stopped:
            with self._lock:
                if self._thread is thread:
                    self._thread = None
        return stopped

    def _worker(self) -> None:
        deliver_pending()
        while not self._stop_event.wait(settings.EMAIL_OUTBOX_POLL_SECONDS):
            deliver_pending()


email_scheduler = EmailScheduler()
