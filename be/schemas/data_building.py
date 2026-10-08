from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ExtractRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    method: Literal["trafilatura", "markdownify"] = "trafilatura"


class CleanRequest(BaseModel):
    markdown: str = Field(min_length=1, max_length=200000)
    keep_picture_text: bool = True
    min_picture_text_chars: int = Field(default=80, ge=0, le=1000)
    separate_picture_text: bool = True


class SourceMetadata(BaseModel):
    title: str = Field(default="", max_length=300)
    country: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    province: str = Field(default="", max_length=100)
    language: str = Field(default="english", max_length=50)


class PrepareRequest(BaseModel):
    cleaned_markdown: str = Field(min_length=1, max_length=200000)
    chunk_size: int = Field(default=1200, ge=300, le=3000)
    chunk_overlap: int = Field(default=150, ge=0, le=500)
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Overlap must be smaller than chunk size.")
        return self


class StoreRequest(PrepareRequest):
    document_type: Literal["html", "pdf", "markdown"]
    source_location: str = Field(min_length=1, max_length=2048)
    raw_markdown: str = Field(min_length=1, max_length=200000)
    extraction_method: str = Field(min_length=1, max_length=50)
    file_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
