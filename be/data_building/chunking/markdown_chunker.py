from __future__ import annotations

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
    metadata: Dict[str, Any] = field(default_factory=dict)
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
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

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
                strip_headers=False,
            )

            header_docs = header_splitter.split_text(markdown)

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
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

            chunks: list[MarkdownChunk] = []
            chunk_index = 0

            for doc in header_docs:
                split_texts = text_splitter.split_text(doc.page_content)

                for split_text in split_texts:
                    cleaned_text = split_text.strip()

                    if not cleaned_text:
                        continue

                    chunk = MarkdownChunk(
                        chunk_index=chunk_index,
                        chunk_text=cleaned_text,
                        metadata=dict(doc.metadata),
                        word_count=len(cleaned_text.split()),
                        char_count=len(cleaned_text),
                    )

                    chunks.append(chunk)
                    chunk_index += 1

            duration = time.perf_counter() - start_time

            return MarkdownChunkerResult(
                chunks=chunks,
                success=True,
                duration_seconds=duration,
                stats=self._get_stats(chunks),
            )

        except Exception as e:
            duration = time.perf_counter() - start_time

            return MarkdownChunkerResult(
                chunks=[],
                success=False,
                error=str(e),
                duration_seconds=duration,
            )

    def _get_stats(self, chunks: list[MarkdownChunk]) -> Dict[str, Any]:
        if not chunks:
            return {
                "chunk_count": 0,
                "total_words": 0,
                "total_chars": 0,
                "average_words": 0,
                "average_chars": 0,
            }

        total_words = sum(chunk.word_count for chunk in chunks)
        total_chars = sum(chunk.char_count for chunk in chunks)

        return {
            "chunk_count": len(chunks),
            "total_words": total_words,
            "total_chars": total_chars,
            "average_words": total_words / len(chunks),
            "average_chars": total_chars / len(chunks),
        }