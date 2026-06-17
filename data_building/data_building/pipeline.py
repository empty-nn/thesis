from dataclasses import asdict
import time
from pathlib import Path
from typing import Any, Dict, List

import pymupdf4llm
from data_building.chunking.markdown_chunker import MarkdownChunker
from data_building.embedding.generate_embedding import generate_embedding
from data_building.json_helper import hash_file, metadata_to_dict, now_iso, safe_filename, safe_float, safe_list, save_json
from data_building.clean_markdown.clean_markdown import clean_markdown_general
from data_building.extract_metadata import safe_extract_ai_metadata
# =========================================================
# CONFIG
# =========================================================


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE_WORDS = 180
CHUNK_OVERLAP_WORDS = 40

KEEP_PICTURE_TEXT = True
MIN_PICTURE_TEXT_CHARS = 80
SEPARATE_PICTURE_TEXT = True

SOURCE_TYPE = "tourism_guide"
LANGUAGE = "english"

INPUT_PDF_DIR = "pdfs"
OUTPUT_JSON_DIR = "json_output"

INCLUDE_EMBEDDING = True


def process_pdf_to_json(
    pdf_path: str | Path,
    output_dir: str | Path = OUTPUT_JSON_DIR,
) -> Dict[str, Any]:
    """
    PDF -> Markdown -> Clean -> Chunk -> AI metadata -> Embedding -> JSON
    """

    start_time = time.perf_counter()

    pdf_path_obj = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path_obj.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path_obj}")

    if pdf_path_obj.suffix.lower() != ".pdf":
        raise ValueError(f"File must be a PDF: {pdf_path_obj}")

    file_hash = hash_file(pdf_path_obj)
    source_id = file_hash[:16]

    safe_title = safe_filename(pdf_path_obj.stem)
    output_file = output_dir / f"{safe_title}_{source_id}.json"

    inserted_count = 0
    failed_count = 0

    try:
        print("\n===================================================")
        print(f"Processing PDF: {pdf_path_obj}")
        print("===================================================")

        print("[1] PDF to Markdown")
        raw_markdown = pymupdf4llm.to_markdown(str(pdf_path_obj))

        print("[2] Clean")
        cleaned_markdown = clean_markdown_general(raw_markdown)

        print("[3] Chunk")
        chunker = MarkdownChunker()

        prepared = chunker.chunk(cleaned_markdown)

        prepared_dict = asdict(prepared)
        chunks = prepared_dict["chunks"]
        print(f"Prepared chunks: {len(chunks)}")

        document_json: Dict[str, Any] = {
            "sourceId": source_id,
            "document": {
                "title": pdf_path_obj.stem,
                "documentType": "pdf",
                "sourceType": SOURCE_TYPE,
                "sourceFile": pdf_path_obj.as_posix(),
                "fileHash": file_hash,
                "rawContent": raw_markdown,
                "cleanedMarkdown": cleaned_markdown,
                "ingestionStatus": "processing",
                "language": LANGUAGE,
                "chunkCount": 0,
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
            },
            "chunks": [],
            "stats": {
                "preparedChunkCount": len(chunks),
                "insertedChunkCount": 0,
                "failedChunkCount": 0,
                "durationSeconds": None,
            },
            "success": True,
            "error": None,
        }

        print("[3] Process chunks")

        previous_summary = None
        previous_heading = None
        previous_city = None
        previous_country = None

        for chunk_data in chunks:
            chunk_index = chunk_data['chunk_index']
            chunk_text = chunk_data['chunk_text']
            section_heading = chunk_data['section_heading']
            header_metadata = chunk_data['header_metadata']

            context_text = f"""
                Document title: {pdf_path_obj.stem}
                Source file: {pdf_path_obj.as_posix()}

                Current section heading: {section_heading}
                Header metadata: {header_metadata}

                Previous chunk summary: {previous_summary}
                Previous heading: {previous_heading}
                Previous country: {previous_country}
                Previous city: {previous_city}
            """.strip()

            try:
                print(f"Processing chunk {chunk_index + 1}/{len(chunks)}")

                metadata = safe_extract_ai_metadata(
                    chunk_text=chunk_text,
                    context_text=context_text,
                )
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
                    "header_metadata": header_metadata,
                    "embedding_dim": len(embedding) if embedding else 0,
                }

                chunk_json = {
                    "chunkId": f"{source_id}_{chunk_index:04d}",
                    "sourceId": source_id,
                    "chunkIndex": chunk_index,
                    "chunkText": chunk_text,
                    "chunkHash": chunk_data['chunk_hash'],
                    "wordCount": chunk_data['word_count'],
                    "charCount": chunk_data['char_count'],
                    "sectionHeading": section_heading,
                    "headerMetadata": header_metadata,

                    "aiTopic": metadata.chunk_topic,

                    "country": metadata.country,
                    "city": metadata.city,
                    "province": metadata.province,
                    "placeName": metadata.place_name,
                    "placeType": metadata.place_type,

                    "aiSummary": metadata.summary,
                    "aiTags": safe_list(metadata.ai_tags),
                    "aiActivities": safe_list(metadata.ai_activities),
                    "aiTravelStyles": safe_list(metadata.ai_travel_styles),
                    "aiSuitableFor": safe_list(metadata.ai_suitable_for),

                    "aiMetadata": ai_metadata,
                    "metadataSource": "ai_inferred",
                    "metadataConfidence": safe_float(metadata.confidence),

                    "embedding": embedding,
                    "embeddingModel": EMBEDDING_MODEL_NAME if embedding else None,

                    "success": True,
                    "error": None,
                }

                document_json["chunks"].append(chunk_json)

                inserted_count += 1

                print(f"[OK] Chunk {chunk_index}")

            except Exception as e:
                failed_count += 1

                print(f"[FAILED CHUNK {chunk_index}]")
                print(e)

                failed_chunk_json = {
                    "chunkId": f"{source_id}_{chunk_index:04d}",
                    "sourceId": source_id,
                    "chunkIndex": chunk_index,
                    "chunkText": chunk_text,
                    "chunkHash": chunk_data.get("chunk_hash"),
                    "wordCount": chunk_data.get("word_count"),
                    "charCount": chunk_data.get("char_count"),
                    "sectionHeading": section_heading,
                    "headerMetadata": header_metadata,
                    "success": False,
                    "error": str(e),
                }

                document_json["chunks"].append(failed_chunk_json)

                continue

        print("[4] Finalize JSON")

        duration = time.perf_counter() - start_time

        if failed_count == 0:
            ingestion_status = "completed"
        else:
            ingestion_status = "completed_with_errors"

        document_json["document"]["ingestionStatus"] = ingestion_status
        document_json["document"]["chunkCount"] = inserted_count
        document_json["document"]["updatedAt"] = now_iso()

        document_json["stats"]["insertedChunkCount"] = inserted_count
        document_json["stats"]["failedChunkCount"] = failed_count
        document_json["stats"]["durationSeconds"] = duration

        save_json(document_json, output_file)

        print(f"Saved JSON: {output_file}")
        print(f"Inserted chunks: {inserted_count}")
        print(f"Failed chunks: {failed_count}")

        return document_json

    except Exception as e:
        duration = time.perf_counter() - start_time

        print("[PIPELINE FAILED]")
        print(e)

        failed_json = {
            "sourceId": source_id,
            "document": {
                "title": pdf_path_obj.stem,
                "documentType": "pdf",
                "sourceType": SOURCE_TYPE,
                "sourceFile": pdf_path_obj.as_posix(),
                "fileHash": file_hash,
                "rawContent": "",
                "cleanedMarkdown": "",
                "ingestionStatus": "failed",
                "language": LANGUAGE,
                "chunkCount": 0,
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
            },
            "chunks": [],
            "stats": {
                "preparedChunkCount": 0,
                "insertedChunkCount": 0,
                "failedChunkCount": 0,
                "durationSeconds": duration,
            },
            "success": False,
            "error": str(e),
        }

        failed_output_file = output_dir / f"{safe_title}_{source_id}_failed.json"
        save_json(failed_json, failed_output_file)

        print(f"Saved failed JSON: {failed_output_file}")

        return failed_json


def process_pdf_folder_to_json(
    input_dir: str | Path = INPUT_PDF_DIR,
    output_dir: str | Path = OUTPUT_JSON_DIR,
    recursive: bool = True,
) -> List[Dict[str, Any]]:
    """
    Loop through a folder and process all PDFs into JSON files.
    """

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

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
    print(f"Output folder: {output_dir}")
    print(f"Found PDFs: {len(pdf_files)}")
    print("===================================================")

    results = []

    for pdf_file in pdf_files:
        result = process_pdf_to_json(
            pdf_path=pdf_file,
            output_dir=output_dir,
        )

        results.append(
            {
                "sourceId": result.get("sourceId"),
                "title": result.get("document", {}).get("title"),
                "sourceFile": result.get("document", {}).get("sourceFile"),
                "ingestionStatus": result.get("document", {}).get("ingestionStatus"),
                "chunkCount": result.get("document", {}).get("chunkCount"),
                "success": result.get("success"),
                "error": result.get("error"),
            }
        )

    completed_count = sum(
        1
        for item in results
        if item.get("ingestionStatus") == "completed"
    )

    completed_with_errors_count = sum(
        1
        for item in results
        if item.get("ingestionStatus") == "completed_with_errors"
    )

    failed_count = sum(
        1
        for item in results
        if item.get("ingestionStatus") == "failed"
    )

    summary = {
        "inputDir": input_dir.as_posix(),
        "outputDir": output_dir.as_posix(),
        "totalFiles": len(pdf_files),
        "completedCount": completed_count,
        "completedWithErrorsCount": completed_with_errors_count,
        "failedCount": failed_count,
        "results": results,
        "createdAt": now_iso(),
    }

    summary_file = output_dir / "_summary.json"
    save_json(summary, summary_file)

    print("\n===================================================")
    print("Folder processing completed")
    print(f"Summary saved: {summary_file}")
    print(f"Completed: {completed_count}")
    print(f"Completed with errors: {completed_with_errors_count}")
    print(f"Failed: {failed_count}")
    print("===================================================")

    return results


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    process_pdf_folder_to_json(
        input_dir=r"C:\Users\RUY6HC\Desktop\hehe\test-main\be\pdfs",
        output_dir=r"C:\Users\RUY6HC\Desktop\hehe\test-main\be\pdfs_output",
        recursive=True,
    )