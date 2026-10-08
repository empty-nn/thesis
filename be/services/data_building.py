"""Bounded extraction and atomic ingestion, reusing the loaded embedding model."""
from dataclasses import asdict
import hashlib
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from fastapi import HTTPException
import urllib3
from data_building.chunking.markdown_chunker import MarkdownChunker
from db.full_model import Document, RagChunkORM
from schemas.data_building import PrepareRequest, StoreRequest

MAX_TEXT = 200000


def public_destination(url: str):
    """Connect to the validated IP directly, preventing DNS rebinding."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password
                or parsed.port not in {None, 80, 443}):
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = [item[4][0] for item in addresses]
        if not ips or any(not ipaddress.ip_address(ip).is_global
                          or ipaddress.ip_address(ip).is_multicast for ip in ips):
            raise ValueError()
        return parsed, host, port, ips[0]
    except (ValueError, UnicodeError, OSError):
        raise HTTPException(422, "Use a public HTTP(S) URL on port 80 or 443.")


def fetch_public_html(url: str) -> tuple[str, str]:
    deadline = time.monotonic() + 30
    for _ in range(4):
        if time.monotonic() >= deadline:
            raise HTTPException(504, "Website took too long to download.")
        parsed, host, port, ip = public_destination(url)
        pool = (urllib3.HTTPSConnectionPool(ip, port, server_hostname=host,
                    assert_hostname=host, cert_reqs="CERT_REQUIRED")
                if parsed.scheme == "https" else urllib3.HTTPConnectionPool(ip, port))
        response = None
        try:
            path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            response = pool.urlopen("GET", path, headers={
                "Host": host if port in {80, 443} else f"{host}:{port}",
                "User-Agent": "TravelGuideAssistant/1.0 (thesis research)",
                "Accept": "text/html,application/xhtml+xml",
            }, redirect=False, retries=False, preload_content=False,
                timeout=urllib3.Timeout(connect=5, read=10))
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise HTTPException(422, "Website returned an invalid redirect.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise HTTPException(422, f"Website returned HTTP {response.status}.")
            mime = response.headers.get("Content-Type", "").lower()
            if not ("text/html" in mime or "application/xhtml+xml" in mime):
                raise HTTPException(422, "URL must return an HTML page; use PDF upload for PDFs.")
            data = bytearray()
            while True:
                block = response.read(65536, decode_content=True)
                if not block:
                    break
                data.extend(block)
                if len(data) > 2 * 1024 * 1024:
                    raise HTTPException(413, "HTML page is larger than the 2 MB extraction limit.")
                if time.monotonic() > deadline:
                    raise HTTPException(504, "Website took too long to download.")
            return bytes(data).decode("utf-8", errors="replace"), url
        except urllib3.exceptions.HTTPError:
            raise HTTPException(422, "Website could not be downloaded securely. Try another public URL.")
        finally:
            if response:
                response.close()
            pool.close()
    raise HTTPException(422, "Website has too many redirects.")


def validate_extracted(markdown: str):
    if not markdown.strip():
        raise HTTPException(422, "No readable text found. Scanned PDFs need OCR before upload.")
    if len(markdown) > MAX_TEXT:
        raise HTTPException(413, "Extracted text exceeds 200,000 characters. Split the source first.")


def extract_url(url: str, method: str) -> dict:
    from bs4 import BeautifulSoup
    from markdownify import markdownify
    import trafilatura
    html, final_url = fetch_public_html(url)
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True)[:300] if soup.title else ""
    if method == "trafilatura":
        markdown = trafilatura.extract(html, url=final_url, output_format="markdown",
            include_comments=False, include_tables=True, include_links=True) or ""
    else:
        for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]):
            tag.decompose()
        markdown = markdownify(str(soup.body or soup), heading_style="ATX").strip()
    validate_extracted(markdown)
    return {"document_type": "html", "source_location": final_url,
            "extraction_method": method, "raw_markdown": markdown, "title": title,
            "file_hash": None}


def extract_pdf(content: bytes, filename: str) -> dict:
    import pymupdf
    if not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Upload a valid PDF file.")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass or pdf.page_count > 100:
                raise HTTPException(422, "Use an unencrypted PDF with at most 100 pages.")
            texts = []
            total = 0
            for index, page in enumerate(pdf):
                text = page.get_text(sort=True).strip()
                total += len(text) + 30
                if total > MAX_TEXT:
                    raise HTTPException(413, "PDF text exceeds 200,000 characters. Split it first.")
                if text:
                    texts.append(f"## Page {index + 1}\n\n{text}")
            markdown = "\n\n".join(texts)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "PDF could not be read. Check that it is not damaged.")
    validate_extracted(markdown)
    name = filename.replace("\\", "/").split("/")[-1][:200]
    return {"document_type": "pdf", "source_location": name or "document.pdf",
            "extraction_method": "pymupdf", "raw_markdown": markdown,
            "title": name, "file_hash": hashlib.sha256(content).hexdigest()}


def prepare_chunks(payload: PrepareRequest) -> list[dict]:
    result = MarkdownChunker(chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap, include_heading_context=True).chunk(payload.cleaned_markdown)
    if not result.success or not result.chunks:
        raise HTTPException(422, "No readable chunks found. Review the cleaned Markdown.")
    unique = {chunk.chunk_hash: asdict(chunk) for chunk in result.chunks}
    chunks = list(unique.values())
    if len(chunks) > 250:
        raise HTTPException(413, "At most 250 chunks per save. Split the document or increase chunk size.")
    for index, chunk in enumerate(chunks):
        chunk["chunk_index"] = index
    return chunks


def store_document(db, payload: StoreRequest, user_id: str) -> dict:
    from core.model_registry import EMBEDDING_MODEL_NAME, get_embedding_model
    chunks = prepare_chunks(payload)
    vectors = get_embedding_model().encode([chunk["chunk_text"] for chunk in chunks],
        batch_size=16, normalize_embeddings=True).tolist()
    if len(vectors) != len(chunks) or any(len(vector) != 384 for vector in vectors):
        raise ValueError("Unexpected embedding dimensions")
    metadata = payload.metadata.model_dump()
    document = Document(document_type=payload.document_type, source_location=payload.source_location,
        file_hash=payload.file_hash, raw_markdown=payload.raw_markdown,
        cleaned_markdown=payload.cleaned_markdown, ingestion_status="completed",
        extraction_method=payload.extraction_method, chunking_method="langchain_markdown_chunker",
        embedding_model=EMBEDDING_MODEL_NAME, language=metadata["language"], verified=False,
        extra_metadata={**metadata, "created_by": user_id, "metadata_source": "manual"})
    db.add(document)
    db.flush()
    for chunk, vector in zip(chunks, vectors):
        db.add(RagChunkORM(document_id=document.id, chunk_index=chunk["chunk_index"],
            chunk_hash=chunk["chunk_hash"], chunk_text=chunk["chunk_text"],
            word_count=chunk["word_count"], section_heading=chunk["section_heading"],
            country=metadata["country"] or None, city=metadata["city"] or None,
            province=metadata["province"] or None, embedding=vector,
            embedding_model=EMBEDDING_MODEL_NAME, verified=False,
            extra_metadata={"header_metadata": chunk["header_metadata"], "metadata_source": "manual"}))
    document_id = str(document.id)
    db.commit()
    return {"document_id": document_id, "saved_chunks": len(chunks), "status": "completed"}
