"""
crawler/tests/test_config_models.py
===================================
Unit tests for CrawlerSettings, data models, schema constraints, and environment overrides.
"""
import pytest
from pydantic import ValidationError
from crawler.config import CrawlerSettings
from crawler.models import (
    ChunkDataset,
    ChunkRecord,
    ContentBlock,
    CrawlStats,
    DiscoveredURL,
    FetchStatus,
    Heading,
    PageRecord,
    RawDataset,
    ValidationIssue,
    ValidationReport,
)

SAMPLE_HEX_64 = "a" * 64
SAMPLE_HEX_64_B = "b" * 64


class TestCrawlerSettings:
    def test_default_values(self):
        settings = CrawlerSettings()
        assert settings.crawler_approved_origin == "eurekasolutions.in"
        assert settings.crawler_approved_path_prefix == "/Eureka2026/"
        assert settings.chunk_target_tokens == 500
        assert settings.chunk_overlap_tokens == 75
        assert settings.chunk_max_tokens == 700
        assert settings.chunk_min_tokens == 80
        assert settings.crawler_max_pages == 150
        assert settings.crawler_max_depth == 6

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CRAWLER_MAX_PAGES", "42")
        monkeypatch.setenv("CHUNK_TARGET_TOKENS", "400")
        settings = CrawlerSettings()
        assert settings.crawler_max_pages == 42
        assert settings.chunk_target_tokens == 400

    def test_overlap_tokens_must_be_less_than_target(self, monkeypatch):
        monkeypatch.setenv("CHUNK_TARGET_TOKENS", "100")
        monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "120")
        with pytest.raises(ValidationError):
            CrawlerSettings()

    def test_target_tokens_must_be_le_max_tokens(self, monkeypatch):
        monkeypatch.setenv("CHUNK_TARGET_TOKENS", "800")
        monkeypatch.setenv("CHUNK_MAX_TOKENS", "700")
        with pytest.raises(ValidationError):
            CrawlerSettings()

    def test_excluded_patterns_list(self):
        settings = CrawlerSettings()
        patterns = settings.excluded_patterns_list
        assert isinstance(patterns, list)
        assert "privacy-policy" in patterns
        assert "mailto:" in patterns


class TestHeadingAndContentBlockModels:
    def test_heading_valid(self):
        h = Heading(level=2, text="  About Our Team  ")
        assert h.level == 2
        assert h.text == "About Our Team"

    def test_heading_invalid_level(self):
        with pytest.raises(ValidationError):
            Heading(level=7, text="Invalid")
        with pytest.raises(ValidationError):
            Heading(level=0, text="Invalid")

    def test_content_block_valid(self):
        b = ContentBlock(block_type="paragraph", content="Sample text", heading_context="Intro")
        assert b.block_type == "paragraph"
        assert b.content == "Sample text"

    def test_content_block_invalid_type(self):
        with pytest.raises(ValidationError):
            ContentBlock(block_type="unsupported_type", content="Sample")


class TestPageRecordModel:
    def test_valid_page_record(self):
        pr = PageRecord(
            page_id=SAMPLE_HEX_64,
            schema_version="1.0",
            source_url="https://eurekasolutions.in/Eureka2026/about",
            final_url="https://eurekasolutions.in/Eureka2026/about",
            title="About Us",
            content="Eureka Solutions company background.",
            content_hash=SAMPLE_HEX_64_B,
            http_status=200,
        )
        assert pr.page_id == SAMPLE_HEX_64
        assert pr.title == "About Us"
        assert pr.canonical_url is None
        assert pr.warnings == []
        assert pr.is_low_content is False

    def test_invalid_hash_raises(self):
        with pytest.raises(ValidationError):
            PageRecord(
                page_id="not-a-64-char-hex",
                schema_version="1.0",
                source_url="https://eurekasolutions.in/Eureka2026/about",
                final_url="https://eurekasolutions.in/Eureka2026/about",
                content_hash=SAMPLE_HEX_64_B,
            )

    def test_invalid_schema_version_raises(self):
        with pytest.raises(ValidationError):
            PageRecord(
                page_id=SAMPLE_HEX_64,
                schema_version="2.0",
                source_url="https://eurekasolutions.in/Eureka2026/about",
                final_url="https://eurekasolutions.in/Eureka2026/about",
                content_hash=SAMPLE_HEX_64_B,
            )


class TestRawDatasetModel:
    def test_raw_dataset_defaults(self):
        rd = RawDataset()
        assert rd.schema_version == "1.0"
        assert rd.pages == []
        assert isinstance(rd.stats, CrawlStats)
        assert len(rd.run_id) > 0

    def test_raw_dataset_invalid_schema_raises(self):
        with pytest.raises(ValidationError):
            RawDataset(schema_version="0.9")


class TestChunkRecordAndDataset:
    def test_valid_chunk_record(self):
        cr = ChunkRecord(
            chunk_id=SAMPLE_HEX_64,
            page_id=SAMPLE_HEX_64_B,
            chunk_index=0,
            source_url="https://eurekasolutions.in/Eureka2026/services",
            content="Chunk content text.",
            token_count=12,
            content_hash=SAMPLE_HEX_64,
            chunking_version="1.0",
        )
        assert cr.chunk_index == 0
        assert cr.token_count == 12

    def test_empty_content_raises(self):
        with pytest.raises(ValidationError):
            ChunkRecord(
                chunk_id=SAMPLE_HEX_64,
                page_id=SAMPLE_HEX_64_B,
                chunk_index=0,
                source_url="https://eurekasolutions.in/Eureka2026/services",
                content="   ",
                token_count=0,
                content_hash=SAMPLE_HEX_64,
            )

    def test_chunk_dataset_syncs_total_chunks(self):
        cr = ChunkRecord(
            chunk_id=SAMPLE_HEX_64,
            page_id=SAMPLE_HEX_64_B,
            chunk_index=0,
            source_url="https://eurekasolutions.in/Eureka2026/services",
            content="Some text",
            token_count=5,
            content_hash=SAMPLE_HEX_64,
        )
        ds = ChunkDataset(chunks=[cr])
        assert ds.total_chunks == 1


class TestValidationReportModel:
    def test_validation_report_pass_and_fail(self):
        rep_pass = ValidationReport(dataset="raw", schema_valid=True, total_records=5, error_count=0)
        assert rep_pass.passed is True

        rep_fail = ValidationReport(
            dataset="raw",
            schema_valid=True,
            total_records=5,
            error_count=1,
            issues=[ValidationIssue(severity="error", message="Broken URL")],
        )
        assert rep_fail.passed is False
