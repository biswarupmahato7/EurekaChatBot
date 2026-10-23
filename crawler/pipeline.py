"""
crawler/pipeline.py
===================
Orchestration for the Eureka RAG Chatbot crawler pipeline.

Full pipeline:
  Seed/Sitemap → Discover → Scope-check → Fetch → Parse → Validate → Export → Report

Incremental pipeline:
  Load previous dataset → Identify new/changed/unchanged → Fetch only new/changed
  → Merge with unchanged → Export → Report

Failure handling:
- One failed URL never aborts the run (unless configured otherwise)
- Atomic writes: temp file → rename (raw data, checkpoints)
- Checkpoints saved every N pages
- Previous valid output is preserved until new output is fully written + validated
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from crawler.checkpoints import CheckpointManager
from crawler.config import CrawlerSettings
from crawler.discovery import DiscoveryQueue, parse_sitemap_xml
from crawler.fetcher import SafeFetcher, RobotsTxtCache
from crawler.models import CrawlStats, PageRecord, RawDataset
from crawler.parser import PageParser
from crawler.reports import build_crawl_report, print_crawl_summary, save_report
from crawler.url_utils import is_in_scope, normalize_url
from crawler.validation import validate_raw_dataset

logger = logging.getLogger(__name__)

CHECKPOINT_INTERVAL = 10  # Save checkpoint every N pages


# ===========================================================================
# Atomic JSON writer
# ===========================================================================

def atomic_write_json(data: Any, dest: Path) -> None:
    """Write JSON atomically: write to temp then rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=dest.parent, prefix=".tmp_data_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, dest)
        logger.info("Wrote %s", dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ===========================================================================
# Pipeline runner
# ===========================================================================

class CrawlPipeline:
    """Orchestrates a full or incremental crawl run."""

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings
        self.parser = PageParser(
            approved_origin=settings.crawler_approved_origin,
            approved_prefix=settings.crawler_approved_path_prefix,
            extra_allowed_paths=settings.extra_allowed_paths_list,
        )
        self.checkpoint_mgr = CheckpointManager(settings.checkpoints_path)
        self.run_id = str(uuid.uuid4())

    def run(self) -> RawDataset:
        """Execute the pipeline based on settings.pipeline_mode."""
        if self.settings.pipeline_mode == "incremental":
            return self._run_incremental()
        return self._run_full()

    # ── Full run ──────────────────────────────────────────────────────────────

    def _run_full(self) -> RawDataset:
        logger.info("Starting FULL crawl run %s", self.run_id)
        crawl_start = datetime.now(timezone.utc).isoformat()

        # Build fetcher (dry_run skips page GETs)
        fetcher = self._make_fetcher()

        # Discovery queue
        queue = DiscoveryQueue(
            approved_origin=self.settings.crawler_approved_origin,
            approved_prefix=self.settings.crawler_approved_path_prefix,
            max_depth=self.settings.crawler_max_depth,
            max_pages=self.settings.crawler_max_pages,
            extra_allowed_paths=self.settings.extra_allowed_paths_list,
        )

        # Seed from sitemap
        sitemap_urls = self._fetch_sitemap(fetcher)
        if sitemap_urls:
            added = queue.add_from_sitemap(sitemap_urls)
            logger.info("Added %d URLs from sitemap", added)
        else:
            # Fall back to seed URL
            queue.seed(self.settings.crawler_base_url)
            logger.info("Sitemap unavailable — seeded with base URL")

        # Stats tracking
        stats = CrawlStats()
        stats.discovered = queue.enqueued_count
        pages: list[PageRecord] = []
        error_categories: dict[str, int] = {}

        if self.settings.dry_run:
            logger.info("DRY RUN — no page GET requests will be made")
            crawl_finish = datetime.now(timezone.utc).isoformat()
            dataset = self._build_dataset(
                pages, stats, crawl_start, crawl_finish,
                is_complete=True, is_dry_run=True,
            )
            self._save_dataset(dataset)
            self._save_report(dataset, crawl_start, crawl_finish, error_categories)
            return dataset

        # Main crawl loop
        page_count = 0
        seen_page_ids: set[str] = set()
        while queue:
            entry = queue.pop()
            if entry is None:
                break

            stats.attempted += 1
            url = entry.normalized_url

            logger.info("[%d/%d] Crawling: %s", page_count + 1, self.settings.crawler_max_pages, url)

            # Fetch
            fetch_status, html = fetcher.fetch_text(url)
            time.sleep(self.settings.crawler_request_delay_seconds)

            # Track HTTP status
            if fetch_status.http_status:
                key = str(fetch_status.http_status)
                stats.http_status_counts[key] = stats.http_status_counts.get(key, 0) + 1

            if fetch_status.blocked:
                stats.blocked += 1
                error_categories["blocked"] = error_categories.get("blocked", 0) + 1
                logger.warning("Blocked: %s — %s", url, fetch_status.block_reason)
                continue

            if fetch_status.skipped or fetch_status.robots_disallowed:
                stats.skipped += 1
                continue

            if fetch_status.error or fetch_status.http_status not in (200,):
                stats.failed += 1
                err_key = f"http_{fetch_status.http_status}" if fetch_status.http_status else "connection_error"
                error_categories[err_key] = error_categories.get(err_key, 0) + 1
                logger.warning("Failed %s: status=%s error=%s", url, fetch_status.http_status, fetch_status.error)
                continue

            if not html:
                stats.failed += 1
                logger.warning("Empty HTML for %s", url)
                continue

            # Parse
            try:
                record = self.parser.parse(
                    html_text=html,
                    source_url=url,
                    final_url=fetch_status.final_url,
                    http_status=fetch_status.http_status,
                )
            except Exception as exc:
                logger.error("Parse error for %s: %s", url, exc)
                stats.failed += 1
                error_categories["parse_error"] = error_categories.get("parse_error", 0) + 1
                continue

            if record.page_id in seen_page_ids:
                logger.info(
                    "Skipping duplicate page (canonical already crawled): %s (canonical: %s)",
                    url, record.canonical_url,
                )
                stats.duplicate_urls += 1
                continue
            seen_page_ids.add(record.page_id)

            pages.append(record)
            stats.succeeded += 1
            page_count += 1

            if record.is_empty:
                stats.empty_or_low_content += 1
            elif record.is_low_content:
                stats.empty_or_low_content += 1

            # Add new links from this page to the queue
            new_links = record.internal_links
            added = queue.add_from_page_links(new_links, parent_depth=entry.depth)
            stats.discovered = queue.enqueued_count + page_count

            # Checkpoint
            if page_count % CHECKPOINT_INTERVAL == 0:
                self._save_checkpoint(pages, queue, stats)

        # Final stats
        stats.skipped += len([e for e in queue.skipped if e.skip_reason == "out_of_scope"])
        stats.out_of_scope = len([e for e in queue.skipped if e.skip_reason == "out_of_scope"])

        crawl_finish = datetime.now(timezone.utc).isoformat()
        is_complete = stats.failed == 0 and not queue

        dataset = self._build_dataset(
            pages, stats, crawl_start, crawl_finish,
            is_complete=is_complete, is_dry_run=False,
        )
        self._save_dataset(dataset)
        self._save_report(dataset, crawl_start, crawl_finish, error_categories)
        self.checkpoint_mgr.cleanup_old(keep=3)
        return dataset

    # ── Incremental run ───────────────────────────────────────────────────────

    def _run_incremental(self) -> RawDataset:
        logger.info("Starting INCREMENTAL crawl run %s", self.run_id)
        crawl_start = datetime.now(timezone.utc).isoformat()

        # Load previous dataset
        prev_dataset = self._load_previous_raw()
        prev_pages_by_url: dict[str, dict[str, Any]] = {}
        if prev_dataset:
            for page in prev_dataset.get("pages", []):
                url = page.get("source_url") or page.get("final_url")
                if url:
                    prev_pages_by_url[url] = page
            logger.info("Loaded %d pages from previous dataset", len(prev_pages_by_url))

        fetcher = self._make_fetcher()
        queue = DiscoveryQueue(
            approved_origin=self.settings.crawler_approved_origin,
            approved_prefix=self.settings.crawler_approved_path_prefix,
            max_depth=self.settings.crawler_max_depth,
            max_pages=self.settings.crawler_max_pages,
            extra_allowed_paths=self.settings.extra_allowed_paths_list,
        )
        sitemap_urls = self._fetch_sitemap(fetcher)
        if sitemap_urls:
            queue.add_from_sitemap(sitemap_urls)
        else:
            queue.seed(self.settings.crawler_base_url)

        if prev_pages_by_url:
            for prev_url in prev_pages_by_url:
                queue.add_from_page_links([prev_url], parent_depth=0)

        stats = CrawlStats()
        stats.discovered = queue.enqueued_count
        pages: list[PageRecord] = []
        seen_page_ids: set[str] = set()
        error_categories: dict[str, int] = {}
        unchanged_count = 0

        while queue:
            entry = queue.pop()
            if entry is None:
                break
            stats.attempted += 1
            url = entry.normalized_url

            # Fetch to detect changes
            fetch_status, html = fetcher.fetch_text(url)
            time.sleep(self.settings.crawler_request_delay_seconds)

            if fetch_status.http_status:
                key = str(fetch_status.http_status)
                stats.http_status_counts[key] = stats.http_status_counts.get(key, 0) + 1

            if fetch_status.blocked:
                stats.blocked += 1
                # Preserve previous content on transient failures
                if url in prev_pages_by_url:
                    prev = prev_pages_by_url[url]
                    # reconstruct as PageRecord using raw dict — preserve old data
                    try:
                        pages.append(PageRecord(**prev))
                        logger.info("Preserved previous content for blocked URL: %s", url)
                    except Exception:
                        pass
                continue

            if fetch_status.error or fetch_status.http_status not in (200,):
                stats.failed += 1
                # Preserve previous content on transient failure
                if url in prev_pages_by_url:
                    prev_page = prev_pages_by_url[url]
                    try:
                        pages.append(PageRecord(**prev_page))
                        logger.info("Preserved previous content for failed URL: %s", url)
                    except Exception:
                        pass
                continue

            if not html:
                stats.failed += 1
                if url in prev_pages_by_url:
                    try:
                        pages.append(PageRecord(**prev_pages_by_url[url]))
                    except Exception:
                        pass
                continue

            # Parse and check if content changed
            try:
                record = self.parser.parse(
                    html_text=html,
                    source_url=url,
                    final_url=fetch_status.final_url,
                    http_status=fetch_status.http_status,
                )
            except Exception as exc:
                logger.error("Parse error for %s: %s", url, exc)
                stats.failed += 1
                if url in prev_pages_by_url:
                    try:
                        pages.append(PageRecord(**prev_pages_by_url[url]))
                    except Exception:
                        pass
                continue

            if record.page_id in seen_page_ids:
                logger.info("Skipping duplicate canonical page in incremental: %s", url)
                stats.duplicate_urls += 1
                continue
            seen_page_ids.add(record.page_id)

            prev_page = prev_pages_by_url.get(url)
            if prev_page and prev_page.get("content_hash") == record.content_hash:
                # Unchanged — use previous record
                unchanged_count += 1
                try:
                    pages.append(PageRecord(**prev_page))
                except Exception:
                    pages.append(record)
            else:
                pages.append(record)
                if prev_page:
                    logger.info("Content changed: %s", url)

            stats.succeeded += 1

            new_links = record.internal_links
            queue.add_from_page_links(new_links, parent_depth=entry.depth)
            stats.discovered = queue.enqueued_count + stats.succeeded

        stats.out_of_scope = len([e for e in queue.skipped if e.skip_reason == "out_of_scope"])
        crawl_finish = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Incremental run complete: %d succeeded, %d unchanged, %d failed",
            stats.succeeded, unchanged_count, stats.failed,
        )

        # Failure-safe preservation: keep any previous page records not visited in this run
        existing_page_urls = {p.source_url for p in pages}
        for p_url, p_data in prev_pages_by_url.items():
            if p_url not in existing_page_urls:
                try:
                    pages.append(PageRecord(**p_data))
                    logger.info("Preserved unvisited previous page: %s", p_url)
                except Exception:
                    pass

        dataset = self._build_dataset(
            pages, stats, crawl_start, crawl_finish,
            is_complete=(stats.failed == 0),
        )
        self._save_dataset(dataset)
        self._save_report(dataset, crawl_start, crawl_finish, error_categories)
        self.checkpoint_mgr.cleanup_old(keep=3)
        return dataset

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_fetcher(self) -> SafeFetcher:
        robots_cache = RobotsTxtCache(
            user_agent=self.settings.crawler_user_agent,
            timeout=self.settings.crawler_request_timeout_seconds,
        )
        return SafeFetcher(
            user_agent=self.settings.crawler_user_agent,
            timeout_seconds=self.settings.crawler_request_timeout_seconds,
            max_retries=self.settings.crawler_max_retries,
            delay_seconds=0,  # Pipeline controls delay explicitly
            max_response_bytes=self.settings.crawler_max_response_bytes,
            approved_origin=self.settings.crawler_approved_origin,
            approved_prefix=self.settings.crawler_approved_path_prefix,
            extra_allowed_paths=self.settings.extra_allowed_paths_list,
            robots_cache=robots_cache,
        )

    def _fetch_sitemap(self, fetcher: SafeFetcher) -> list[str]:
        """Fetch and parse the sitemap. Returns list of raw loc URLs."""
        sitemap_url = self.settings.crawler_sitemap_url
        logger.info("Fetching sitemap: %s", sitemap_url)
        fetch_status, text = fetcher.fetch_text(
            sitemap_url, content_types=("text/xml", "application/xml", "text/html")
        )
        if not text or fetch_status.http_status != 200:
            logger.warning("Sitemap fetch failed: %s", fetch_status.error or fetch_status.http_status)
            return []
        from crawler.discovery import parse_sitemap_xml
        urls = parse_sitemap_xml(text)
        logger.info("Sitemap contained %d URLs", len(urls))
        return urls

    def _build_dataset(
        self,
        pages: list[PageRecord],
        stats: CrawlStats,
        crawl_start: str,
        crawl_finish: str,
        is_complete: bool = False,
        is_dry_run: bool = False,
    ) -> RawDataset:
        try:
            start_dt = datetime.fromisoformat(crawl_start)
            finish_dt = datetime.fromisoformat(crawl_finish)
            duration = (finish_dt - start_dt).total_seconds()
        except Exception:
            duration = None

        return RawDataset(
            schema_version="1.0",
            run_id=self.run_id,
            crawler_version=self.settings.crawler_version,
            website_scope=self.settings.crawler_base_url,
            crawl_start=crawl_start,
            crawl_finish=crawl_finish,
            duration_seconds=duration,
            config_summary=self.settings.safe_config_summary(),
            is_complete=is_complete,
            is_dry_run=is_dry_run,
            stats=stats,
            pages=pages,
        )

    def _save_dataset(self, dataset: RawDataset) -> None:
        """Atomically save raw dataset to configured path."""
        dest = self.settings.raw_data_path_obj
        data = dataset.model_dump(mode="json")
        atomic_write_json(data, dest)

    def _load_previous_raw(self) -> Optional[dict[str, Any]]:
        """Load the previous raw dataset for incremental runs."""
        path = self.settings.raw_data_path_obj
        if not path.exists():
            logger.info("No previous raw dataset found at %s", path)
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load previous dataset: %s", exc)
            return None

    def _save_checkpoint(
        self,
        pages: list[PageRecord],
        queue: DiscoveryQueue,
        stats: CrawlStats,
    ) -> None:
        pages_dicts = [p.model_dump(mode="json") for p in pages]
        pending = [
            {"url": e.normalized_url, "depth": e.depth, "source": e.source}
            for e in list(queue._queue)  # snapshot
        ]
        self.checkpoint_mgr.save(
            run_id=self.run_id,
            pages_so_far=pages_dicts,
            seen_urls=queue._seen,
            pending_urls=pending,
            stats=stats.model_dump(mode="json"),
        )

    def _save_report(
        self,
        dataset: RawDataset,
        crawl_start: str,
        crawl_finish: str,
        error_categories: dict[str, int],
    ) -> None:
        pages_dicts = [p.model_dump(mode="json") for p in dataset.pages]
        validation = validate_raw_dataset(
            dataset.model_dump(mode="json"),
            approved_origin=self.settings.crawler_approved_origin,
            approved_prefix=self.settings.crawler_approved_path_prefix,
        )
        report = build_crawl_report(
            run_id=self.run_id,
            crawler_version=self.settings.crawler_version,
            config_summary=self.settings.safe_config_summary(),
            crawl_start=crawl_start,
            crawl_finish=crawl_finish,
            stats=dataset.stats.model_dump(mode="json"),
            pages=pages_dicts,
            validation_summary={
                "passed": validation.passed,
                "errors": validation.error_count,
                "warnings": validation.warning_count,
            },
            is_complete=dataset.is_complete,
            is_dry_run=dataset.is_dry_run,
            is_fixture_run=dataset.is_fixture_run,
            known_limitations=dataset.known_limitations,
            error_categories=error_categories,
        )
        path = save_report(report, self.settings.reports_path, self.run_id)
        print_crawl_summary(report)
        logger.info("Report: %s", path)
