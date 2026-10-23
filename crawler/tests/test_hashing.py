"""
crawler/tests/test_hashing.py
Tests for deterministic hashing and stable identifiers.
"""
import pytest
from crawler.hashing import (
    make_page_id,
    make_content_hash,
    make_chunk_id,
    make_chunk_content_hash,
)

CANONICAL = "https://eurekasolutions.in/Eureka2026/services"
SOURCE = "https://eurekasolutions.in/Eureka2026/services"


class TestPageId:
    def test_stable_on_repeated_calls(self):
        id1 = make_page_id(CANONICAL, SOURCE)
        id2 = make_page_id(CANONICAL, SOURCE)
        assert id1 == id2

    def test_is_64_char_hex(self):
        pid = make_page_id(CANONICAL, SOURCE)
        assert len(pid) == 64
        assert all(c in "0123456789abcdef" for c in pid)

    def test_uses_canonical_over_source(self):
        canonical = "https://eurekasolutions.in/Eureka2026/services"
        source_different = "https://eurekasolutions.in/Eureka2026/services?q=test"
        pid_canonical = make_page_id(canonical, source_different)
        pid_canonical2 = make_page_id(canonical, canonical)
        assert pid_canonical == pid_canonical2

    def test_falls_back_to_source_when_no_canonical(self):
        pid = make_page_id(None, SOURCE)
        pid2 = make_page_id("", SOURCE)
        assert pid == pid2

    def test_different_urls_produce_different_ids(self):
        pid1 = make_page_id(None, "https://eurekasolutions.in/Eureka2026/services")
        pid2 = make_page_id(None, "https://eurekasolutions.in/Eureka2026/about-us")
        assert pid1 != pid2

    def test_fragment_stripped_for_hash(self):
        pid_with = make_page_id("https://eurekasolutions.in/Eureka2026/services#section", SOURCE)
        pid_without = make_page_id("https://eurekasolutions.in/Eureka2026/services", SOURCE)
        assert pid_with == pid_without

    def test_host_lowercased(self):
        pid_lower = make_page_id("https://eurekasolutions.in/Eureka2026/services", SOURCE)
        pid_upper = make_page_id("https://EUREKASOLUTIONS.IN/Eureka2026/services", SOURCE)
        assert pid_lower == pid_upper


class TestContentHash:
    def test_stable_on_repeated_calls(self):
        h1 = make_content_hash("hello world", "My Title")
        h2 = make_content_hash("hello world", "My Title")
        assert h1 == h2

    def test_is_64_char_hex(self):
        h = make_content_hash("content", "title")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_content_change_changes_hash(self):
        h1 = make_content_hash("original content", "title")
        h2 = make_content_hash("modified content", "title")
        assert h1 != h2

    def test_title_change_changes_hash(self):
        h1 = make_content_hash("content", "original title")
        h2 = make_content_hash("content", "different title")
        assert h1 != h2

    def test_empty_title_ok(self):
        h = make_content_hash("content", "")
        assert len(h) == 64

    def test_empty_content_ok(self):
        h = make_content_hash("", "title")
        assert len(h) == 64

    def test_whitespace_normalised(self):
        h1 = make_content_hash("  hello world  ", "title")
        h2 = make_content_hash("hello world", "title")
        assert h1 == h2


class TestChunkId:
    def test_stable_on_repeated_calls(self):
        pid = make_page_id(CANONICAL, SOURCE)
        cid1 = make_chunk_id(pid, 0, "1.0")
        cid2 = make_chunk_id(pid, 0, "1.0")
        assert cid1 == cid2

    def test_different_index_different_id(self):
        pid = make_page_id(CANONICAL, SOURCE)
        cid0 = make_chunk_id(pid, 0, "1.0")
        cid1 = make_chunk_id(pid, 1, "1.0")
        assert cid0 != cid1

    def test_different_version_different_id(self):
        pid = make_page_id(CANONICAL, SOURCE)
        cid_v1 = make_chunk_id(pid, 0, "1.0")
        cid_v2 = make_chunk_id(pid, 0, "2.0")
        assert cid_v1 != cid_v2

    def test_different_page_different_id(self):
        pid1 = make_page_id(None, "https://eurekasolutions.in/Eureka2026/a")
        pid2 = make_page_id(None, "https://eurekasolutions.in/Eureka2026/b")
        assert make_chunk_id(pid1, 0, "1.0") != make_chunk_id(pid2, 0, "1.0")

    def test_is_64_char_hex(self):
        pid = make_page_id(CANONICAL, SOURCE)
        cid = make_chunk_id(pid, 5, "1.0")
        assert len(cid) == 64
        assert all(c in "0123456789abcdef" for c in cid)
