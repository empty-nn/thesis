"""Authenticated, preview-first knowledge base construction API."""
import os
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from db.full_model import Document, UserORM
from db.session import get_db
from schemas.data_building import CleanRequest, ExtractRequest, PrepareRequest, StoreRequest
from services.data_building import extract_pdf, extract_url, prepare_chunks, store_document
from data_building.clean_markdown.clean_markdown import clean_markdown_general
from services.session_auth import require_session_user_id

router = APIRouter(prefix="/data-building", tags=["data-building"],
                   dependencies=[Depends(require_session_user_id)])


def can_store(request: Request, db: Session) -> bool:
    user = db.get(UserORM, require_session_user_id(request))
    admins = {value.strip().lower() for value in
              os.getenv("DATA_BUILDING_ADMIN_EMAILS", "").split(",") if value.strip()}
    return bool(user and user.is_active and user.email and user.email.lower() in admins)


@router.get("/capabilities")
def capabilities(request: Request, db: Session = Depends(get_db)):
    return {"can_store": can_store(request, db), "max_pdf_bytes": 8 * 1024 * 1024,
            "metadata_mode": "manual", "max_text_chars": 200000}


@router.post("/extract-url")
def extract_html(payload: ExtractRequest):
    return extract_url(payload.url, payload.method)


@router.post("/extract-pdf")
def extract_upload(file: UploadFile = File(...)):
    try:
        content = file.file.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(413, "PDF must be no larger than 8 MB.")
        return extract_pdf(content, file.filename or "document.pdf")
    finally:
        file.file.close()


@router.post("/clean")
def clean(payload: CleanRequest):
    result = clean_markdown_general(payload.markdown, keep_picture_text=payload.keep_picture_text,
        min_picture_text_chars=payload.min_picture_text_chars,
        separate_picture_text=payload.separate_picture_text)
    if not result.strip():
        raise HTTPException(422, "Cleaning left no readable text. Please edit the extraction.")
    return {"cleaned_markdown": result}


@router.post("/prepare")
def prepare(payload: PrepareRequest):
    return {"chunks": prepare_chunks(payload), "metadata_mode": "manual"}


@router.post("/store")
def store(payload: StoreRequest, request: Request, db: Session = Depends(get_db)):
    if not can_store(request, db):
        raise HTTPException(403, "Only configured knowledge-base administrators can save documents.")
    checks = [Document.source_location == payload.source_location]
    if payload.file_hash:
        checks.append(Document.file_hash == payload.file_hash)
    existing = db.scalar(select(Document).where(
        Document.document_type == payload.document_type, or_(*checks)))
    if existing:
        raise HTTPException(409, "This source already exists. Existing evidence has not been changed.")
    try:
        return store_document(db, payload, require_session_user_id(request))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This source already exists. Existing evidence has not been changed.")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "Document could not be saved. No partial changes were committed.")
