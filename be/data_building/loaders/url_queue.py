
from db.full_model import URLSource, URLStatus
from db.session import SessionLocal
from sqlalchemy.sql import func

def add_url(url: str) -> URLSource:
    """Add a URL to the queue if it doesn't already exist."""
    db = SessionLocal()
    try:
        existing = db.query(URLSource).filter(URLSource.url == url).first()
        if existing:
            return existing
        src = URLSource(url=url, status=URLStatus.PENDING)
        db.add(src)
        db.commit()
        db.refresh(src)
        return src
    finally:
        db.close()

def get_next_pending() -> URLSource | None:
    """Get the oldest pending URL and mark it as processing."""
    db = SessionLocal()
    try:
        src = db.query(URLSource).filter(
            URLSource.status == URLStatus.PENDING
        ).order_by(URLSource.added_at).with_for_update(skip_locked=True).first()
        if src:
            src.status = URLStatus.PROCESSING
            db.commit()
            db.refresh(src)
        return src
    finally:
        db.close()

def mark_completed(url_source_id, document_id):
    db = SessionLocal()
    try:
        src = db.query(URLSource).get(url_source_id)
        if src:
            src.status = URLStatus.COMPLETED
            src.document_id = document_id
            src.processed_at = func.now()
            db.commit()
    finally:
        db.close()

def mark_failed(url_source_id, error_message):
    db = SessionLocal()
    try:
        src = db.query(URLSource).get(url_source_id)
        if src:
            src.status = URLStatus.FAILED
            src.error_message = error_message
            src.processed_at = func.now()
            db.commit()
    finally:
        db.close()