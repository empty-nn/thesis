import json
import hashlib
from pathlib import Path
from typing import Any, Callable
from services.clean_markdown import clean_markdown_general
from data_building.loaders import PdfConverter, HtmlConverter
from data_building.chunking import MarkdownChunker
class DataBuildingPipeline:
    def __init__(
        self,
        output_dir: str | Path,
        pdf_method: str = "pymupdf",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_method = pdf_method

    def process_pdf(self, pdf_file: str | Path) -> dict[str, Any]:
        pdf_file = Path(pdf_file)

        source_id = self._create_source_id(pdf_file.as_posix())
        file_hash = self._hash_file(pdf_file)

        converter = PdfConverter(pdf_file)
        chunker = MarkdownChunker()
        extract_result = converter.to_markdown(method=self.pdf_method)

        if not extract_result.success:
            raise RuntimeError(
                f"PDF extraction failed: {extract_result.error}"
            )

        raw_markdown = extract_result.markdown

        clean_markdown = clean_markdown_general(raw_markdown)

        chunk_texts = chunker.chunk(clean_markdown)

        chunks = self._build_chunks(
            source_id=source_id,
            chunk_texts=chunk_texts,
        )

        document = {
            "sourceId": source_id,
            "document": {
                "documentType": "pdf",
                "sourceLocation": pdf_file.as_posix(),
                "fileHash": file_hash,
                "extractionMethod": extract_result.method,
                "ingestionStatus": "completed",
                "rawMarkdown": raw_markdown,
                "cleanMarkdown": clean_markdown,
                "metadata": {},
                "stats": extract_result.stats,
            },
            "chunks": chunks,
        }

        self._save_json(source_id, document)

        return document

    def process_pdf_folder(
        self,
        input_dir: str | Path,
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        input_dir = Path(input_dir)

        pdf_files = (
            input_dir.rglob("*.pdf")
            if recursive
            else input_dir.glob("*.pdf")
        )

        results = []

        for pdf_file in pdf_files:
            try:
                result = self.process_pdf(pdf_file)
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "sourceLocation": pdf_file.as_posix(),
                        "success": False,
                        "error": str(e),
                    }
                )

        return results

    def _build_chunks(
        self,
        source_id: str,
        chunk_texts: list[str],
    ) -> list[dict[str, Any]]:
        chunks = []

        for index, content in enumerate(chunk_texts):
            chunk_hash = self._hash_text(content)

            chunks.append(
                {
                    "chunkId": f"{source_id}_{index:04d}",
                    "sourceId": source_id,
                    "chunkIndex": index,
                    "content": content,
                    "chunkHash": chunk_hash,
                    "metadata": {},
                }
            )

        return chunks

    def _save_json(
        self,
        source_id: str,
        data: dict[str, Any],
    ) -> Path:
        output_file = self.output_dir / f"{source_id}.json"

        output_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return output_file

    def _create_source_id(self, source_location: str) -> str:
        return hashlib.sha256(
            source_location.encode("utf-8")
        ).hexdigest()[:16]

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    def _hash_file(self, file_path: Path) -> str:
        hasher = hashlib.sha256()

        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)

        return hasher.hexdigest()


pipeline = DataBuildingPipeline(
    output_dir="data/json_documents",
    pdf_method="pymupdf",
)

results = pipeline.process_pdf_folder(
    input_dir="uploads/pdf_documents",
    recursive=True,
)