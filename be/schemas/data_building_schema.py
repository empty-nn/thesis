from schemas.camel_model import CamelModel


class PdfConvertRequest(CamelModel):
    file_path: str
    method: str = "pymupdf"

class ConvertResponse(CamelModel):
    exists: bool = False
    source_id: int | None = None
    current_step: str | None = None

    document_type: str | None = None
    source_location: str | None = None
    extraction_method: str | None = None

    raw_markdown: str | None = None
    cleaned_markdown: str | None = None
    metadata: dict | None = None
    chunks: list[dict] | None = None


class HtmlUrlConvertRequest(CamelModel):
    url: str
    method: str = "trafilatura"

class ExtractionInfo(CamelModel):
    document_type: str
    source_location: str
    raw_markdown: str
    extraction_method:str

class CleanMarkdownRequest(CamelModel):
    md: str
    keep_picture_text: bool = True
    min_picture_text_chars: int = 80
    separate_picture_text: bool = True