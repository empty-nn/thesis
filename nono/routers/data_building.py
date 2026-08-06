
from pathlib import Path
from db.full_model import Document
from ingestion.file_hash import file_sha256
from db.session import get_db
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from pydantic import BaseModel
from data_building.loaders.pdf_converter import PdfConverter
from services import HtmlConversionService
from services import PdfConversionService
from ingestion.clean_markdown import clean_markdown_general

data_building_router = APIRouter(prefix="/api", tags=["Base Data Set"])

class PdfConvertRequest(BaseModel):
    file_path: str
    method: str = "pymupdf"

class ConvertResponse(BaseModel):
    source_location: str
    extraction_method: str
    raw_markdown: str

# For later use
@data_building_router.post("/convert-pdf", response_model=ConvertResponse)
def convert_pdf(request: PdfConvertRequest):
    converter = PdfConverter(request.pdf_path)
    result = converter.to_markdown(method=request.method)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {
        "method": result.method,
        "markdown": result.markdown,
        "stats": result.stats,
    }

@data_building_router.post("/convert-pdf-upload", response_model=ConvertResponse)
async def convert_pdf_upload(
    file: UploadFile = File(...),
    method: str = Form("pymupdf"),
):
    service = PdfConversionService()

    file_path = service.save_upload_file(file)
    markdown = service.convert_to_markdown(file_path, method)

    return {
        "source_location": str(file_path),
        "extraction_method": method,
        "raw_markdown": markdown.markdown,
    }

class HtmlUrlConvertRequest(BaseModel):
    url: str
    method: str = "trafilatura"

@data_building_router.post("/convert-html-url")
async def convert_html_url(request: HtmlUrlConvertRequest):
    html_service = HtmlConversionService()
    result = html_service.convert_url_to_markdown(
        url=request.url,
        method=request.method,
    )

    return {
        "markdown": result.markdown,
        "method": result.method,
        "source_name": result.source_name,
    }

class ExtractionInfo(BaseModel):
    document_type: str
    source_location: str
    raw_markdown: str
    extraction_method:str

@data_building_router.post("/save-extraction-info")
def save_extraction_info(request: ExtractionInfo, db: Session = Depends(get_db)):
    document_type = request.document_type
    file_hash = None
    if document_type == 'pdf':
        file_hash = file_sha256(request.source_location)

    document = Document(
        document_type = document_type,
        source_location = request.source_location,
        file_hash = file_hash,
        raw_markdown = request.raw_markdown,
        extraction_method = request.extraction_method,
        ingestion_status = "extraction"
    )

    db.add(document)
    db.commit()
    db.refresh(document)
    
    return document.id

@data_building_router.post("/compare-html-methods")
async def compare_html_methods(request: HtmlUrlConvertRequest):
    html_service = HtmlConversionService()
    results = html_service.compare_url_methods(
        url=request.url,
    )

    return [
        {
            "markdown": result.markdown,
            "method": result.method,
            "source_name": result.source_name,
            "success": result.success,
            "error": result.error,
            "duration_seconds": result.duration_seconds,
            "stats": result.stats,
        }
        for result in results
    ]

class CleanMarkdownRequest(BaseModel):
    md: str
    keep_picture_text: bool = True
    min_picture_text_chars: int = 80
    separate_picture_text: bool = True

@data_building_router.post("/clean-markdown")
async def clean_markdown(request: CleanMarkdownRequest):
    return clean_markdown_general(
        request.md,
        request.keep_picture_text,
        request.min_picture_text_chars,
        request.separate_picture_text,
    )
    