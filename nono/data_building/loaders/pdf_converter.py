from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class PdfConverterResult:
    method: str
    source_file: str
    markdown: str
    success: bool
    error: Optional[str] = None
    duration_seconds: float = 0.0
    stats: Dict[str, Any] = field(default_factory=dict)


class PdfToMarkdownStrategy(ABC):
    method_name: str

    @abstractmethod
    def convert(self, pdf_path: Path) -> str:
        pass


class PyMuPDFStrategy(PdfToMarkdownStrategy):
    method_name = "pymupdf"

    def convert(self, pdf_path: Path) -> str:
        import pymupdf4llm

        return pymupdf4llm.to_markdown(str(pdf_path))


class DoclingStrategy(PdfToMarkdownStrategy):
    method_name = "docling"

    def convert(self, pdf_path: Path) -> str:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))

        return result.document.export_to_markdown()


class PdfConverterFactory:
    _strategies = {
        "pymupdf": PyMuPDFStrategy,
        "docling": DoclingStrategy,
    }

    @classmethod
    def create(cls, method: str) -> PdfToMarkdownStrategy:
        method = method.lower().strip()

        strategy_class = cls._strategies.get(method)

        if not strategy_class:
            raise ValueError(
                f"Unsupported PDF conversion method: {method}. "
                f"Available methods: {cls.available_methods()}"
            )

        return strategy_class()

    @classmethod
    def available_methods(cls) -> list[str]:
        return list(cls._strategies.keys())


class PdfConverter:
    def __init__(self, pdf_file: str | Path):
        self.pdf_file = Path(pdf_file)

        if not self.pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_file}")

        if self.pdf_file.suffix.lower() != ".pdf":
            raise ValueError(f"File must be a PDF: {self.pdf_file}")

    def to_markdown(self, method: str = "pymupdf") -> PdfConverterResult:
        start_time = time.perf_counter()

        try:
            strategy = PdfConverterFactory.create(method)
            markdown = strategy.convert(self.pdf_file)

            duration = time.perf_counter() - start_time

            return PdfConverterResult(
                method=strategy.method_name,
                source_file=str(self.pdf_file),
                markdown=markdown,
                success=True,
                duration_seconds=duration,
                stats=self._get_markdown_stats(markdown),
            )

        except Exception as e:
            duration = time.perf_counter() - start_time

            return PdfConverterResult(
                method=method,
                source_file=str(self.pdf_file),
                markdown="",
                success=False,
                error=str(e),
                duration_seconds=duration,
            )

    def compare_methods(
        self,
        output_dir: str | Path | None = None,
    ) -> list[PdfConverterResult]:
        results = []

        for method in PdfConverterFactory.available_methods():
            result = self.to_markdown(method=method)
            results.append(result)

            if output_dir and result.success:
                self.save_markdown(
                    markdown=result.markdown,
                    method=result.method,
                    output_dir=output_dir,
                )

        return results

    def save_markdown(
        self,
        markdown: str,
        method: str,
        output_dir: str | Path,
    ) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{self.pdf_file.stem}.{method}.md"

        output_file.write_text(
            markdown,
            encoding="utf-8",
        )

        return output_file

    def available_methods(self) -> list[str]:
        return PdfConverterFactory.available_methods()

    def _get_markdown_stats(self, markdown: str) -> Dict[str, Any]:
        lines = markdown.splitlines()
        words = markdown.split()

        heading_count = sum(
            1 for line in lines
            if line.strip().startswith("#")
        )

        table_line_count = sum(
            1 for line in lines
            if "|" in line
        )

        return {
            "char_count": len(markdown),
            "word_count": len(words),
            "line_count": len(lines),
            "heading_count": heading_count,
            "table_line_count": table_line_count,
        }