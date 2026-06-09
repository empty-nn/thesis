from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol
import pymupdf4llm

@dataclass
class PdfMarkdownResult:
    method: str
    source_file: str
    markdown: str = ""
    success: bool = True
    error: Optional[str] = None
    duration_seconds: float = 0.0
    stats: Dict[str, int | float] = field(default_factory=dict)


class PdfToMarkdownConverter(Protocol):
    name: str

    def convert(self, pdf_path: Path) -> str:
        ...


class PyMuPDF4LLMConverter:
    name = "pymupdf4llm"

    def convert(self, pdf_path: Path) -> str:
        return pymupdf4llm.to_markdown(str(pdf_path))

class DoclingConverter:
    """
    Optional converter.
    Only works if docling is installed.
    """

    name = "docling"

    def convert(self, pdf_path: Path) -> str:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))

        return result.document.export_to_markdown()


class PdfMarkdownLoader:
    def __init__(
        self,
        method: str = "pymupdf4llm",
        converters: Optional[List[PdfToMarkdownConverter]] = None,
    ):
        self.method = method

        default_converters: List[PdfToMarkdownConverter] = [
            PyMuPDF4LLMConverter(),
            DoclingConverter(),
        ]

        self.converters = {
            converter.name: converter
            for converter in (converters or default_converters)
        }

    def available_methods(self) -> List[str]:
        return list(self.converters.keys())

    def load(
        self,
        pdf_path: str | Path,
        method: Optional[str] = None,
    ) -> PdfMarkdownResult:
        selected_method = method or self.method
        pdf_path_obj = Path(pdf_path)

        if not pdf_path_obj.exists():
            return PdfMarkdownResult(
                method=selected_method,
                source_file=str(pdf_path_obj),
                success=False,
                error=f"PDF file does not exist: {pdf_path_obj}",
            )

        if selected_method not in self.converters:
            return PdfMarkdownResult(
                method=selected_method,
                source_file=str(pdf_path_obj),
                success=False,
                error=(
                    f"Unknown PDF converter method: {selected_method}. "
                    f"Available methods: {self.available_methods()}"
                ),
            )

        converter = self.converters[selected_method]

        start_time = time.perf_counter()

        try:
            markdown = converter.convert(pdf_path_obj)

            duration = time.perf_counter() - start_time

            return PdfMarkdownResult(
                method=selected_method,
                source_file=str(pdf_path_obj),
                markdown=markdown,
                success=True,
                duration_seconds=duration,
                stats=self._build_stats(markdown),
            )

        except Exception as e:
            duration = time.perf_counter() - start_time

            return PdfMarkdownResult(
                method=selected_method,
                source_file=str(pdf_path_obj),
                success=False,
                error=str(e),
                duration_seconds=duration,
            )

    def compare(
        self,
        pdf_path: str | Path,
        methods: Optional[List[str]] = None,
        output_dir: Optional[str | Path] = None,
    ) -> List[PdfMarkdownResult]:
        methods_to_run = methods or self.available_methods()

        results = []

        for method in methods_to_run:
            result = self.load(
                pdf_path=pdf_path,
                method=method,
            )

            results.append(result)

            if output_dir and result.success:
                self._save_markdown_result(
                    result=result,
                    output_dir=Path(output_dir),
                )

        return results

    def _save_markdown_result(
        self,
        result: PdfMarkdownResult,
        output_dir: Path,
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        source_name = Path(result.source_file).stem
        output_path = output_dir / f"{source_name}.{result.method}.md"

        output_path.write_text(
            result.markdown,
            encoding="utf-8",
        )

    def _build_stats(self, markdown: str) -> Dict[str, int | float]:
        lines = markdown.splitlines()
        words = markdown.split()

        heading_count = sum(
            1 for line in lines
            if line.strip().startswith("#")
        )

        image_count = markdown.count("![")
        table_like_line_count = sum(
            1 for line in lines
            if "|" in line
        )

        return {
            "char_count": len(markdown),
            "word_count": len(words),
            "line_count": len(lines),
            "heading_count": heading_count,
            "image_count": image_count,
            "table_like_line_count": table_like_line_count,
        }