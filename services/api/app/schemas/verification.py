from datetime import datetime

from pydantic import BaseModel, StrictBool

from app.schemas.common import OrmModel


class VerificationIn(BaseModel):
    real_name: str
    id_card: str
    sensitive_consent: StrictBool


class OcrMatchSummary(BaseModel):
    name_match: bool
    id_number_match: bool
    birth_date_match: bool
    gender_match: bool
    validity_match: bool


class OcrValidity(BaseModel):
    valid_from: str | None = None
    valid_until: str | None = None
    long_term: bool = False


class VerificationOut(OrmModel):
    id: int
    real_name: str
    id_card_masked: str | None = None
    status: str
    reject_reason: str | None = None
    front_photo: str | None = None
    back_photo: str | None = None
    ocr_status: str = "not_started"
    ocr_summary: OcrMatchSummary | None = None
    ocr_error_code: str | None = None
    ocr_updated_at: datetime | None = None
    ocr_message: str | None = None
    ocr_validity: OcrValidity | None = None
    consent_recorded: bool = False
    created_at: datetime | None = None
