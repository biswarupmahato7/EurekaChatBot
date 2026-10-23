"""
crawler/chunker.py
==================
Token-aware, structure-aware chunker for the Eureka RAG Chatbot.

Input:  A PageRecord (already parsed and cleaned)
Output: A list of ChunkRecord objects

Chunking strategy (in priority order):
1. Split at section/heading boundaries
2. Split at paragraph/block boundaries
3. Sentence-level fallback for oversized text
4. Hard token-count split as last resort (always enforced)

TOKENIZER NOTE (architecture §4.1 / PS §7.1):
  The same tiktoken encoding used here MUST be used consistently for all
  downstream token budget calculations. Token counts are encoding-specific.
  The encoding name is stored in ChunkRecord.chunking_version and the
  dataset's chunking_config.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import tiktoken

from crawler.hashing import make_chunk_id, make_chunk_content_hash
from crawler.models import ChunkRecord, PageRecord

logger = logging.getLogger(__name__)


# ===========================================================================
# Tokenizer wrapper
# ===========================================================================

class Tokenizer:
    """Cached tiktoken encoder wrapper."""

    _instances: dict[str, "Tokenizer"] = {}

    def __new__(cls, encoding_name: str = "cl100k_base") -> "Tokenizer":
        if encoding_name not in cls._instances:
            instance = super().__new__(cls)
            instance._enc = tiktoken.get_encoding(encoding_name)
            instance._name = encoding_name
            cls._instances[encoding_name] = instance
        return cls._instances[encoding_name]

    def count(self, text: str) -> int:
        """Return the token count for text."""
        return len(self._enc.encode(text))

    @property
    def name(self) -> str:
        return self._name


# ===========================================================================
# Chunker
# ===========================================================================

class Chunker:
    """Convert a PageRecord into a list of ChunkRecord objects.

    Parameters
    ----------
    encoding_name : tiktoken encoding (must match downstream usage)
    target_tokens : target chunk size
    overlap_tokens : overlap between adjacent chunks
    max_tokens : hard maximum — NEVER exceeded
    min_tokens : soft minimum — avoid tiny chunks when possible
    chunking_version : version identifier stored in output
    """

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        target_tokens: int = 500,
        overlap_tokens: int = 75,
        max_tokens: int = 700,
        min_tokens: int = 80,
        chunking_version: str = "1.0",
    ) -> None:
        if overlap_tokens >= target_tokens:
            raise ValueError(f"overlap_tokens ({overlap_tokens}) must be < target_tokens ({target_tokens})")
        if target_tokens > max_tokens:
            raise ValueError(f"target_tokens ({target_tokens}) must be <= max_tokens ({max_tokens})")

        self.tok = Tokenizer(encoding_name)
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.chunking_version = chunking_version

    def chunk_page(self, page: PageRecord) -> list[ChunkRecord]:
        """Produce ChunkRecord list for one PageRecord.

        Returns empty list if page content is empty.
        """
        content = page.content.strip()
        if not content:
            logger.debug("Skipping empty page: %s", page.source_url)
            return []

        # Build heading-aware sections from the page
        sections = self._split_into_sections(page)
        chunks: list[ChunkRecord] = []

        for section_text, section_heading, heading_path in sections:
            section_text = section_text.strip()
            if not section_text:
                continue
            section_chunks = self._chunk_text(
                section_text,
                section_heading=section_heading,
                heading_path=heading_path,
            )
            chunks.extend(section_chunks)

        # If no sections produced chunks, chunk the whole content
        if not chunks:
            raw_chunks = self._chunk_text(content, section_heading=None, heading_path=[])
            chunks.extend(raw_chunks)

        # Assign chunk_index and build ChunkRecord objects
        result: list[ChunkRecord] = []
        for idx, (text, heading, hpath) in enumerate(
            self._flatten_chunks(chunks)
        ):
            token_count = self.tok.count(text)
            # Hard maximum enforcement
            if token_count > self.max_tokens:
                sub_chunks = self._hard_split(text)
                for sub_idx, sub_text in enumerate(sub_chunks):
                    actual_idx = len(result)
                    result.append(self._make_chunk(
                        page=page,
                        text=sub_text,
                        chunk_index=actual_idx,
                        section_heading=heading,
                        heading_path=hpath,
                    ))
            else:
                result.append(self._make_chunk(
                    page=page,
                    text=text,
                    chunk_index=len(result),
                    section_heading=heading,
                    heading_path=hpath,
                ))

        return result

    # ── Section splitting ──────────────────────────────────────────────────────

    def _split_into_sections(
        self, page: PageRecord
    ) -> list[tuple[str, Optional[str], list[str]]]:
        """Split page content into (text, heading, heading_path) sections.

        Uses headings extracted from the page to divide content at
        natural section boundaries.
        """
        content = page.content
        headings = [(h.level, h.text) for h in page.headings]

        if not headings:
            return [(content, None, [])]

        sections: list[tuple[str, Optional[str], list[str]]] = []
        heading_stack: list[tuple[int, str]] = []

        # Split content at heading boundaries (regex on the text)
        lines = content.splitlines()
        current_lines: list[str] = []
        current_heading: Optional[str] = None
        heading_path: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Check if this line matches a known heading
            matched_heading = self._find_heading_match(stripped, headings)
            if matched_heading is not None:
                level, h_text = matched_heading
                # Save current section
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append((section_text, current_heading, list(heading_path)))

                # Update heading context
                current_heading = h_text
                heading_stack = [(l, t) for (l, t) in heading_stack if l < level]
                heading_stack.append((level, h_text))
                heading_path = [t for (_, t) in heading_stack]
                current_lines = []
            else:
                current_lines.append(line)

        # Last section
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append((section_text, current_heading, list(heading_path)))

        return sections if sections else [(content, None, [])]

    def _find_heading_match(
        self, text: str, headings: list[tuple[int, str]]
    ) -> Optional[tuple[int, str]]:
        """Return (level, text) if this line exactly matches a known heading."""
        text_clean = text.strip()
        for level, h_text in headings:
            if text_clean == h_text.strip():
                return (level, h_text)
        return None

    # ── Text chunking ─────────────────────────────────────────────────────────

    def _chunk_text(
        self,
        text: str,
        section_heading: Optional[str],
        heading_path: list[str],
    ) -> list[tuple[str, Optional[str], list[str]]]:
        """Split text into (chunk_text, heading, heading_path) tuples."""
        token_count = self.tok.count(text)

        if token_count <= self.target_tokens:
            return [(text, section_heading, heading_path)]

        # Split by paragraphs first
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paragraphs) <= 1:
            # Single block — split by sentences
            paragraphs = self._split_sentences(text)

        return self._merge_paragraphs(paragraphs, section_heading, heading_path)

    def _merge_paragraphs(
        self,
        paragraphs: list[str],
        heading: Optional[str],
        heading_path: list[str],
    ) -> list[tuple[str, Optional[str], list[str]]]:
        """Greedily merge paragraphs into chunks respecting token limits with overlap."""
        if not paragraphs:
            return []

        chunks: list[tuple[str, Optional[str], list[str]]] = []
        current: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.tok.count(para)

            # Single paragraph exceeds max — hard split it
            if para_tokens > self.max_tokens:
                if current:
                    chunks.append(("\n\n".join(current), heading, heading_path))
                    current = []
                    current_tokens = 0
                for sub in self._hard_split(para):
                    chunks.append((sub, heading, heading_path))
                continue

            # Adding this paragraph would exceed target — flush and start new
            if current and current_tokens + para_tokens > self.target_tokens:
                chunk_text = "\n\n".join(current)
                chunks.append((chunk_text, heading, heading_path))

                # Overlap: carry last paragraph(s) into next chunk
                overlap_text = self._build_overlap(current)
                current = [overlap_text, para] if overlap_text else [para]
                current_tokens = self.tok.count("\n\n".join(current))
            else:
                current.append(para)
                current_tokens += para_tokens

        # Flush remainder
        if current:
            chunks.append(("\n\n".join(current), heading, heading_path))

        return chunks

    def _build_overlap(self, paragraphs: list[str]) -> str:
        """Return the overlap text (last N tokens worth of paragraphs)."""
        if not paragraphs or self.overlap_tokens <= 0:
            return ""
        overlap_parts: list[str] = []
        tokens_so_far = 0
        for para in reversed(paragraphs):
            t = self.tok.count(para)
            if tokens_so_far + t <= self.overlap_tokens:
                overlap_parts.insert(0, para)
                tokens_so_far += t
            else:
                break
        return "\n\n".join(overlap_parts)

    def _split_sentences(self, text: str) -> list[str]:
        """Split text at sentence boundaries."""
        # Basic sentence splitter — split on '. ', '! ', '? '
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [p.strip() for p in parts if p.strip()]

    def _hard_split(self, text: str) -> list[str]:
        """Force-split text into chunks <= max_tokens by word boundaries."""
        words = text.split()
        chunks: list[str] = []
        current_words: list[str] = []
        current_tokens = 0

        for word in words:
            wt = self.tok.count(word + " ")
            if current_tokens + wt > self.max_tokens and current_words:
                chunks.append(" ".join(current_words))
                current_words = [word]
                current_tokens = wt
            else:
                current_words.append(word)
                current_tokens += wt

        if current_words:
            chunks.append(" ".join(current_words))

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _flatten_chunks(
        self, chunks: list[tuple[str, Optional[str], list[str]]]
    ) -> list[tuple[str, Optional[str], list[str]]]:
        return chunks  # already flat

    def _make_chunk(
        self,
        page: PageRecord,
        text: str,
        chunk_index: int,
        section_heading: Optional[str],
        heading_path: list[str],
    ) -> ChunkRecord:
        text = text.strip()
        token_count = self.tok.count(text)
        chunk_id = make_chunk_id(page.page_id, chunk_index, self.chunking_version)
        content_hash = make_chunk_content_hash(text)

        return ChunkRecord(
            chunk_id=chunk_id,
            page_id=page.page_id,
            chunk_index=chunk_index,
            source_url=page.source_url,
            canonical_url=page.canonical_url,
            page_title=page.title,
            section_heading=section_heading,
            heading_path=heading_path,
            content=text,
            token_count=token_count,
            content_hash=content_hash,
            chunking_version=self.chunking_version,
            last_crawled_at=page.crawl_timestamp,
        )
