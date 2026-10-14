from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Image(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    id: int | None = None
    sha256sum: str = Field(min_length=64, max_length=64)
    filepath: str
    added_at: datetime
    ocr_text: str | None = None
    embedding: list[float] | None = Field(
        default=None, min_length=1024, max_length=1024
    )


class ImageCreate(BaseModel):
    sha256sum: str = Field(min_length=64, max_length=64)
    filepath: str
    added_at: datetime
    ocr_text: str | None = None
    embedding: list[float] | None = Field(
        default=None, min_length=1024, max_length=1024
    )


class ImageUpdate(BaseModel):
    ocr_text: str | None = None
    embedding: list[float] | None = Field(
        default=None, min_length=1024, max_length=1024
    )
