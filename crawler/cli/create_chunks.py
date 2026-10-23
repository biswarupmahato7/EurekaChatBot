"""
crawler/cli/create_chunks.py
============================
CLI for generating token-aware chunks from the raw crawl dataset.

Usage:
    python -m crawler.cli.create_chunks [options]

PowerShell:
    .\.venv\Scripts\python.exe -m crawler.cli.create_chunks --help
    .\.venv\Scripts\python.exe -m crawler.cli.create_chunks
    .\.venv\Scripts\python.exe -m crawler.cli.create_chunks --target-tokens 500 --overlap 75
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m crawler.cli.create_chunks",
        description=(
            "Generate token-aware chunks from data/raw/eureka_website_data.json "
            "and save to data/processed/eureka_website_chunks.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default chunking (500 target, 75 overlap, 700 max)
  python -m crawler.cli.create_chunks

  # Custom parameters
  python -m crawler.cli.create_chunks --target-tokens 400 --overlap 50

  # Verbose
  python -m crawler.cli.create_chunks --log-level DEBUG
""",
    )
    parser.add_argument("--raw-input", type=str, default=None, help="Override raw dataset path")
    parser.add_argument("--output", type=str, default=None, help="Override processed output path")
    parser.add_argument("--target-tokens", type=int, default=None, help="Target chunk size in tokens")
    parser.add_argument("--overlap", type=int, default=None, help="Overlap tokens between chunks")
    parser.add_argument("--max-tokens", type=int, default=None, help="Hard maximum tokens per chunk")
    parser.add_argument("--min-tokens", type=int, default=None, help="Soft minimum tokens per chunk")
    parser.add_argument("--tokenizer", type=str, default=None, help="tiktoken encoding name")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from crawler.logging_config import setup_logging
    setup_logging(level=args.log_level)
    logger = logging.getLogger("create_chunks")

    try:
        overrides: dict = {}
        if args.target_tokens: overrides["chunk_target_tokens"] = args.target_tokens
        if args.overlap: overrides["chunk_overlap_tokens"] = args.overlap
        if args.max_tokens: overrides["chunk_max_tokens"] = args.max_tokens
        if args.min_tokens: overrides["chunk_min_tokens"] = args.min_tokens
        if args.tokenizer: overrides["tokenizer"] = args.tokenizer

        from crawler.config import get_settings
        settings = get_settings(**overrides)

        raw_path = Path(args.raw_input or settings.raw_data_path)
        out_path = Path(args.output or settings.processed_data_path)

        if not raw_path.exists():
            logger.error("Raw dataset not found: %s", raw_path)
            logger.error("Run the crawler first: python -m crawler.cli.crawl_website")
            return 1

        logger.info("Loading raw dataset from %s", raw_path)
        with raw_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)

        pages_data = raw_data.get("pages", [])
        logger.info("Loaded %d pages", len(pages_data))

        from crawler.chunker import Chunker
        from crawler.models import PageRecord, ChunkDataset, ChunkRecord

        chunker = Chunker(
            encoding_name=settings.tokenizer,
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
            max_tokens=settings.chunk_max_tokens,
            min_tokens=settings.chunk_min_tokens,
            chunking_version=settings.chunking_version,
        )

        all_chunks: list[ChunkRecord] = []
        seen_pids: set[str] = set()
        seen_chunk_ids: set[str] = set()
        skipped_pages = 0

        for page_dict in pages_data:
            pid = page_dict.get("page_id")
            if pid and pid in seen_pids:
                logger.warning("Skipping duplicate page_id in raw dataset: %s", pid)
                skipped_pages += 1
                continue
            if pid:
                seen_pids.add(pid)

            try:
                page = PageRecord(**page_dict)
            except Exception as exc:
                logger.warning("Skipping invalid page record: %s", exc)
                skipped_pages += 1
                continue

            try:
                chunks = chunker.chunk_page(page)
                for c in chunks:
                    if c.chunk_id in seen_chunk_ids:
                        logger.warning("Skipping duplicate chunk_id: %s", c.chunk_id)
                        continue
                    seen_chunk_ids.add(c.chunk_id)
                    all_chunks.append(c)
            except Exception as exc:
                logger.error("Chunking error for %s: %s", page.source_url, exc)
                skipped_pages += 1

        max_tokens_seen = max((c.token_count for c in all_chunks), default=0)
        logger.info(
            "Chunking complete: %d chunks from %d pages | max_tokens=%d",
            len(all_chunks), len(pages_data) - skipped_pages, max_tokens_seen,
        )

        # Compute source raw hash
        import hashlib
        raw_content = raw_path.read_bytes()
        source_hash = hashlib.sha256(raw_content).hexdigest()

        dataset = ChunkDataset(
            schema_version="1.0",
            run_id=str(uuid.uuid4()),
            crawler_version=settings.crawler_version,
            source_raw_run_id=raw_data.get("run_id"),
            source_raw_hash=source_hash,
            chunking_config=settings.chunking_config_dict(),
            created_at=datetime.now(timezone.utc).isoformat(),
            total_chunks=len(all_chunks),
            total_pages=len(pages_data) - skipped_pages,
            chunks=all_chunks,
        )

        # Atomic write
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = dataset.model_dump(mode="json")
        fd, tmp = tempfile.mkstemp(dir=out_path.parent, prefix=".tmp_chunks_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, out_path)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise

        logger.info("Chunks saved to %s", out_path)

        if skipped_pages > 0:
            logger.warning("Skipped %d pages due to errors", skipped_pages)

        return 0

    except Exception as exc:
        import traceback
        logging.getLogger("create_chunks").error("Fatal error: %s", exc)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
