"""
crawler/cli/validate_data.py
============================
CLI for validating raw and processed datasets.

Usage:
    python -m crawler.cli.validate_data [options]

PowerShell:
    .\.venv\Scripts\python.exe -m crawler.cli.validate_data --help
    .\.venv\Scripts\python.exe -m crawler.cli.validate_data --dataset raw
    .\.venv\Scripts\python.exe -m crawler.cli.validate_data --dataset chunks
    .\.venv\Scripts\python.exe -m crawler.cli.validate_data --dataset both

Exit codes:
  0 = validation passed
  1 = validation errors found
  2 = file not found or unreadable
"""
from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m crawler.cli.validate_data",
        description="Validate raw and/or processed JSON datasets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m crawler.cli.validate_data --dataset raw
  python -m crawler.cli.validate_data --dataset chunks
  python -m crawler.cli.validate_data --dataset both
  python -m crawler.cli.validate_data --raw-path /custom/path/data.json
""",
    )
    parser.add_argument(
        "--dataset", choices=["raw", "chunks", "both"], default="both",
        help="Which dataset to validate (default: both)",
    )
    parser.add_argument("--raw-path", type=str, default=None, help="Override raw dataset path")
    parser.add_argument("--chunks-path", type=str, default=None, help="Override chunks dataset path")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from crawler.logging_config import setup_logging
    setup_logging(level=args.log_level)

    import logging
    logger = logging.getLogger("validate_data")

    from crawler.config import get_settings
    settings = get_settings()

    from pathlib import Path
    from crawler.validation import (
        load_json_file, validate_raw_dataset, validate_chunk_dataset,
        print_validation_summary,
    )

    raw_path = Path(args.raw_path or settings.raw_data_path)
    chunks_path = Path(args.chunks_path or settings.processed_data_path)

    any_error = False

    # Validate raw dataset
    if args.dataset in ("raw", "both"):
        if not raw_path.exists():
            logger.error("Raw dataset not found: %s", raw_path)
            return 2
        raw_data = load_json_file(raw_path)
        if raw_data is None:
            logger.error("Could not parse raw dataset JSON: %s", raw_path)
            return 2
        raw_report = validate_raw_dataset(
            raw_data,
            approved_origin=settings.crawler_approved_origin,
            approved_prefix=settings.crawler_approved_path_prefix,
        )
        print_validation_summary(raw_report)
        if not raw_report.passed:
            any_error = True

    # Validate chunks dataset
    if args.dataset in ("chunks", "both"):
        if not chunks_path.exists():
            logger.error("Chunks dataset not found: %s", chunks_path)
            return 2
        chunk_data = load_json_file(chunks_path)
        if chunk_data is None:
            logger.error("Could not parse chunks dataset JSON: %s", chunks_path)
            return 2

        raw_data_for_xref = None
        if args.dataset == "both" and raw_path.exists():
            raw_data_for_xref = load_json_file(raw_path)

        chunk_report = validate_chunk_dataset(
            chunk_data,
            raw_data=raw_data_for_xref,
            max_tokens=settings.chunk_max_tokens,
        )
        print_validation_summary(chunk_report)
        if not chunk_report.passed:
            any_error = True

    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
