from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class HtmlCleanerResult:
    method: str
    source_name: str
    markdown: str
    success: bool
    error: Optional[str] = None
    duration_seconds: float = 0.0
    stats: Dict[str, Any] = field(default_factory=dict)


class HtmlCleanerStrategy(ABC):
    method_name: str

    @abstractmethod
    def clean(
        self,
        html_text: str,
        source_url: Optional[str] = None,
    ) -> str:
        pass


class TrafilaturaCleaner(HtmlCleanerStrategy):
    method_name = "trafilatura"

    def clean(
        self,
        html_text: str,
        source_url: Optional[str] = None,
    ) -> str:
        import trafilatura

        markdown = trafilatura.extract(
            html_text,
            url=source_url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_precision=True,
        )

        return markdown.strip() if markdown else ""


class ReadabilityCleaner(HtmlCleanerStrategy):
    method_name = "readability"

    def clean(
        self,
        html_text: str,
        source_url: Optional[str] = None,
    ) -> str:
        from markdownify import markdownify
        from readability import Document

        document = Document(html_text)

        title = document.short_title()
        summary_html = document.summary(html_partial=True)

        markdown = markdownify(
            summary_html,
            heading_style="ATX",
            bullets="-",
            strip=["script", "style"],
        ).strip()

        if title:
            return f"# {title.strip()}\n\n{markdown}".strip()

        return markdown


class JusTextCleaner(HtmlCleanerStrategy):
    method_name = "justext"

    def clean(
        self,
        html_text: str,
        source_url: Optional[str] = None,
    ) -> str:
        import justext

        paragraphs = justext.justext(
            html_text,
            justext.get_stoplist("English"),
        )

        kept_paragraphs = [
            paragraph.text.strip()
            for paragraph in paragraphs
            if not paragraph.is_boilerplate and paragraph.text.strip()
        ]

        return "\n\n".join(kept_paragraphs).strip()


class BoilerPy3Cleaner(HtmlCleanerStrategy):
    method_name = "boilerpy3"

    def clean(
        self,
        html_text: str,
        source_url: Optional[str] = None,
    ) -> str:
        from boilerpy3 import extractors

        extractor = extractors.ArticleExtractor()
        markdown = extractor.get_content(html_text)

        return markdown.strip() if markdown else ""


class InscriptisCleaner(HtmlCleanerStrategy):
    method_name = "inscriptis"

    def clean(
        self,
        html_text: str,
        source_url: Optional[str] = None,
    ) -> str:
        from inscriptis import get_text

        markdown = get_text(html_text)

        return markdown.strip() if markdown else ""



class HtmlCleanerFactory:
    _strategies = {
        "trafilatura": TrafilaturaCleaner,
        "readability": ReadabilityCleaner,
        "justext": JusTextCleaner,
        "boilerpy3": BoilerPy3Cleaner,
        "inscriptis": InscriptisCleaner,
    }

    @classmethod
    def create(cls, method: str) -> HtmlCleanerStrategy:
        method = method.lower().strip()

        strategy_class = cls._strategies.get(method)

        if not strategy_class:
            raise ValueError(
                f"Unsupported HTML cleaner method: {method}. "
                f"Available methods: {cls.available_methods()}"
            )

        return strategy_class()

    @classmethod
    def available_methods(cls) -> list[str]:
        return list(cls._strategies.keys())


class HtmlCleaner:
    def __init__(
        self,
        html_text: str,
        source_name: str = "html_string",
        source_url: Optional[str] = None,
    ):
        if not html_text or not html_text.strip():
            raise ValueError("HTML content is empty")

        self.html_text = html_text
        self.source_name = source_name
        self.source_url = source_url

    def clean(
        self,
        method: str = "trafilatura",
    ) -> HtmlCleanerResult:
        start_time = time.perf_counter()

        try:
            strategy = HtmlCleanerFactory.create(method)

            markdown = strategy.clean(
                html_text=self.html_text,
                source_url=self.source_url,
            )

            duration = time.perf_counter() - start_time

            return HtmlCleanerResult(
                method=strategy.method_name,
                source_name=self.source_name,
                markdown=markdown,
                success=bool(markdown.strip()),
                error=None if markdown.strip() else "Empty extracted markdown",
                duration_seconds=duration,
                stats=self._get_markdown_stats(markdown),
            )

        except Exception as e:
            duration = time.perf_counter() - start_time

            return HtmlCleanerResult(
                method=method,
                source_name=self.source_name,
                markdown="",
                success=False,
                error=str(e),
                duration_seconds=duration,
            )

    def clean_with_fallback(
        self,
        preferred_methods: Optional[list[str]] = None,
        min_chars: int = 300,
    ) -> HtmlCleanerResult:
        methods = preferred_methods or [
            "trafilatura",
            "readability",
            "justext",
            "boilerpy3",
            "inscriptis",
        ]

        last_result: Optional[HtmlCleanerResult] = None

        for method in methods:
            result = self.clean(method=method)
            last_result = result

            if result.success and len(result.markdown.strip()) >= min_chars:
                return result

        if last_result:
            return last_result

        return HtmlCleanerResult(
            method="fallback",
            source_name=self.source_name,
            markdown="",
            success=False,
            error="No HTML cleaner method produced enough content",
        )

    def compare_methods(self) -> list[HtmlCleanerResult]:
        results = []

        for method in HtmlCleanerFactory.available_methods():
            result = self.clean(method=method)
            results.append(result)

        return results

    def available_methods(self) -> list[str]:
        return HtmlCleanerFactory.available_methods()

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

        link_count = len(
            re.findall(r"\[.+?\]\(.+?\)", markdown)
        )

        image_count = len(
            re.findall(r"!\[.*?\]\(.+?\)", markdown)
        )

        return {
            "char_count": len(markdown),
            "word_count": len(words),
            "line_count": len(lines),
            "heading_count": heading_count,
            "table_line_count": table_line_count,
            "link_count": link_count,
            "image_count": image_count,
        }