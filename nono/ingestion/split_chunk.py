import re
import hashlib
from typing import List, Dict, Any

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .clean_markdown import clean_markdown_general

def normalize_for_dedup(text: str) -> str:
    """
    Normalize text for duplicate detection.
    """
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def text_hash(text: str) -> str:
    """
    Create stable hash for chunk deduplication.
    """
    normalized = normalize_for_dedup(text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def is_useless_line(line: str) -> bool:
    """
    Detect useless lines after Markdown cleaning.

    Designed for:
    - tourism PDF
    - brochure
    - guidebook
    - thesis RAG preprocessing
    """

    stripped = line.strip()

    if not stripped:
        return False

    lower = stripped.lower()

    # Keep Markdown structure
    if stripped.startswith("#"):
        return False

    if stripped.startswith("- "):
        return False

    if re.match(r"^\d+\.", stripped):
        return False

    # Remove page number only
    if re.fullmatch(r"\d{1,4}", stripped):
        return True

    # Remove common page markers
    if re.fullmatch(r"page\s+\d+(\s+of\s+\d+)?", lower):
        return True

    if re.fullmatch(r"\d+\s*/\s*\d+", stripped):
        return True

    # Remove common PDF/brochure noise
    useless_patterns = [
        r"^table of contents$",
        r"^contents$",
        r"^index$",
        r"^references$",
        r"^bibliography$",
        r"^copyright\b",
        r"^all rights reserved\b",
        r"^printed in\b",
        r"^downloaded from\b",
        r"^source:\s*$",
        r"^website:\s*$",
        r"^email:\s*$",
        r"^tel:\s*$",
        r"^phone:\s*$",
        r"^fax:\s*$",
        r"^follow us\b",
        r"^visit us\b",
        r"^click here\b",
        r"^back to top$",
    ]

    for pattern in useless_patterns:
        if re.search(pattern, lower):
            return True

    # Remove lines that are mostly symbols
    symbol_ratio = sum(not ch.isalnum() and not ch.isspace() for ch in stripped) / max(len(stripped), 1)
    if len(stripped) <= 40 and symbol_ratio > 0.5:
        return True

    return False


def reduce_useless_info(md: str) -> str:
    """
    Reduce useless information after clean_markdown_general().

    This is safer than using an LLM to delete text because it uses conservative rules.
    """

    if not md:
        return ""

    lines = md.splitlines()
    cleaned_lines = []

    for line in lines:
        if is_useless_line(line):
            continue

        cleaned_lines.append(line)

    md = "\n".join(cleaned_lines)

    # Remove repeated blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)

    return md.strip()


def is_bad_chunk(text: str, min_chars: int = 120) -> bool:
    """
    Filter chunks that are too weak for embedding.
    """

    stripped = text.strip()

    if not stripped:
        return True

    # Too short usually gives bad retrieval
    if len(stripped) < min_chars:
        return True

    # Too little alphabetic content
    alpha_count = sum(ch.isalpha() for ch in stripped)
    alpha_ratio = alpha_count / max(len(stripped), 1)

    if alpha_ratio < 0.35:
        return True

    # Too many URLs
    url_count = len(re.findall(r"https?://|www\.", stripped.lower()))
    if url_count >= 3:
        return True

    return False


def split_markdown_for_rag(
    md: str,
    source_file: str = "",
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
) -> List[Dict[str, Any]]:
    """
    Split cleaned Markdown into RAG chunks.

    Strategy:
    1. Split by Markdown headers first.
    2. Split large sections using RecursiveCharacterTextSplitter.
    3. Keep header metadata.
    4. Remove weak chunks.
    5. Deduplicate chunks.

    Output:
    List of dicts ready for embedding/database insert.
    """

    if not md:
        return []

    headers_to_split_on = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
        ("####", "h4"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )

    header_docs = markdown_splitter.split_text(md)

    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
            "",
        ],
    )

    final_docs: List[Document] = recursive_splitter.split_documents(header_docs)

    chunks = []
    seen_hashes = set()

    for idx, doc in enumerate(final_docs):
        content = doc.page_content.strip()

        if is_bad_chunk(content):
            continue

        h = text_hash(content)

        if h in seen_hashes:
            continue

        seen_hashes.add(h)

        metadata = dict(doc.metadata)
        metadata["source_file"] = source_file
        metadata["chunk_id"] = len(chunks)
        metadata["chunk_hash"] = h
        metadata["char_count"] = len(content)

        chunks.append(
            {
                "content": content,
                "metadata": metadata,
            }
        )

    return chunks


def prepare_markdown_for_rag(
    raw_md: str,
    source_file: str = "",
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
    keep_picture_text: bool = True,
    min_picture_text_chars: int = 80,
    separate_picture_text: bool = True,
) -> List[Dict[str, Any]]:
    """
    Full post-clean pipeline.

    Pipeline:
    raw Markdown
    -> clean Markdown
    -> reduce useless info
    -> split into RAG chunks

    Use this after:
    raw_md = pymupdf4llm.to_markdown(pdf_path)

    Requires:
    - clean_markdown_general()
    - reduce_useless_info()
    - split_markdown_for_rag()
    """

    clean_md = clean_markdown_general(
        raw_md,
        keep_picture_text=keep_picture_text,
        min_picture_text_chars=min_picture_text_chars,
        separate_picture_text=separate_picture_text,
    )

    reduced_md = reduce_useless_info(clean_md)

    chunks = split_markdown_for_rag(
        reduced_md,
        source_file=source_file,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return chunks