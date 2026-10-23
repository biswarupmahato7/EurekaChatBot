"""
crawler/tests/test_validation.py
================================
Unit tests for raw dataset and chunk dataset validation routines.
"""
import pytest
from crawler.validation import validate_raw_dataset, validate_chunk_dataset
from crawler.models import RawDataset, PageRecord, ChunkDataset, ChunkRecord
from crawler.hashing import make_page_id, make_content_hash, make_chunk_id, make_chunk_content_hash

PID_1 = make_page_id("https://eurekasolutions.in/Eureka2026/p1", "https://eurekasolutions.in/Eureka2026/p1")
PID_2 = make_page_id("https://eurekasolutions.in/Eureka2026/p2", "https://eurekasolutions.in/Eureka2026/p2")
CHASH_1 = make_content_hash("Content 1", "Title 1")
CHASH_2 = make_content_hash("Content 2", "Title 2")


class TestValidateRawDataset:
    def test_valid_raw_dataset_passes(self):
        data = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "crawler_version": "1.0.0",
            "pages": [
                {
                    "page_id": PID_1,
                    "schema_version": "1.0",
                    "source_url": "https://eurekasolutions.in/Eureka2026/p1",
                    "final_url": "https://eurekasolutions.in/Eureka2026/p1",
                    "title": "Title 1",
                    "content": "This is valid content that is long enough to avoid being empty.",
                    "content_hash": CHASH_1,
                }
            ],
        }
        report = validate_raw_dataset(data)
        assert report.passed is True
        assert report.error_count == 0

    def test_missing_schema_version_fails(self):
        data = {
            "schema_version": "0.9",
            "run_id": "test-run-123",
            "pages": [],
        }
        report = validate_raw_dataset(data)
        assert report.passed is False
        assert any("schema_version" in i.field for i in report.issues if i.field)

    def test_duplicate_page_id_fails(self):
        page = {
            "page_id": PID_1,
            "schema_version": "1.0",
            "source_url": "https://eurekasolutions.in/Eureka2026/p1",
            "final_url": "https://eurekasolutions.in/Eureka2026/p1",
            "title": "Title 1",
            "content": "Content text here.",
            "content_hash": CHASH_1,
        }
        data = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "pages": [page, dict(page, source_url="https://eurekasolutions.in/Eureka2026/p1-diff")],
        }
        report = validate_raw_dataset(data)
        assert report.passed is False
        assert any("Duplicate page_id" in i.message for i in report.issues)

    def test_out_of_scope_url_fails(self):
        data = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "pages": [
                {
                    "page_id": PID_1,
                    "schema_version": "1.0",
                    "source_url": "https://malicious.com/Eureka2026/p1",
                    "final_url": "https://malicious.com/Eureka2026/p1",
                    "content": "Content text here.",
                    "content_hash": CHASH_1,
                }
            ],
        }
        report = validate_raw_dataset(data)
        assert report.passed is False
        assert any("scope" in i.message.lower() for i in report.issues)


class TestValidateChunkDataset:
    def test_valid_chunk_dataset_passes(self):
        cid = make_chunk_id(PID_1, 0, "1.0")
        chunk_hash = make_chunk_content_hash("Chunk text content.")
        data = {
            "schema_version": "1.0",
            "run_id": "test-chunk-run",
            "total_chunks": 1,
            "chunks": [
                {
                    "chunk_id": cid,
                    "page_id": PID_1,
                    "chunk_index": 0,
                    "source_url": "https://eurekasolutions.in/Eureka2026/p1",
                    "content": "Chunk text content.",
                    "token_count": 4,
                    "content_hash": chunk_hash,
                    "chunking_version": "1.0",
                }
            ],
        }
        report = validate_chunk_dataset(data, raw_data={"pages": [{"page_id": PID_1}]})
        assert report.passed is True
        assert report.error_count == 0

    def test_dangling_chunk_fails(self):
        cid = make_chunk_id(PID_1, 0, "1.0")
        chunk_hash = make_chunk_content_hash("Chunk text content.")
        data = {
            "schema_version": "1.0",
            "run_id": "test-chunk-run",
            "chunks": [
                {
                    "chunk_id": cid,
                    "page_id": PID_1,
                    "chunk_index": 0,
                    "source_url": "https://eurekasolutions.in/Eureka2026/p1",
                    "content": "Chunk text content.",
                    "token_count": 4,
                    "content_hash": chunk_hash,
                }
            ],
        }
        # raw_data contains PID_2, but chunk references PID_1
        report = validate_chunk_dataset(data, raw_data={"pages": [{"page_id": PID_2}]})
        assert report.passed is False
        assert any("non-existent page_id" in i.message for i in report.issues)

    def test_duplicate_chunk_id_fails(self):
        cid = make_chunk_id(PID_1, 0, "1.0")
        chunk = {
            "chunk_id": cid,
            "page_id": PID_1,
            "chunk_index": 0,
            "source_url": "https://eurekasolutions.in/Eureka2026/p1",
            "content": "Chunk text content.",
            "token_count": 4,
            "content_hash": make_chunk_content_hash("Chunk text content."),
        }
        data = {
            "schema_version": "1.0",
            "run_id": "test-chunk-run",
            "chunks": [chunk, chunk],
        }
        report = validate_chunk_dataset(data)
        assert report.passed is False
        assert any("Duplicate chunk_id" in i.message for i in report.issues)
