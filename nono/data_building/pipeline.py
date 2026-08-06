from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List
import re
import hashlib
import traceback

from data_building.url_text import read_url_status_file, update_url_status, write_url_status_file
from data_building.loaders import fetch_html, HtmlConverter, PdfConverter
from db.session import SessionLocal
from db.full_model import Document, RagChunkORM

from data_building.chunking.markdown_chunker import MarkdownChunker
from data_building.clean_markdown.clean_markdown import clean_markdown_general
from data_building.embedding.generate_embedding import generate_embedding
from data_building.json_helper import hash_file, safe_list, safe_float
from data_building.extract_metadata.extract_service import process_chunks_by_batch


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
INCLUDE_EMBEDDING = True

def normalize_for_hash(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def generate_chunk_hash(text: str) -> str:
    normalized = normalize_for_hash(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def process_url_to_md(url, method):
    html_text = fetch_html(url=url, timeout=30,)

    cleaner = HtmlConverter(
        html_text=html_text,
        source_url=url,
    )

    result = cleaner.clean(method=method)
    return result.markdown

def process_pdf_to_md(file_path, method):
    converter = PdfConverter(str(file_path))
    result = converter.to_markdown(method=method)

    return result.markdown

def process_to_db(
    extract_method,
    pdf_path: str | Path = None,
    url: str = None,
) -> Dict[str, Any]:
    """
    PDF -> Markdown -> Clean -> Chunk -> Batch AI metadata -> Embedding -> PostgreSQL
    """
    db = SessionLocal()

    file_hash = None
    try:
        print("\n===================================================")
        print(f"Processing")
        print("===================================================")

        print("[1] PDF to Markdown")
        if pdf_path is not None:
            raw_markdown = process_pdf_to_md(pdf_path, extract_method)
            pdf_path_obj = Path(pdf_path)
            file_hash = hash_file(pdf_path_obj)
        else:
            raw_markdown = process_url_to_md(url, extract_method)

        print("[2] Clean Markdown")
        cleaned_markdown = clean_markdown_general(raw_markdown)

        print("[3] Chunk Markdown")
        chunker = MarkdownChunker()
        prepared = chunker.chunk(cleaned_markdown)

        prepared_dict = asdict(prepared)
        chunks = prepared_dict["chunks"]

        print(f"Prepared chunks: {len(chunks)}")
        print("[4] Create document row")
        source_location = url if url else str(pdf_path_obj)
        document_type = "pdf" if pdf_path is not None else "html"

        document = Document(
            document_type=document_type,
            source_location=source_location,
            file_hash=file_hash,
            raw_markdown=raw_markdown,
            cleaned_markdown=cleaned_markdown,
            ingestion_status="processing",
            extraction_method=extract_method,
            chunking_method="langchain_markdown_chunker",
            embedding_model=EMBEDDING_MODEL_NAME,
            language="english",
        )

        db.add(document)
        db.flush()

        print("[5] Batch AI metadata extraction")

        enriched_chunks = process_chunks_by_batch(chunks=chunks, batch_size=10)

        print(f"Enriched chunks: {len(enriched_chunks)}")
        print("[6] Generate embeddings and save chunks")

        for chunk in enriched_chunks:
            chunk_text = chunk["chunk_text"]

            embedding = generate_embedding(text=chunk_text, model=EMBEDDING_MODEL_NAME)

            chunk_hash = chunk.get("chunk_hash") or generate_chunk_hash(chunk_text)
            chunk_row = RagChunkORM(
                document_id=document.id,

                chunk_index=chunk["chunk_index"],
                chunk_hash=chunk_hash,
                chunk_text=chunk_text,
                word_count=chunk.get("word_count"),

                section_heading=chunk.get("section_heading"),
                page_number=chunk.get("page_number"),

                country=chunk.get("country"),
                city=chunk.get("city"),
                province=chunk.get("province"),
                place_name=chunk.get("place_name"),
                place_type=chunk.get("place_type"),

                ai_summary=chunk.get("ai_summary") or chunk.get("summary"),
                ai_topic=chunk.get("ai_topic") or chunk.get("chunk_topic"),

                ai_tags=safe_list(chunk.get("ai_tags")),
                ai_activities=safe_list(chunk.get("ai_activities")),
                ai_travel_styles=safe_list(chunk.get("ai_travel_styles")),
                ai_suitable_for=safe_list(chunk.get("ai_suitable_for")),

                ai_metadata={
                    "confidence": safe_float(chunk.get("metadata_confidence") or chunk.get("confidence")),
                    "reasoning": (chunk.get("metadata_reasoning") or chunk.get("reasoning")),
                    "header_metadata": chunk.get("header_metadata", {}),
                },

                embedding=embedding,
                embedding_model=EMBEDDING_MODEL_NAME,
            )

            db.add(chunk_row)

        document.ingestion_status = "completed"

        db.commit()
        db.refresh(document)

        print("[DONE]")

        return {
            "success": True,
            "document_id": str(document.id),
            "total_chunks": len(chunks),
            "saved_chunks": len(enriched_chunks),
        }

    except Exception as e:
        db.rollback()

        print("[PIPELINE FAILED]")
        print(e)
        traceback.print_exc()

        return {
            "success": False,
            "error": str(e),
        }

    finally:
        db.close()

def process_pdf_folder_to_db(
    input_dir: str | Path,
    recursive: bool = True,
) -> List[Dict[str, Any]]:
    input_dir = Path(input_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")

    if not input_dir.is_dir():
        raise ValueError(f"Input path must be a folder: {input_dir}")

    pdf_files = (
        sorted(input_dir.rglob("*.pdf"))
        if recursive
        else sorted(input_dir.glob("*.pdf"))
    )

    print("===================================================")
    print(f"Input folder: {input_dir}")
    print(f"Found PDFs: {len(pdf_files)}")
    print("===================================================")

    results = []

    for pdf_file in pdf_files:
        result = process_to_db(pdf_file, extract_method="pymupdf")
        results.append(result)

    return results

if __name__ == "__main__":
    process_pdf_folder_to_db(
        input_dir=r"C:\Users\RUY6HC\Desktop\hehe\test-main\be\pdfs",
        recursive=True,
    )