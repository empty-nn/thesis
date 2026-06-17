import hashlib
from pathlib import Path
from urllib.parse import urlparse

from schemas.data_building_schema import ExtractionInfo
from db.full_model import Document
from db.session import get_db
from sqlalchemy.orm import Session

def file_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(block)

    return hasher.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

def is_url(source_location: str) -> bool:
    """Check whether source location is an HTTP or HTTPS URL."""
    parsed = urlparse(source_location)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_source_location(source_location: str) -> str:
    """Normalize file path or URL before saving/checking."""
    source_location = str(source_location).strip()

    if is_url(source_location):
        return source_location

    return Path(source_location).as_posix()


def get_file_hash_if_local_file(source_location: str) -> str | None:
    """Return file hash only when source location is a local file."""
    if is_url(source_location):
        return None

    file_path = Path(source_location)

    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_location}")

    return file_sha256(file_path)


def find_existing_document(
    db: Session,
    source_location: str,
    file_hash: str | None,
) -> Document | None:
    """Find existing document by file hash for files or source URL for web pages."""
    if file_hash:
        return (
            db.query(Document)
            .filter(Document.file_hash == file_hash)
            .first()
        )

    return (
        db.query(Document)
        .filter(Document.source_location == source_location)
        .first()
    )


def save_extraction_info_service(
    db: Session,
    request: ExtractionInfo,
) -> Document:
    """Save extraction info or return existing document if already saved."""
    source_location = normalize_source_location(request.source_location)

    file_hash = get_file_hash_if_local_file(source_location)

    existing_document = find_existing_document(
        db=db,
        source_location=source_location,
        file_hash=file_hash,
    )

    if existing_document:
        return existing_document

    document = Document(
        document_type=request.document_type,
        source_location=source_location,
        file_hash=file_hash,
        raw_markdown=request.raw_markdown,
        extraction_method=request.extraction_method,
        ingestion_status="extraction",
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document