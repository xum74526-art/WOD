import logging
import threading
from collections.abc import Callable

from app.config import settings
from app.db import SessionLocal
from app.news_service import sync_news


logger = logging.getLogger(__name__)


def _sync_once(stop_event: threading.Event) -> None:
    if stop_event.is_set():
        return
    db = SessionLocal()
    try:
        sync_news(db, should_stop=stop_event.is_set)
    except Exception:
        db.rollback()
        logger.exception("scheduled news synchronization failed")
    finally:
        db.close()


class NewsScheduler:
    def __init__(
        self,
        task: Callable[[threading.Event], None] = _sync_once,
        *,
        interval_seconds: float | None = None,
        enabled: Callable[[], bool] | None = None,
    ) -> None:
        self._task = task
        self._interval_seconds = interval_seconds
        self._enabled = enabled or (lambda: settings.NEWS_SYNC_ENABLED)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        with self._lock:
            if not self._enabled() or (self._thread and self._thread.is_alive()):
                return False
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._worker,
                name="kai-news-sync",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return True
            self._stop_event.set()
        thread.join(timeout if timeout is not None else settings.NEWS_SCHEDULER_STOP_TIMEOUT_SECONDS)
        stopped = not thread.is_alive()
        if stopped:
            with self._lock:
                if self._thread is thread:
                    self._thread = None
        else:
            logger.error("news scheduler did not stop before shutdown timeout")
        return stopped

    def _worker(self) -> None:
        interval = self._interval_seconds
        if interval is None:
            interval = max(60, settings.NEWS_SYNC_INTERVAL_MINUTES * 60)
        while not self._stop_event.is_set():
            self._task(self._stop_event)
            if self._stop_event.wait(interval):
                break


news_scheduler = NewsScheduler()
