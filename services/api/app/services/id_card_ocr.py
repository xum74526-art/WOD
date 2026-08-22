"""Local, non-authoritative ID-card OCR pre-check.

The service deliberately keeps OCR output in memory only.  It returns boolean
comparisons and validity dates, never the raw OCR text or a full identity
number.  A successful result is only a document-data match; it is not a
government identity lookup and must not mark a user as verified.
"""

from __future__ import annotations

import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.utils.id_card_util import extract_birthday, extract_gender


OCR_STATUS_NOT_STARTED = "not_started"
OCR_STATUS_PROCESSING = "processing"
OCR_STATUS_MATCHED = "matched"
OCR_STATUS_REVIEW_REQUIRED = "review_required"
OCR_STATUS_ERROR = "error"
OCR_STATUS_UNAVAILABLE = "unavailable"

OCR_SUMMARY_KEYS = (
    "name_match",
    "id_number_match",
    "birth_date_match",
    "gender_match",
    "validity_match",
)


class LocalOcrError(RuntimeError):
    """Expected local OCR failure with a non-sensitive machine code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedFront:
    name: str | None
    id_number: str | None
    birth_date: str | None
    gender: str | None


@dataclass(frozen=True)
class ParsedBack:
    valid_from: str | None
    valid_until: str | None
    long_term: bool


@dataclass(frozen=True)
class OcrPrecheckResult:
    status: str
    summary: dict[str, bool] | None
    error_code: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    long_term: bool = False


_OCR_SEMAPHORE = threading.BoundedSemaphore(max(1, settings.ID_OCR_MAX_CONCURRENCY))


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").replace("：", ":")


def _normalized_lines(text: str) -> list[str]:
    return [_compact(line) for line in (text or "").splitlines() if _compact(line)]


def _date_string(year: str, month: str, day: str) -> str | None:
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        return None
    return parsed.isoformat()


def _labeled_value(lines: list[str], label: str, pattern: str) -> str | None:
    expression = re.compile(rf"{label}:?({pattern})")
    stop_labels = ("性别", "民族", "出生", "住址", "公民身份号码")
    for line in lines:
        match = expression.search(line)
        if not match:
            continue
        value = match.group(1)
        for stop in stop_labels:
            if stop == label:
                continue
            value = value.split(stop, 1)[0]
        return value or None
    return None


def parse_front(text: str) -> ParsedFront:
    """Extract the five relevant front-side fields without guessing OCR typos."""
    lines = _normalized_lines(text)
    compact = "".join(lines).upper()
    name = _labeled_value(lines, "姓名", r"[\u3400-\u9fff·]{2,10}")
    gender = _labeled_value(lines, "性别", r"[男女]")

    birth_match = re.search(
        r"出生(?:日期)?:?((?:18|19|20)\d{2})[年./\-](\d{1,2})[月./\-](\d{1,2})日?",
        compact,
    )
    birth_date = _date_string(*birth_match.groups()) if birth_match else None

    labeled_id = re.search(r"公民身份号码?:?(\d{17}[\dX])", compact)
    if not labeled_id:
        labeled_id = re.search(r"(?<!\d)(\d{17}[\dX])(?!\d)", compact)
    id_number = labeled_id.group(1) if labeled_id else None
    return ParsedFront(
        name=name,
        id_number=id_number,
        birth_date=birth_date,
        gender=gender,
    )


def parse_back(text: str) -> ParsedBack:
    """Extract and validate the printed ID-card validity interval."""
    compact = "".join(_normalized_lines(text))
    compact = compact.replace("—", "-").replace("–", "-").replace("~", "-").replace("～", "-")
    match = re.search(
        r"有效期限?:?"
        r"((?:19|20)\d{2})[年./\-](\d{1,2})[月./\-](\d{1,2})日?"
        r"(?:至|-)"
        r"(?:"
        r"((?:19|20)\d{2})[年./\-](\d{1,2})[月./\-](\d{1,2})日?"
        r"|(长期)"
        r")",
        compact,
    )
    if not match:
        return ParsedBack(valid_from=None, valid_until=None, long_term=False)
    valid_from = _date_string(match.group(1), match.group(2), match.group(3))
    long_term = bool(match.group(7))
    valid_until = None
    if not long_term and match.group(4):
        valid_until = _date_string(match.group(4), match.group(5), match.group(6))
    return ParsedBack(valid_from=valid_from, valid_until=valid_until, long_term=long_term)


def _run_tesseract(image_path: Path) -> str:
    command = settings.ID_OCR_TESSERACT_CMD.strip()
    if not command:
        raise LocalOcrError("engine_not_configured")
    args = [
        command,
        str(image_path),
        "stdout",
        "-l",
        settings.ID_OCR_LANGUAGES,
        "--psm",
        "6",
    ]
    try:
        completed = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            timeout=max(1.0, settings.ID_OCR_TIMEOUT_SECONDS),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise LocalOcrError("engine_unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise LocalOcrError("engine_timeout") from exc
    except OSError as exc:
        raise LocalOcrError("engine_start_failed") from exc
    if completed.returncode != 0:
        # stderr can contain paths and OCR diagnostics; intentionally discard it.
        raise LocalOcrError("engine_failed")
    output = completed.stdout[: settings.ID_OCR_MAX_OUTPUT_CHARS]
    if not output.strip():
        raise LocalOcrError("empty_output")
    return output


def _validity_matches(back: ParsedBack, *, today: date) -> bool:
    if not back.valid_from:
        return False
    try:
        valid_from = date.fromisoformat(back.valid_from)
    except ValueError:
        return False
    if valid_from > today:
        return False
    if back.long_term:
        return True
    if not back.valid_until:
        return False
    try:
        valid_until = date.fromisoformat(back.valid_until)
    except ValueError:
        return False
    return valid_from <= valid_until and valid_until >= today


def run_identity_precheck(
    front_path: Path,
    back_path: Path,
    *,
    real_name: str,
    id_number: str,
    today: date | None = None,
) -> OcrPrecheckResult:
    """OCR both sides and compare only against the submitted identity fields."""
    if not settings.ID_OCR_ENABLED:
        return OcrPrecheckResult(status=OCR_STATUS_UNAVAILABLE, summary=None, error_code="disabled")
    acquired = _OCR_SEMAPHORE.acquire(timeout=max(0.1, settings.ID_OCR_QUEUE_TIMEOUT_SECONDS))
    if not acquired:
        return OcrPrecheckResult(status=OCR_STATUS_ERROR, summary=None, error_code="queue_busy")
    try:
        front_text = _run_tesseract(front_path)
        back_text = _run_tesseract(back_path)
    except LocalOcrError as exc:
        status = OCR_STATUS_UNAVAILABLE if exc.code in {"engine_not_configured", "engine_unavailable"} else OCR_STATUS_ERROR
        return OcrPrecheckResult(status=status, summary=None, error_code=exc.code)
    finally:
        _OCR_SEMAPHORE.release()

    claimed_id = re.sub(r"\s+", "", id_number or "").upper()
    front = parse_front(front_text)
    back = parse_back(back_text)
    check_date = today or date.today()
    summary = {
        "name_match": front.name == real_name,
        "id_number_match": front.id_number == claimed_id,
        "birth_date_match": front.birth_date == extract_birthday(claimed_id),
        "gender_match": front.gender == extract_gender(claimed_id),
        "validity_match": _validity_matches(back, today=check_date),
    }
    matched = all(summary.values())
    return OcrPrecheckResult(
        status=OCR_STATUS_MATCHED if matched else OCR_STATUS_REVIEW_REQUIRED,
        summary=summary,
        error_code=None if matched else "document_data_mismatch",
        valid_from=back.valid_from,
        valid_until=back.valid_until,
        long_term=back.long_term,
    )
