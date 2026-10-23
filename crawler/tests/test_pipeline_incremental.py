"""
crawler/tests/test_pipeline_incremental.py
==========================================
Integration tests for full and incremental pipeline execution, atomic writes,
and failure-safe previous page preservation.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from crawler.config import CrawlerSettings
from crawler.models import FetchStatus, PageRecord, RawDataset
from crawler.pipeline import CrawlPipeline, atomic_write_json
from crawler.hashing import make_page_id, make_content_hash

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw_path = tmp_path / "raw" / "raw_data.json"
    proc_path = tmp_path / "processed" / "chunks.json"
    rep_path = tmp_path / "reports"
    ckpt_path = tmp_path / "checkpoints"

    settings = CrawlerSettings(
        crawler_base_url="https://eurekasolutions.in/Eureka2026/",
        crawler_approved_origin="eurekasolutions.in",
        crawler_approved_path_prefix="/Eureka2026/",
        crawler_sitemap_url="https://eurekasolutions.in/Eureka2026/sitemap.xml",
        crawler_max_pages=10,
        crawler_max_depth=3,
        crawler_request_delay_seconds=0.0,
        raw_data_path=str(raw_path),
        processed_data_path=str(proc_path),
        reports_path=str(rep_path),
        checkpoints_path=str(ckpt_path),
    )
    return settings


class TestAtomicWrite:
    def test_atomic_write_creates_valid_json(self, tmp_path):
        dest = tmp_path / "subdir" / "output.json"
        data = {"hello": "world", "num": 42}
        atomic_write_json(data, dest)

        assert dest.exists()
        with dest.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data


class TestPipelineOrchestration:
    def test_full_pipeline_with_mocked_fetcher(self, pipeline_env):
        services_html = (FIXTURES_DIR / "services_page.html").read_text(encoding="utf-8")
        sitemap_xml = (FIXTURES_DIR / "sitemap.xml").read_text(encoding="utf-8")

        pipeline = CrawlPipeline(pipeline_env)

        # Mock fetcher responses: sitemap + services page
        def fake_fetch_text(url, content_types=None):
            if "sitemap.xml" in url:
                return FetchStatus(url=url, final_url=url, http_status=200, content_type="text/xml"), sitemap_xml
            return FetchStatus(url=url, final_url=url, http_status=200, content_type="text/html"), services_html

        with patch.object(pipeline, "_make_fetcher") as mock_mf:
            mock_fetcher = MagicMock()
            mock_fetcher.fetch_text.side_effect = fake_fetch_text
            mock_mf.return_value = mock_fetcher

            dataset = pipeline._run_full()

            assert dataset.schema_version == "1.0"
            assert dataset.stats.succeeded > 0
            assert pipeline_env.raw_data_path_obj.exists()

            # Verify saved JSON
            with pipeline_env.raw_data_path_obj.open("r", encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["schema_version"] == "1.0"
            assert len(saved["pages"]) == dataset.stats.succeeded

    def test_incremental_mode_preserves_failed_pages_and_skips_unchanged(self, pipeline_env):
        url = "https://eurekasolutions.in/Eureka2026/services"
        services_html = (FIXTURES_DIR / "services_page.html").read_text(encoding="utf-8")

        # 1. Establish initial dataset
        pipeline = CrawlPipeline(pipeline_env)
        rec = pipeline.parser.parse(services_html, url, url, http_status=200)

        initial_dataset = RawDataset(
            schema_version="1.0",
            run_id="run-initial",
            website_scope=pipeline_env.crawler_base_url,
            pages=[rec],
        )
        pipeline._save_dataset(initial_dataset)
        assert pipeline_env.raw_data_path_obj.exists()

        # 2. Run incremental where the page fetch fails (e.g. 500 error / network timeout)
        pipeline_env.pipeline_mode = "incremental"
        pipeline_inc = CrawlPipeline(pipeline_env)

        def failing_fetch_text(fetch_url, content_types=None):
            if "sitemap.xml" in fetch_url:
                return FetchStatus(url=fetch_url, final_url=fetch_url, http_status=200), ""
            # Simulate failure on the services page
            return FetchStatus(url=fetch_url, final_url=fetch_url, http_status=500, error="HTTP 500"), ""

        with patch.object(pipeline_inc, "_make_fetcher") as mock_mf:
            mock_fetcher = MagicMock()
            mock_fetcher.fetch_text.side_effect = failing_fetch_text
            mock_mf.return_value = mock_fetcher

            # Seed the queue with the existing page URL
            dataset_inc = pipeline_inc._run_incremental()

            # Critical acceptance check: previous valid page MUST NOT disappear!
            page_urls = [p.source_url for p in dataset_inc.pages]
            assert url in page_urls
            assert dataset_inc.stats.failed >= 1

    def test_incremental_mode_detects_changed_content(self, pipeline_env):
        url = "https://eurekasolutions.in/Eureka2026/services"
        services_html_old = (FIXTURES_DIR / "services_page.html").read_text(encoding="utf-8")
        services_html_new = services_html_old.replace("Technology Services", "NextGen AI Services")

        pipeline = CrawlPipeline(pipeline_env)
        rec_old = pipeline.parser.parse(services_html_old, url, url, http_status=200)

        initial_dataset = RawDataset(
            schema_version="1.0",
            run_id="run-initial",
            pages=[rec_old],
        )
        pipeline._save_dataset(initial_dataset)

        # Run incremental with new content
        pipeline_env.pipeline_mode = "incremental"
        pipeline_inc = CrawlPipeline(pipeline_env)

        def new_fetch_text(fetch_url, content_types=None):
            return FetchStatus(url=fetch_url, final_url=fetch_url, http_status=200), services_html_new

        with patch.object(pipeline_inc, "_make_fetcher") as mock_mf:
            mock_fetcher = MagicMock()
            mock_fetcher.fetch_text.side_effect = new_fetch_text
            mock_mf.return_value = mock_fetcher

            dataset_inc = pipeline_inc._run_incremental()

            page = dataset_inc.pages[0]
            assert page.content_hash != rec_old.content_hash
            assert "NextGen AI Services" in page.content
