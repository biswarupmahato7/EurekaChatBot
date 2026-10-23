"""
crawler/cli/run_pipeline.py
===========================
CLI for running the complete crawler pipeline (crawl → chunk → validate → report).

Usage:
    python -m crawler.cli.run_pipeline [options]

PowerShell:
    .\.venv\Scripts\python.exe -m crawler.cli.run_pipeline --mode full
    .\.venv\Scripts\python.exe -m crawler.cli.run_pipeline --mode incremental
    .\.venv\Scripts\python.exe -m crawler.cli.run_pipeline --mode full --max-pages 103
    .\.venv\Scripts\python.exe -m crawler.cli.run_pipeline --dry-run

Exit codes:
  0 = pipeline completed successfully
  1 = validation errors or partial completion
  2 = critical failure
"""
from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m crawler.cli.run_pipeline",
        description=(
            "Run the full Eureka RAG Chatbot data pipeline: "
            "crawl -> chunk -> validate -> report"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full crawl pipeline (all 103 sitemap pages)
  python -m crawler.cli.run_pipeline --mode full

  # Incremental update (only fetch changed pages)
  python -m crawler.cli.run_pipeline --mode incremental

  # Limited crawl
  python -m crawler.cli.run_pipeline --mode full --max-pages 50

  # Dry run (no page fetches)
  python -m crawler.cli.run_pipeline --dry-run
""",
    )
    parser.add_argument(
        "--mode", choices=["full", "incremental"], default="full",
        help="Pipeline mode: full rebuild or incremental update (default: full)",
    )
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None, help="Request delay in seconds")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument(
        "--skip-chunking", action="store_true", default=False,
        help="Stop after crawling, skip chunking step",
    )
    parser.add_argument(
        "--skip-validation", action="store_true", default=False,
        help="Skip post-pipeline validation",
    )
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from crawler.logging_config import setup_logging
    setup_logging(level=args.log_level)

    import logging
    logger = logging.getLogger("run_pipeline")

    try:
        overrides: dict = {"pipeline_mode": args.mode}
        if args.max_pages: overrides["crawler_max_pages"] = args.max_pages
        if args.delay: overrides["crawler_request_delay_seconds"] = args.delay
        if args.dry_run: overrides["dry_run"] = True

        from crawler.config import get_settings
        settings = get_settings(**overrides)

        # ── Step 1: Crawl ────────────────────────────────────────────────────
        logger.info("=== STEP 1/3: Crawl (%s mode) ===", args.mode.upper())
        from crawler.pipeline import CrawlPipeline
        pipeline = CrawlPipeline(settings)
        dataset = pipeline.run()
        logger.info(
            "Crawl complete: %d pages | complete=%s",
            len(dataset.pages), dataset.is_complete,
        )

        if args.dry_run or args.skip_chunking:
            logger.info("Skipping chunking (dry_run=%s skip_chunking=%s)", args.dry_run, args.skip_chunking)
            return 0

        # ── Step 2: Chunk ────────────────────────────────────────────────────
        logger.info("=== STEP 2/3: Chunk ===")
        from crawler.cli.create_chunks import main as chunk_main
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["create_chunks"]
        chunk_rc = chunk_main()
        _sys.argv = old_argv
        if chunk_rc != 0:
            logger.error("Chunking failed with exit code %d", chunk_rc)
            return 1

        if args.skip_validation:
            logger.info("Skipping validation")
            return 0

        # ── Step 3: Validate ─────────────────────────────────────────────────
        logger.info("=== STEP 3/3: Validate ===")
        from crawler.cli.validate_data import main as validate_main
        _sys.argv = ["validate_data", "--dataset", "both"]
        validate_rc = validate_main()
        _sys.argv = old_argv

        if validate_rc != 0:
            logger.warning("Validation found issues (exit %d)", validate_rc)
            return 1

        logger.info("Pipeline complete — all steps passed.")
        return 0

    except Exception as exc:
        import traceback
        logging.getLogger("run_pipeline").error("Fatal error: %s", exc)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
