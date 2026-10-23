"""
crawler/validation.py
=====================
Validate raw and processed JSON datasets.

Detects:
- Schema version and required fields
- Unique page/chunk IDs
- Valid in-scope source URLs
- Duplicate URLs and content hashes
- Empty/low content pages and chunks
- Over-limit chunks
- Chunks referencing nonexistent pages
- Token count validity

Exit codes:
  0 = passed (no errors)
  1 = validation errors found
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from crawler.models import ValidationIssue, ValidationReport
from crawler.url_utils import is_in_scope

logger = logging.getLogger(__name__)

_APPROVED_ORIGIN = "eurekasolutions.in"
_APPROVED_PREFIX = "/Eureka2026/"


# ===========================================================================
# Raw dataset validation
# ===========================================================================

def validate_raw_dataset(
    data: dict[str, Any],
    approved_origin: str = _APPROVED_ORIGIN,
    approved_prefix: str = _APPROVED_PREFIX,
) -> ValidationReport:
    """Validate a raw dataset dict. Returns a ValidationReport."""
    issues: list[ValidationIssue] = []

    def err(msg: str, record_id: Optional[str] = None, field: Optional[str] = None) -> None:
        issues.append(ValidationIssue(severity="error", record_id=record_id, field=field, message=msg))

    def warn(msg: str, record_id: Optional[str] = None, field: Optional[str] = None) -> None:
        issues.append(ValidationIssue(severity="warning", record_id=record_id, field=field, message=msg))

    # ── Root level ────────────────────────────────────────────────────────────
    schema_version = data.get("schema_version")
    if schema_version != "1.0":
        err(f"schema_version must be '1.0', got {schema_version!r}", field="schema_version")

    if not data.get("run_id"):
        err("run_id is missing or empty", field="run_id")

    if not data.get("crawler_version"):
        warn("crawler_version is missing", field="crawler_version")

    pages = data.get("pages", [])
    if not isinstance(pages, list):
        err("pages must be a list", field="pages")
        return ValidationReport(
            dataset="raw",
            schema_valid=False,
            total_records=0,
            error_count=len([i for i in issues if i.severity == "error"]),
            warning_count=len([i for i in issues if i.severity == "warning"]),
            issues=issues,
        )

    # ── Per-page checks ───────────────────────────────────────────────────────
    seen_page_ids: set[str] = set()
    seen_source_urls: set[str] = set()
    seen_content_hashes: set[str] = set()

    for i, page in enumerate(pages):
        pid = page.get("page_id", f"<page[{i}]>")

        # Required fields
        for field in ("page_id", "source_url", "final_url", "content_hash"):
            if not page.get(field):
                err(f"Required field '{field}' is missing or empty", record_id=pid, field=field)

        # Duplicate page_id
        page_id = page.get("page_id", "")
        if page_id:
            if page_id in seen_page_ids:
                err(f"Duplicate page_id: {page_id}", record_id=pid, field="page_id")
            seen_page_ids.add(page_id)

        # Duplicate source URL
        source_url = page.get("source_url", "")
        if source_url:
            if source_url in seen_source_urls:
                warn(f"Duplicate source_url: {source_url}", record_id=pid, field="source_url")
            seen_source_urls.add(source_url)

        # Duplicate content hash
        content_hash = page.get("content_hash", "")
        if content_hash:
            if content_hash in seen_content_hashes:
                warn(f"Duplicate content_hash: {content_hash[:16]}...", record_id=pid, field="content_hash")
            seen_content_hashes.add(content_hash)

        # URL scope check
        if source_url and not is_in_scope(source_url, approved_origin, approved_prefix):
            err(f"source_url not in approved scope: {source_url}", record_id=pid, field="source_url")

        # Empty content
        content = page.get("content", "")
        if not content or not content.strip():
            warn(f"Page has empty content", record_id=pid, field="content")

        # Missing title
        if not page.get("title"):
            warn(f"Page has no title", record_id=pid, field="title")

        # Schema version on record
        rec_schema = page.get("schema_version")
        if rec_schema and rec_schema != "1.0":
            err(f"Record schema_version must be '1.0', got {rec_schema!r}", record_id=pid)

    error_count = len([i for i in issues if i.severity == "error"])
    warning_count = len([i for i in issues if i.severity == "warning"])

    return ValidationReport(
        dataset="raw",
        schema_valid=error_count == 0,
        total_records=len(pages),
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
    )


# ===========================================================================
# Processed (chunk) dataset validation
# ===========================================================================

def validate_chunk_dataset(
    chunk_data: dict[str, Any],
    raw_data: Optional[dict[str, Any]] = None,
    max_tokens: int = 700,
) -> ValidationReport:
    """Validate a processed chunks dataset. Returns a ValidationReport."""
    issues: list[ValidationIssue] = []

    def err(msg: str, record_id: Optional[str] = None, field: Optional[str] = None) -> None:
        issues.append(ValidationIssue(severity="error", record_id=record_id, field=field, message=msg))

    def warn(msg: str, record_id: Optional[str] = None, field: Optional[str] = None) -> None:
        issues.append(ValidationIssue(severity="warning", record_id=record_id, field=field, message=msg))

    # ── Root level ────────────────────────────────────────────────────────────
    if chunk_data.get("schema_version") != "1.0":
        err(f"schema_version must be '1.0', got {chunk_data.get('schema_version')!r}")

    if not chunk_data.get("run_id"):
        err("run_id missing", field="run_id")

    # Build known page_ids from raw dataset for cross-reference
    known_page_ids: set[str] = set()
    if raw_data and isinstance(raw_data.get("pages"), list):
        for page in raw_data["pages"]:
            pid = page.get("page_id")
            if pid:
                known_page_ids.add(pid)

    chunks = chunk_data.get("chunks", [])
    if not isinstance(chunks, list):
        err("chunks must be a list", field="chunks")
        return ValidationReport(
            dataset="processed",
            schema_valid=False,
            total_records=0,
            error_count=len([i for i in issues if i.severity == "error"]),
            warning_count=len([i for i in issues if i.severity == "warning"]),
            issues=issues,
        )

    seen_chunk_ids: set[str] = set()
    max_observed_tokens = 0

    for chunk in chunks:
        cid = chunk.get("chunk_id", "<unknown>")

        # Required fields
        for field in ("chunk_id", "page_id", "source_url", "content", "token_count", "content_hash"):
            if chunk.get(field) is None or chunk.get(field) == "":
                err(f"Required field '{field}' missing or empty", record_id=cid, field=field)

        # Duplicate chunk_id
        if cid in seen_chunk_ids:
            err(f"Duplicate chunk_id: {cid}", record_id=cid, field="chunk_id")
        seen_chunk_ids.add(cid)

        # Cross-reference page_id
        page_id = chunk.get("page_id", "")
        if page_id and known_page_ids and page_id not in known_page_ids:
            err(f"chunk references non-existent page_id: {page_id}", record_id=cid, field="page_id")

        # Token count
        token_count = chunk.get("token_count", 0)
        if isinstance(token_count, int):
            if token_count > max_tokens:
                err(
                    f"chunk token_count {token_count} exceeds max {max_tokens}",
                    record_id=cid, field="token_count",
                )
            max_observed_tokens = max(max_observed_tokens, token_count)
            if token_count == 0:
                warn("chunk has zero token_count", record_id=cid, field="token_count")
        else:
            err(f"token_count must be int, got {type(token_count)}", record_id=cid, field="token_count")

        # Empty content
        content = chunk.get("content", "")
        if not content or not content.strip():
            err("chunk content is empty", record_id=cid, field="content")

        # Source URL
        if not chunk.get("source_url"):
            err("chunk missing source_url", record_id=cid, field="source_url")

    # total_chunks consistency
    declared_total = chunk_data.get("total_chunks", 0)
    actual_total = len(chunks)
    if declared_total != actual_total:
        warn(f"total_chunks {declared_total} != actual chunk count {actual_total}")

    error_count = len([i for i in issues if i.severity == "error"])
    warning_count = len([i for i in issues if i.severity == "warning"])

    return ValidationReport(
        dataset="processed",
        schema_valid=error_count == 0,
        total_records=actual_total,
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
    )


# ===========================================================================
# File-level helpers
# ===========================================================================

def load_json_file(path: str | Path) -> Optional[dict[str, Any]]:
    """Load and parse a JSON file. Returns None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, FileNotFoundError) as exc:
        logger.error("Could not load JSON from %s: %s", path, exc)
        return None


def print_validation_summary(report: ValidationReport) -> None:
    """Print a human-readable validation summary."""
    status = "PASSED" if report.passed else "FAILED"
    print()
    print(f"  Validation [{report.dataset.upper()}]: {status}")
    print(f"    Total records : {report.total_records}")
    print(f"    Errors        : {report.error_count}")
    print(f"    Warnings      : {report.warning_count}")
    if not report.passed:
        print()
        print("    Errors:")
        for issue in report.issues:
            if issue.severity == "error":
                rec = f" [{issue.record_id[:8]}...]" if issue.record_id else ""
                fld = f" ({issue.field})" if issue.field else ""
                print(f"      ERROR{rec}{fld}: {issue.message}")
        print()
        print("    Warnings (first 10):")
        warnings = [i for i in report.issues if i.severity == "warning"][:10]
        for issue in warnings:
            rec = f" [{issue.record_id[:8]}...]" if issue.record_id else ""
            fld = f" ({issue.field})" if issue.field else ""
            print(f"      WARN{rec}{fld}: {issue.message}")
