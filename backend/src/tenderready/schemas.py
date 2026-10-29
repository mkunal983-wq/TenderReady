from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, strict=True, extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    supplier_name: str = Field(min_length=1, max_length=200)

    @field_validator("title", "supplier_name", mode="before")
    @classmethod
    def reject_control_characters(cls, value):
        if isinstance(value, str) and any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
            raise ValueError("Control characters are not permitted.")
        return value


class WorkspaceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    supplier_name: str
    revision: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def serialize_utc(cls, value: datetime):
        # SQLite drops timezone metadata; stored timestamps are always UTC.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class WorkspaceRename(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, strict=True, extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    expected_title: str = Field(min_length=1, max_length=200)

    @field_validator("title", "expected_title", mode="before")
    @classmethod
    def validate_previous_title(cls, value):
        return WorkspaceCreate.reject_control_characters(value)


class WorkspaceDelete(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    confirm: bool
    expected_title: str = Field(min_length=1, max_length=200)

    @field_validator("confirm")
    @classmethod
    def require_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit deletion confirmation required.")
        return value
