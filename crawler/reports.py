"""
crawler/reports.py
==================
Report generation for crawl runs and validation results.

Reports are:
- Machine-readable: JSON saved to data/reports/
- Human-readable: summary printed to stdout
- Honest: counts come from actual pipeline events, never fabricated

A partial or fixture run is explicitly labeled as such.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_crawl_report(
    run_id: str,
    crawler_version: str,
    config_summary: dict[str, Any],
    crawl_start: str,
    crawl_finish: str,
    stats: dict[str, Any],
    pages: list[dict[str, Any]],
    validation_summary: Optional[dict[str, Any]] = None,
    is_complete: bool = False,
    is_dry_run: bool = False,
    is_fixture_run: bool = False,
    known_limitations: Optional[list[str]] = None,
    error_categories: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Build the machine-readable crawl report dict."""

    # Run status label
    if is_dry_run:
        run_status = "dry_run"
    elif is_fixture_run:
        run_status = "fixture_run"
    elif is_complete:
        run_status = "complete"
    else:
        run_status = "partial"

    # Duration
    try:
        from datetime import datetime
        start_dt = datetime.fromisoformat(crawl_start)
        finish_dt = datetime.fromisoformat(crawl_finish)
        duration = (finish_dt - start_dt).total_seconds()
    except Exception:
        duration = None

    # HTTP status breakdown from pages
    http_status_counts: dict[str, int] = {}
    for page in pages:
        status = str(page.get("http_status", "unknown"))
        http_status_counts[status] = http_status_counts.get(status, 0) + 1

    return {
        "report_version": "1.0",
        "run_id": run_id,
        "crawler_version": crawler_version,
        "run_status": run_status,
        "crawl_start": crawl_start,
        "crawl_finish": crawl_finish,
        "duration_seconds": duration,
        "config_summary": config_summary,
        "stats": stats,
        "http_status_breakdown": http_status_counts,
        "page_count": len(pages),
        "empty_pages": sum(1 for p in pages if p.get("is_empty")),
        "low_content_pages": sum(1 for p in pages if p.get("is_low_content")),
        "pages_with_warnings": sum(1 for p in pages if p.get("warnings")),
        "validation": validation_summary or {},
        "error_categories": error_categories or {},
        "known_limitations": known_limitations or [],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def save_report(report: dict[str, Any], reports_dir: str | Path, run_id: str) -> Path:
    """Save a crawl report JSON atomically. Returns the saved path."""
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    out_path = reports_path / f"crawl_report_{run_id}.json"

    fd, tmp_path = tempfile.mkstemp(dir=reports_path, prefix=".tmp_report_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, out_path)
        logger.info("Report saved: %s", out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return out_path


def print_crawl_summary(report: dict[str, Any]) -> None:
    """Print a human-readable crawl summary to stdout."""
    stats = report.get("stats", {})
    print()
    print("=" * 60)
    print("  EUREKA RAG CHATBOT — CRAWL REPORT")
    print("=" * 60)
    print(f"  Run ID     : {report.get('run_id', 'unknown')}")
    print(f"  Status     : {report.get('run_status', 'unknown').upper()}")
    print(f"  Start      : {report.get('crawl_start', '?')}")
    print(f"  Finish     : {report.get('crawl_finish', '?')}")
    dur = report.get("duration_seconds")
    print(f"  Duration   : {f'{dur:.1f}s' if dur is not None else '?'}")
    print()
    print("  URL Statistics:")
    print(f"    Discovered   : {stats.get('discovered', 0)}")
    print(f"    Attempted    : {stats.get('attempted', 0)}")
    print(f"    Succeeded    : {stats.get('succeeded', 0)}")
    print(f"    Failed       : {stats.get('failed', 0)}")
    print(f"    Skipped      : {stats.get('skipped', 0)}")
    print(f"    Blocked      : {stats.get('blocked', 0)}")
    print(f"    Out of scope : {stats.get('out_of_scope', 0)}")
    print()
    print(f"  Pages extracted: {report.get('page_count', 0)}")
    print(f"  Empty pages    : {report.get('empty_pages', 0)}")
    print(f"  Low content    : {report.get('low_content_pages', 0)}")
    print(f"  With warnings  : {report.get('pages_with_warnings', 0)}")

    http_breakdown = report.get("http_status_breakdown", {})
    if http_breakdown:
        print()
        print("  HTTP Status Breakdown:")
        for code, count in sorted(http_breakdown.items()):
            print(f"    {code}: {count}")

    limitations = report.get("known_limitations", [])
    if limitations:
        print()
        print("  Known Limitations:")
        for lim in limitations:
            print(f"    - {lim}")

    print("=" * 60)
    print()
