from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


@dataclass
class MarkdownChunk:
    chunk_index: int
    chunk_text: str
    chunk_hash: str
    section_heading: Optional[str] = None
    header_metadata: Dict[str, Any] = field(default_factory=dict)
    word_count: int = 0
    char_count: int = 0


@dataclass
class MarkdownChunkerResult:
    chunks: list[MarkdownChunk]
    success: bool
    error: Optional[str] = None
    duration_seconds: float = 0.0
    stats: Dict[str, Any] = field(default_factory=dict)


class MarkdownChunker:
    def __init__(
        self,
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
        min_chunk_chars: int = 150,
        include_heading_context: bool = True,
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")

        if chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")

        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_chars = min_chunk_chars
        self.include_heading_context = include_heading_context

    def chunk(self, markdown: str) -> MarkdownChunkerResult:
        start_time = time.perf_counter()

        try:
            if not markdown or not markdown.strip():
                raise ValueError("Markdown content is empty")

            header_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[
                    ("#", "header_1"),
                    ("##", "header_2"),
                    ("###", "header_3"),
                    ("####", "header_4"),
                ],
                strip_headers=True,
            )

            header_docs = header_splitter.split_text(markdown)

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                length_function=len,
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

            candidates: list[Dict[str, Any]] = []

            for doc in header_docs:
                body = doc.page_content.strip()

                # Skips sections containing only a heading.
                if not body:
                    continue

                metadata = dict(doc.metadata)
                section_heading = self._get_section_heading(metadata)

                split_texts = text_splitter.split_text(body)

                for split_text in split_texts:
                    cleaned_body = split_text.strip()

                    if not cleaned_body:
                        continue

                    if self._is_noise(cleaned_body):
                        continue

                    candidates.append({
                        "body": cleaned_body,
                        "section_heading": section_heading,
                        "header_metadata": metadata,
                    })

            # Merge short adjacent chunks within the same section.
            candidates = self._merge_short_chunks(candidates)

            chunks: list[MarkdownChunk] = []

            for candidate in candidates:
                body = candidate["body"].strip()
                metadata = candidate["header_metadata"]

                if self.include_heading_context:
                    chunk_text = self._add_heading_context(
                        body=body,
                        metadata=metadata,
                    )
                else:
                    chunk_text = body

                chunk_text = chunk_text.strip()

                if not chunk_text:
                    continue

                chunk = MarkdownChunk(
                    chunk_index=len(chunks),
                    chunk_text=chunk_text,
                    chunk_hash=self._hash_text(chunk_text),
                    section_heading=candidate["section_heading"],
                    header_metadata=metadata,
                    word_count=self._count_words(chunk_text),
                    char_count=len(chunk_text),
                )

                chunks.append(chunk)

            duration = time.perf_counter() - start_time

            return MarkdownChunkerResult(
                chunks=chunks,
                success=True,
                duration_seconds=duration,
                stats=self._get_stats(chunks),
            )

        except Exception as exc:
            duration = time.perf_counter() - start_time

            return MarkdownChunkerResult(
                chunks=[],
                success=False,
                error=str(exc),
                duration_seconds=duration,
            )

    def _merge_short_chunks(
        self,
        candidates: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        """
        Merge short chunks with an adjacent chunk only when both belong
        to the same Markdown section.
        """
        if not candidates:
            return []

        working = [
            {
                "body": item["body"],
                "section_heading": item["section_heading"],
                "header_metadata": dict(item["header_metadata"]),
            }
            for item in candidates
        ]

        merged: list[Dict[str, Any]] = []
        index = 0

        while index < len(working):
            current = working[index]
            current_body = current["body"].strip()

            if not current_body:
                index += 1
                continue

            if len(current_body) >= self.min_chunk_chars:
                merged.append(current)
                index += 1
                continue

            # First try to merge the short chunk forward.
            if index + 1 < len(working):
                next_item = working[index + 1]

                if self._same_section(current, next_item):
                    combined = (
                        f"{current_body}\n\n"
                        f"{next_item['body'].strip()}"
                    )

                    if len(combined) <= self.chunk_size:
                        next_item["body"] = combined
                        working[index + 1] = next_item

                        index += 1
                        continue

            # Otherwise try to merge backward.
            if merged and self._same_section(merged[-1], current):
                previous = merged[-1]

                combined = (
                    f"{previous['body'].strip()}\n\n"
                    f"{current_body}"
                )

                if len(combined) <= self.chunk_size:
                    previous["body"] = combined
                    merged[-1] = previous

                    index += 1
                    continue

            # Keep short but meaningful content when it cannot safely
            # be merged with the same section.
            if not self._is_noise(current_body):
                merged.append(current)

            index += 1

        return merged

    @staticmethod
    def _same_section(
        first: Dict[str, Any],
        second: Dict[str, Any],
    ) -> bool:
        return (
            first.get("header_metadata", {})
            == second.get("header_metadata", {})
        )

    @staticmethod
    def _is_noise(text: str) -> bool:
        """
        Remove only clearly meaningless content.

        Do not reject content merely because it is short.
        """
        stripped = text.strip()

        if not stripped:
            return True

        # Heading-only Markdown, for example:
        # ## Buy
        # ### Shopping
        lines = [
            line.strip()
            for line in stripped.splitlines()
            if line.strip()
        ]

        if lines and all(
            re.fullmatch(r"#{1,6}\s+.+", line)
            for line in lines
        ):
            return True

        # Remove Markdown links before checking text quality.
        visible_text = re.sub(
            r"\[([^\]]*)\]\([^)]+\)",
            r"\1",
            stripped,
        )

        # Remove standalone URLs.
        visible_text = re.sub(
            r"https?://\S+",
            " ",
            visible_text,
        )

        visible_text = re.sub(
            r"[#>*_`~|]",
            " ",
            visible_text,
        )

        visible_text = re.sub(
            r"\s+",
            " ",
            visible_text,
        ).strip()

        if not visible_text:
            return True

        alpha_count = sum(
            character.isalpha()
            for character in visible_text
        )

        alpha_ratio = alpha_count / max(len(visible_text), 1)

        if alpha_ratio < 0.25:
            return True

        return False

    @staticmethod
    def _count_words(text: str) -> int:
        return len(
            re.findall(
                r"\b[\w'-]+\b",
                text,
                flags=re.UNICODE,
            )
        )

    def _add_heading_context(
        self,
        body: str,
        metadata: Dict[str, Any],
    ) -> str:
        """
        Convert heading metadata into retrieval context.

        Example:
            Section: Buy > Shopping

            Joe's is located at...
        """
        heading_path = self._get_heading_path(metadata)

        if not heading_path:
            return body

        return f"Section: {heading_path}\n\n{body}"

    @staticmethod
    def _get_heading_path(
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        headings = [
            metadata.get("header_1"),
            metadata.get("header_2"),
            metadata.get("header_3"),
            metadata.get("header_4"),
        ]

        headings = [
            str(heading).strip()
            for heading in headings
            if heading and str(heading).strip()
        ]

        if not headings:
            return None

        return " > ".join(headings)

    @staticmethod
    def _get_section_heading(
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        for key in [
            "header_4",
            "header_3",
            "header_2",
            "header_1",
        ]:
            value = metadata.get(key)

            if value:
                return str(value).strip()

        return None

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _get_stats(
        chunks: list[MarkdownChunk],
    ) -> Dict[str, Any]:
        if not chunks:
            return {
                "chunk_count": 0,
                "total_words": 0,
                "total_chars": 0,
                "average_words": 0,
                "average_chars": 0,
                "min_chars": 0,
                "max_chars": 0,
            }

        total_words = sum(
            chunk.word_count
            for chunk in chunks
        )

        total_chars = sum(
            chunk.char_count
            for chunk in chunks
        )

        char_counts = [
            chunk.char_count
            for chunk in chunks
        ]

        return {
            "chunk_count": len(chunks),
            "total_words": total_words,
            "total_chars": total_chars,
            "average_words": total_words / len(chunks),
            "average_chars": total_chars / len(chunks),
            "min_chars": min(char_counts),
            "max_chars": max(char_counts),
        }