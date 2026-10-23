"""
crawler/tests/test_chunker.py
=============================
Unit tests for token-aware, structure-aware chunking, token budget enforcement,
and stable chunk IDs.
"""
from pathlib import Path
import pytest
from crawler.chunker import Chunker, Tokenizer
from crawler.models import Heading, PageRecord
from crawler.hashing import make_page_id, make_content_hash

SAMPLE_URL = "https://eurekasolutions.in/Eureka2026/services"
PAGE_ID = make_page_id(SAMPLE_URL, SAMPLE_URL)


@pytest.fixture
def sample_page():
    content = """Technology Services
Eureka Solutions delivers enterprise-grade technology services across six practice areas.

Enterprise Software
We build ERP solutions, HR and payroll systems, and document management platforms tailored to your industry. We help clients scale efficiently.

AI and Intelligent Automation
Our AI practice helps organisations implement intelligent automation using agentic AI, copilots, and chatbots. We deploy bespoke models and RAG pipelines.

Business Intelligence
We translate data into actionable insights through Power BI solutions and KPI dashboards."""
    return PageRecord(
        page_id=PAGE_ID,
        schema_version="1.0",
        source_url=SAMPLE_URL,
        final_url=SAMPLE_URL,
        title="Technology Services | Eureka Solutions",
        content=content,
        headings=[
            Heading(level=1, text="Technology Services"),
            Heading(level=2, text="Enterprise Software"),
            Heading(level=2, text="AI and Intelligent Automation"),
            Heading(level=2, text="Business Intelligence"),
        ],
        content_hash=make_content_hash(content, "Technology Services | Eureka Solutions"),
    )


class TestTokenizer:
    def test_singleton_tokenizer(self):
        t1 = Tokenizer("cl100k_base")
        t2 = Tokenizer("cl100k_base")
        assert t1 is t2

    def test_token_counting(self):
        tok = Tokenizer("cl100k_base")
        assert tok.count("Hello world") == 2
        assert tok.count("") == 0


class TestChunker:
    def test_empty_page_returns_no_chunks(self):
        page = PageRecord(
            page_id=PAGE_ID,
            schema_version="1.0",
            source_url=SAMPLE_URL,
            final_url=SAMPLE_URL,
            title="Empty",
            content="",
            content_hash=make_content_hash("", "Empty"),
        )
        chunker = Chunker()
        chunks = chunker.chunk_page(page)
        assert chunks == []

    def test_chunking_preserves_headings_and_structure(self, sample_page):
        chunker = Chunker(target_tokens=40, overlap_tokens=10, max_tokens=60)
        chunks = chunker.chunk_page(sample_page)
        assert len(chunks) > 0

        # Verify all chunk indices are consecutive
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

        # Verify page references
        for c in chunks:
            assert c.page_id == PAGE_ID
            assert c.source_url == SAMPLE_URL
            assert c.token_count <= 60
            assert c.token_count == chunker.tok.count(c.content)

        # Verify section headings are captured
        headings = {c.section_heading for c in chunks if c.section_heading}
        assert len(headings) > 0

    def test_max_tokens_hard_limit_guaranteed(self):
        # Create a page with a 1500-token continuous block of text
        long_text = "word " * 1500
        page = PageRecord(
            page_id=PAGE_ID,
            schema_version="1.0",
            source_url=SAMPLE_URL,
            final_url=SAMPLE_URL,
            title="Long Page",
            content=long_text,
            content_hash=make_content_hash(long_text, "Long Page"),
        )
        max_limit = 200
        chunker = Chunker(target_tokens=150, overlap_tokens=20, max_tokens=max_limit)
        chunks = chunker.chunk_page(page)
        assert len(chunks) > 1
        for c in chunks:
            assert c.token_count <= max_limit, f"Chunk exceeded max_tokens: {c.token_count} > {max_limit}"

    def test_stable_chunk_ids(self, sample_page):
        chunker = Chunker(target_tokens=50, overlap_tokens=10, max_tokens=80)
        chunks1 = chunker.chunk_page(sample_page)
        chunks2 = chunker.chunk_page(sample_page)

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.chunk_id == c2.chunk_id
            assert c1.content_hash == c2.content_hash

    def test_chunking_version_change_updates_chunk_ids(self, sample_page):
        chunker_v1 = Chunker(chunking_version="1.0")
        chunker_v2 = Chunker(chunking_version="2.0")

        chunks_v1 = chunker_v1.chunk_page(sample_page)
        chunks_v2 = chunker_v2.chunk_page(sample_page)

        assert chunks_v1[0].chunk_id != chunks_v2[0].chunk_id

    def test_invalid_parameters_raise(self):
        with pytest.raises(ValueError, match="overlap_tokens"):
            Chunker(target_tokens=100, overlap_tokens=100)
        with pytest.raises(ValueError, match="target_tokens"):
            Chunker(target_tokens=500, max_tokens=400)
