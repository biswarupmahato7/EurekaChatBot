"""
crawler/cli/crawl_website.py
============================
CLI for executing the web crawler.

Usage:
    python -m crawler.cli.crawl_website [options]

PowerShell:
    .\.venv\Scripts\python.exe -m crawler.cli.crawl_website --help
    .\.venv\Scripts\python.exe -m crawler.cli.crawl_website --max-pages 50 --dry-run
    .\.venv\Scripts\python.exe -m crawler.cli.crawl_website --max-pages 103
"""
from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m crawler.cli.crawl_website",
        description=(
            "Crawl the Eureka Solutions website and save structured page records "
            "to data/raw/eureka_website_data.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run — discover URLs, no page GETs
  python -m crawler.cli.crawl_website --dry-run

  # Conservative crawl (50 pages)
  python -m crawler.cli.crawl_website --max-pages 50

  # Full crawl (all 103 sitemap pages)
  python -m crawler.cli.crawl_website --max-pages 103

  # Verbose logging
  python -m crawler.cli.crawl_website --log-level DEBUG

Exit codes:
  0 = crawl completed (may be partial)
  1 = configuration error or critical failure
""",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Maximum pages to crawl (default: from config/env, typically 150)",
    )
    parser.add_argument(
        "--delay", type=float, default=None,
        help="Seconds between requests (default: 1.5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Discover URLs without fetching pages",
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--raw-output", type=str, default=None,
        help="Override output path for raw JSON dataset",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from crawler.logging_config import setup_logging
    setup_logging(level=args.log_level)

    import logging
    logger = logging.getLogger("crawl_website")

    try:
        overrides: dict = {}
        if args.max_pages is not None:
            overrides["crawler_max_pages"] = args.max_pages
        if args.delay is not None:
            overrides["crawler_request_delay_seconds"] = args.delay
        if args.dry_run:
            overrides["dry_run"] = True
        if args.raw_output:
            overrides["raw_data_path"] = args.raw_output

        from crawler.config import get_settings
        settings = get_settings(**overrides)

        logger.info(
            "Starting crawl | mode=%s | dry_run=%s | max_pages=%d",
            settings.pipeline_mode, settings.dry_run, settings.crawler_max_pages,
        )

        from crawler.pipeline import CrawlPipeline
        pipeline = CrawlPipeline(settings)
        dataset = pipeline.run()

        logger.info(
            "Crawl done | pages=%d | succeeded=%d | failed=%d | status=%s",
            len(dataset.pages),
            dataset.stats.succeeded,
            dataset.stats.failed,
            "complete" if dataset.is_complete else "partial",
        )
        return 0

    except Exception as exc:
        import traceback
        logging.getLogger("crawl_website").error("Fatal error: %s", exc)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
