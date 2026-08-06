import re
import hashlib
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List, Optional

import pymupdf4llm

from sentence_transformers import SentenceTransformer

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.full_model import Document, RagChunkORM
from db.base import Base

from ingestion.extract_metadata import extract_ollama_metadata
from ingestion.openAPI_extract import safe_extract_ai_metadata
from schemas.metadata_schema import TourismMetadata


# =========================================================
# CONFIG
# =========================================================

DATABASE_URL = (
    "postgresql+psycopg2://postgres:minhtri123@localhost:5432/travel_rag"
)

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

CHUNK_SIZE_WORDS = 180
CHUNK_OVERLAP_WORDS = 40

KEEP_PICTURE_TEXT = True
MIN_PICTURE_TEXT_CHARS = 80
SEPARATE_PICTURE_TEXT = True

SOURCE_TYPE = "tourism_guide"
LANGUAGE = "english"


# =========================================================
# DATABASE
# =========================================================

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)


# =========================================================
# EMBEDDING MODEL
# =========================================================



# =========================================================
# MARKDOWN CLEANING
# =========================================================

def remove_repeated_short_lines(
    md: str,
    min_repeat: int = 3,
    max_len: int = 80,
) -> str:
    """
    Remove repeated footer/header-like lines.

    Safety:
    - Keep Markdown headings
    - Keep bullet lines
    - Keep numbered list lines
    """

    if not md:
        return ""

    lines = md.splitlines()
    normalized_lines = [line.strip() for line in lines if line.strip()]
    counts = Counter(normalized_lines)

    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append(line)
            continue

        if (
            stripped.startswith("#")
            or stripped.startswith("- ")
            or re.match(r"^\d+\.", stripped)
        ):
            cleaned_lines.append(line)
            continue

        if len(stripped) <= max_len and counts[stripped] >= min_repeat:
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def clean_picture_blocks(
    md: str,
    keep_picture_text: bool = True,
    min_picture_text_chars: int = 80,
    separate_picture_text: bool = True,
) -> str:
    """
    Handle pymupdf4llm picture OCR blocks.

    Logic:
    - Remove short OCR blocks because they often pollute nearby chunks.
    - Keep longer useful OCR blocks separately under "### Image OCR Text".
    """

    if not md:
        return ""

    block_pattern = re.compile(
        r"""
        \s*
        \*{0,2}\s*-{2,}\s*Start\ of\ picture\ text\s*-{2,}\s*\*{0,2}
        \s*
        (.*?)
        \s*
        \*{0,2}\s*-{2,}\s*End\ of\ picture\ text\s*-{2,}\s*\*{0,2}
        \s*
        """,
        flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    def replace_picture_block(match: re.Match) -> str:
        picture_text = match.group(1).strip()

        picture_text = re.sub(r"\n{3,}", "\n\n", picture_text)
        picture_text = "\n".join(
            line.strip()
            for line in picture_text.splitlines()
            if line.strip()
        )

        flat_text = re.sub(r"\s+", " ", picture_text).strip()

        if not keep_picture_text:
            return "\n"

        if len(flat_text) < min_picture_text_chars:
            return "\n"

        alpha_count = sum(ch.isalpha() for ch in flat_text)
        alpha_ratio = alpha_count / max(len(flat_text), 1)

        if alpha_ratio < 0.35:
            return "\n"

        if separate_picture_text:
            return f"\n\n### Image OCR Text\n\n{picture_text}\n\n"

        return f"\n\n{picture_text}\n\n"

    md = block_pattern.sub(replace_picture_block, md)

    md = re.sub(
        r"(?im)^\s*\*{0,2}\s*-{2,}\s*Start of picture text\s*-{2,}\s*\*{0,2}\s*$",
        "",
        md,
    )

    md = re.sub(
        r"(?im)^\s*\*{0,2}\s*-{2,}\s*End of picture text\s*-{2,}\s*\*{0,2}\s*$",
        "",
        md,
    )

    return md


def clean_markdown_general(
    md: str,
    keep_picture_text: bool = True,
    min_picture_text_chars: int = 80,
    separate_picture_text: bool = True,
) -> str:
    """
    General Markdown cleaner for PDF-to-Markdown output.
    """

    if not md:
        return ""

    md = md.replace("\r\n", "\n").replace("\r", "\n")

    md = re.sub(
        r"<br\s*/?>",
        "\n",
        md,
        flags=re.IGNORECASE,
    )

    md = re.sub(
        r"(?im)^\s*\*{0,2}\s*==>\s*picture\b.*?<==\s*\*{0,2}\s*$",
        "",
        md,
    )

    md = clean_picture_blocks(
        md,
        keep_picture_text=keep_picture_text,
        min_picture_text_chars=min_picture_text_chars,
        separate_picture_text=separate_picture_text,
    )

    md = re.sub(
        r"!\[[^\]]*\]\([^)]+\)",
        "",
        md,
    )

    md = re.sub(
        r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*)?>",
        "",
        md,
    )

    md = re.sub(
        r"(?m)^(#{1,6})\s*\*\*(.*?)\*\*\s*$",
        r"\1 \2",
        md,
    )

    md = re.sub(
        r"(?m)^(#{1,6})([^\s#])",
        r"\1 \2",
        md,
    )

    md = re.sub(
        r"(?m)^(#{1,6}\s+[^\n*]{3,100})\*\*(.+?)\*\*\s*$",
        r"\1\n\n\2",
        md,
    )

    md = re.sub(
        r"([a-z0-9.,;:!?])\s*\*\*([A-ZÀ-Ỹ][A-Za-zÀ-ỹ0-9&,'’() /-]{2,80})\*\*\s+",
        r"\1\n\n## \2\n\n",
        md,
    )

    md = re.sub(
        r"(?m)^\s*\*\*([A-ZÀ-Ỹ][^*\n]{2,100})\*\*\s*$",
        r"## \1",
        md,
    )

    md = re.sub(r"\*\*(.*?)\*\*", r"\1", md)
    md = re.sub(r"__(.*?)__", r"\1", md)

    md = re.sub(
        r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)",
        r"\1",
        md,
    )

    md = re.sub(
        r"(?<!\w)_(?!_)(.*?)(?<!_)_(?!\w)",
        r"\1",
        md,
    )

    md = re.sub(r"~~(.*?)~~", r"\1", md)

    md = re.sub(
        r"(?m)^\s*-?\s*(\d{1,2})\s*([A-ZÀ-Ỹ][^\n]{2,100}?)\s+-\s+",
        r"\1. \2 - ",
        md,
    )

    md = re.sub(
        r"(?m)^\s*(\d{1,2})\s+([A-ZÀ-Ỹ][^\n]+)$",
        r"\1. \2",
        md,
    )

    md = re.sub(r"\s+([.,;:!?])", r"\1", md)
    md = re.sub(r"[ \t]{2,}", " ", md)

    md = re.sub(
        r"(?m)^\s*[-•♦]\s*",
        "- ",
        md,
    )

    md = remove_repeated_short_lines(md)

    md = re.sub(
        r"(?m)^#{1,6}\s*$",
        "",
        md,
    )

    md = "\n".join(line.rstrip() for line in md.splitlines())

    md = re.sub(r"\n{3,}", "\n\n", md)

    return md.strip()


def reduce_useless_info(md: str) -> str:
    """
    Conservative useless-info remover.
    Do not delete aggressively before RAG.
    """

    if not md:
        return ""

    useless_patterns = [
        r"^page\s+\d+(\s+of\s+\d+)?$",
        r"^\d+\s*/\s*\d+$",
        r"^copyright\b",
        r"^all rights reserved\b",
        r"^printed in\b",
        r"^downloaded from\b",
        r"^follow us\b",
        r"^visit us\b",
        r"^click here\b",
        r"^back to top$",
    ]

    cleaned_lines = []

    for line in md.splitlines():
        stripped = line.strip()
        lower = stripped.lower()

        if not stripped:
            cleaned_lines.append(line)
            continue

        if (
            stripped.startswith("#")
            or stripped.startswith("- ")
            or re.match(r"^\d+\.", stripped)
        ):
            cleaned_lines.append(line)
            continue

        if re.fullmatch(r"\d{1,4}", stripped):
            continue

        should_remove = False

        for pattern in useless_patterns:
            if re.search(pattern, lower):
                should_remove = True
                break

        if should_remove:
            continue

        cleaned_lines.append(line)

    md = "\n".join(cleaned_lines)
    md = re.sub(r"\n{3,}", "\n\n", md)

    return md.strip()


# =========================================================
# CHUNKING
# =========================================================

def normalize_for_hash(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_hash(text: str) -> str:
    normalized = normalize_for_hash(text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def is_bad_chunk(text: str, min_chars: int = 120) -> bool:
    stripped = text.strip()

    if not stripped:
        return True

    if len(stripped) < min_chars:
        return True

    alpha_count = sum(ch.isalpha() for ch in stripped)
    alpha_ratio = alpha_count / max(len(stripped), 1)

    if alpha_ratio < 0.35:
        return True

    return False


def split_markdown_sections(md_text: str) -> List[Dict[str, Any]]:
    """
    Split Markdown into heading-aware sections.
    Keeps h1, h2, h3, h4 metadata.
    """

    heading_pattern = re.compile(r"^(#{1,6})\s+(.*)$")

    sections = []
    header_stack: Dict[int, str] = {}

    current_lines: List[str] = []
    current_metadata: Dict[str, str] = {}

    def flush_current_section() -> None:
        nonlocal current_lines, current_metadata

        content = "\n".join(current_lines).strip()

        if content:
            heading = None

            for level in range(6, 0, -1):
                key = f"h{level}"
                if key in current_metadata:
                    heading = current_metadata[key]
                    break

            sections.append(
                {
                    "content": content,
                    "header_metadata": dict(current_metadata),
                    "section_heading": heading,
                }
            )

        current_lines = []

    for line in md_text.splitlines():
        match = heading_pattern.match(line.strip())

        if match:
            flush_current_section()

            level = len(match.group(1))
            title = match.group(2).strip()

            for existing_level in list(header_stack.keys()):
                if existing_level >= level:
                    del header_stack[existing_level]

            header_stack[level] = title

            current_metadata = {
                f"h{key}": value
                for key, value in sorted(header_stack.items())
            }

            current_lines.append(line)

        else:
            current_lines.append(line)

    flush_current_section()

    return sections


def chunk_text_by_words(
    text: str,
    max_words: int = 180,
    overlap: int = 40,
) -> List[str]:
    """
    Word-based chunker with overlap.
    Good enough for cleaned tourism guide text.
    """

    words = text.split()

    if not words:
        return []

    if len(words) <= max_words:
        return [" ".join(words)]

    chunks = []
    start = 0

    while start < len(words):
        end = start + max_words
        chunk_words = words[start:end]

        chunks.append(" ".join(chunk_words))

        if end >= len(words):
            break

        start = max(end - overlap, start + 1)

    return chunks


def split_markdown_for_rag(
    md_text: str,
    source_file: str = "",
    chunk_size: int = CHUNK_SIZE_WORDS,
    chunk_overlap: int = CHUNK_OVERLAP_WORDS,
) -> List[Dict[str, Any]]:
    """
    Split cleaned Markdown into RAG-ready chunks.
    """

    sections = split_markdown_sections(md_text)

    chunks: List[Dict[str, Any]] = []
    seen_hashes = set()

    for section in sections:
        section_content = section["content"]
        header_metadata = section["header_metadata"]
        section_heading = section["section_heading"]

        raw_chunks = chunk_text_by_words(
            section_content,
            max_words=chunk_size,
            overlap=chunk_overlap,
        )

        for raw_chunk in raw_chunks:
            chunk = raw_chunk.strip()

            if is_bad_chunk(chunk):
                continue

            chunk_hash = make_hash(chunk)

            if chunk_hash in seen_hashes:
                continue

            seen_hashes.add(chunk_hash)

            chunks.append(
                {
                    "content": chunk,
                    "source_file": source_file,
                    "chunk_index": len(chunks),
                    "chunk_hash": chunk_hash,
                    "word_count": len(chunk.split()),
                    "char_count": len(chunk),
                    "section_heading": section_heading,
                    "header_metadata": header_metadata,
                }
            )

    return chunks


def prepare_markdown_for_rag(
    raw_md: str,
    source_file: str = "",
    chunk_size: int = CHUNK_SIZE_WORDS,
    chunk_overlap: int = CHUNK_OVERLAP_WORDS,
) -> Dict[str, Any]:
    """
    Full Markdown preprocessing pipeline.
    """

    clean_md = clean_markdown_general(
        raw_md,
        keep_picture_text=KEEP_PICTURE_TEXT,
        min_picture_text_chars=MIN_PICTURE_TEXT_CHARS,
        separate_picture_text=SEPARATE_PICTURE_TEXT,
    )

    chunks = split_markdown_for_rag(
        clean_md,
        source_file=source_file,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return {
        "cleaned_markdown": clean_md,
        "chunks": chunks,
    }


# =========================================================
# AI METADATA
# =========================================================

def fallback_metadata(
    chunk_text: str,
    reason: str,
) -> TourismMetadata:
    """
    Fallback metadata when LLM extraction fails.
    """

    return TourismMetadata(
        country="Vietnam",
        city=None,
        province=None,
        place_name=None,
        place_type=None,
        ai_tags=[],
        ai_activities=[],
        ai_travel_styles=[],
        ai_suitable_for=[],
        chunk_topic=None,
        summary=chunk_text[:300],
        confidence=0.0,
        reasoning=reason,
    )


# def safe_extract_ai_metadata(chunk_text: str,  context_text: str = "") -> TourismMetadata:
#     """
#     Extract metadata safely.
#     Pipeline should continue even if Ollama fails for one chunk.
#     """

#     try:
#         return extract_ollama_metadata(chunk_text, context_text=context_text)

#     except Exception as e:
#         print("[AI METADATA FAILED]")
#         print(e)

#         return fallback_metadata(
#             chunk_text=chunk_text,
#             reason=f"AI metadata extraction failed: {e}",
#         )


def metadata_to_dict(metadata: TourismMetadata) -> Dict[str, Any]:
    """
    Compatible with Pydantic v1 and v2.
    """

    if hasattr(metadata, "model_dump"):
        return metadata.model_dump()

    if hasattr(metadata, "dict"):
        return metadata.dict()

    return {}


def safe_list(value: Optional[Any]) -> List[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def safe_float(value: Optional[Any], default: float = 0.0) -> float:
    try:
        if value is None:
            return default

        return float(value)

    except Exception:
        return default


# =========================================================
# EMBEDDINGS
# =========================================================
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

def generate_embedding(text: str) -> List[float]:
    """
    Generate normalized embedding.
    all-MiniLM-L6-v2 returns 384 dimensions.
    """

    vector = embedding_model.encode(
        text,
        normalize_embeddings=True,
    )

    return vector.tolist()


# =========================================================
# MAIN PIPELINE
# =========================================================

def process_pdf(pdf_path: str) -> None:
    """
    PDF -> Markdown -> Clean -> Chunk -> AI metadata -> Embedding -> PostgreSQL
    """

    db = SessionLocal()

    document_id = None
    inserted_count = 0
    failed_count = 0

    try:
        pdf_path_obj = Path(pdf_path)

        print("[1] PDF to Markdown")
        raw_markdown = pymupdf4llm.to_markdown(str(pdf_path_obj))

        print("[2] Clean + reduce + chunk")
        prepared = prepare_markdown_for_rag(
            raw_md=raw_markdown,
            source_file=str(pdf_path_obj),
            chunk_size=CHUNK_SIZE_WORDS,
            chunk_overlap=CHUNK_OVERLAP_WORDS,
        )

        cleaned_markdown = prepared["cleaned_markdown"]
        chunks = prepared["chunks"]

        print(f"Prepared chunks: {len(chunks)}")

        print("[3] Save document")

        document = Document(
            title=pdf_path_obj.stem,
            document_type="pdf",
            source_type=SOURCE_TYPE,
            source_file=str(pdf_path_obj),
            raw_content=raw_markdown,
            cleaned_markdown=cleaned_markdown,
            ingestion_status="processing",
            language=LANGUAGE,
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        document_id = document.id

        print(f"Document ID: {document_id}")

        print("[4] Process chunks")

        previous_summary = None
        previous_heading = None
        previous_city = None
        previous_country = None
        
        for chunk_data in chunks:
            chunk_index = chunk_data["chunk_index"]
            chunk_text = chunk_data["content"]
            section_heading = chunk_data.get("section_heading")
            header_metadata = chunk_data.get("header_metadata", {})
            context_text = f"""
                Document title: {Path(pdf_path).stem}
                Source file: {pdf_path}

                Current section heading: {section_heading}
                Header metadata: {header_metadata}

                Previous chunk summary: {previous_summary}
                Previous heading: {previous_heading}
                Previous country: {previous_country}
                Previous city: {previous_city}
                """.strip()
            try:
                print(f"Processing chunk {chunk_index + 1}/{len(chunks)}")

                metadata = safe_extract_ai_metadata(chunk_text, context_text=context_text)
                previous_summary = metadata.summary
                previous_heading = section_heading
                previous_city = metadata.city or previous_city
                previous_country = metadata.country or previous_country
                metadata_dict = metadata_to_dict(metadata)

                embedding = generate_embedding(chunk_text)

                ai_metadata = {
                    **metadata_dict,
                    "chunk_hash": chunk_data["chunk_hash"],
                    "char_count": chunk_data["char_count"],
                    "header_metadata": chunk_data["header_metadata"],
                    "embedding_dim": len(embedding),
                }

                chunk_row = RagChunkORM(
                    document_id=document_id,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    word_count=chunk_data["word_count"],
                    section_heading=chunk_data["section_heading"],

                    ai_topic=metadata.chunk_topic,

                    country=metadata.country,
                    city=metadata.city,
                    province=metadata.province,
                    place_name=metadata.place_name,
                    place_type=metadata.place_type,

                    ai_summary=metadata.summary,
                    ai_tags=safe_list(metadata.ai_tags),
                    ai_activities=safe_list(metadata.ai_activities),
                    ai_travel_styles=safe_list(metadata.ai_travel_styles),
                    ai_suitable_for=safe_list(metadata.ai_suitable_for),

                    ai_metadata=ai_metadata,
                    metadata_source="ai_inferred",
                    metadata_confidence=safe_float(metadata.confidence),

                    embedding=embedding,
                    embedding_model=EMBEDDING_MODEL_NAME,
                )

                db.add(chunk_row)
                db.commit()

                inserted_count += 1

                print(f"[OK] Chunk {chunk_index}")

            except Exception as e:
                db.rollback()

                failed_count += 1

                print(f"[FAILED CHUNK {chunk_index}]")
                print(e)

                continue

        print("[5] Finalize document")

        document = db.get(Document, document_id)

        if document:
            document.chunk_count = inserted_count

            if failed_count == 0:
                document.ingestion_status = "completed"
            else:
                document.ingestion_status = "completed_with_errors"

            db.commit()

        print(f"Inserted chunks: {inserted_count}")
        print(f"Failed chunks: {failed_count}")

    except Exception as e:
        db.rollback()

        print("[PIPELINE FAILED]")
        print(e)

        if document_id is not None:
            try:
                document = db.get(Document, document_id)

                if document:
                    document.ingestion_status = "failed"
                    db.commit()

            except Exception:
                db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    process_pdf(
        "pdfs/danang_guide.pdf"
    )