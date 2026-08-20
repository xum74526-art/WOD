from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ManualKycSubmitIn(BaseModel):
    verification_type: Literal["individual", "business"]
    country_code: str = Field(default="CN", pattern=r"^[A-Z]{2}$")
    legal_name: str = Field(min_length=2, max_length=128)
    identifier_type: Literal["national_id", "business_registration"]
    identifier_number: str = Field(min_length=6, max_length=64, pattern=r"^[0-9A-Za-z\-]+$")
    representative_name: str | None = Field(default=None, min_length=2, max_length=64)
    declaration_accepted: bool

    @model_validator(mode="after")
    def validate_subject(self):
        if not self.declaration_accepted:
            raise ValueError("必须确认提交的信息真实有效")
        if self.verification_type == "business":
            if self.identifier_type != "business_registration" or not self.representative_name:
                raise ValueError("企业认证必须填写统一社会信用代码和法定代表人")
        elif self.identifier_type != "national_id":
            raise ValueError("个人认证必须填写身份证件号码")
        return self


class ManualKycReviewIn(BaseModel):
    version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)


class ManualKycRejectIn(BaseModel):
    version: int = Field(ge=1)
    note: str = Field(min_length=2, max_length=1000)
