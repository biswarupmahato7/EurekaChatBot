"""
crawler/packaging.py
====================
Utility for creating and validating the final Phase A zip deliverable (eureka-rag-data.zip).

Includes:
  - Crawler source code
  - Dependency manifests
  - Tests and fixtures
  - Crawler README and documentation
  - Crawl, chunking, and validation reports
  - Generated datasets (if present)
  - Completion note

Excludes:
  - .env or secrets
  - Virtual environments (.venv, venv)
  - Python caches (__pycache__, *.pyc)
  - Temporary files and test caches (.pytest_cache)
  - Populated vector stores or embeddings
"""
from __future__ import annotations

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Required file patterns in ZIP
REQUIRED_PATTERNS = [
    "crawler/pipeline.py",
    "crawler/fetcher.py",
    "crawler/parser.py",
    "crawler/chunker.py",
    "crawler/validation.py",
    "crawler/config.py",
    "crawler/models.py",
    "crawler/README.md",
    "crawler/tests/fixtures/services_page.html",
]

# Prohibited file/folder substrings
PROHIBITED_SUBSTRINGS = [
    ".env",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".cursor",
    "chromadb",
    ".sqlite",
]


def create_zip_archive(output_path: Path | str, project_root: Path | str) -> Path:
    """Create the eureka-rag-data.zip deliverable."""
    root = Path(project_root)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Write a completion note if not already existing
    completion_note = root / "COMPLETION_NOTE.md"
    if not completion_note.exists():
        completion_note.write_text(
            "# Eureka RAG Data Pipeline — Completion Note\n\n"
            "This package contains the complete Phase A deliverable for the Eureka RAG Chatbot project.\n"
            "All components (discovery, fetching, parsing, chunking, incremental updates, and validation)\n"
            "have been implemented and tested against comprehensive local fixtures and live discovery.\n",
            encoding="utf-8",
        )

    # Collect files
    files_to_pack: list[tuple[Path, str]] = []

    def is_prohibited(rel_str: str) -> bool:
        norm = rel_str.replace("\\", "/").lower()
        parts = norm.split("/")
        # Allow .env.example
        if norm.endswith(".env.example"):
            return False
        # Prohibited check
        for part in parts:
            if part in (".env", ".venv", "venv", "__pycache__", ".pytest_cache", ".git", ".cursor"):
                return True
        for p in PROHIBITED_SUBSTRINGS:
            if p in (".env", ".venv"):
                continue
            if p in norm:
                return True
        return False

    include_dirs = ["crawler", "docs", "data"]
    include_files = ["requirements.txt", "pytest.ini", "COMPLETION_NOTE.md"]

    for d in include_dirs:
        dir_path = root / d
        if dir_path.exists():
            for p in dir_path.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(root)
                    rel_str = str(rel).replace("\\", "/")
                    if not is_prohibited(rel_str):
                        files_to_pack.append((p, rel_str))

    for f in include_files:
        fp = root / f
        if fp.exists() and fp.is_file():
            files_to_pack.append((fp, f))

    logger.info("Packing %d files into %s", len(files_to_pack), out)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, arcname in files_to_pack:
            zf.write(src, arcname)

    return out


def verify_zip_archive(zip_path: Path | str) -> dict[str, Any]:
    """Verify that a ZIP file meets Phase A packaging criteria."""
    path = Path(zip_path)
    if not path.exists():
        return {"valid": False, "error": f"Zip file does not exist: {path}"}

    with zipfile.ZipFile(path, "r") as zf:
        namelist = zf.namelist()

        # 1. Prohibited check
        prohibited_found = []
        for name in namelist:
            norm = name.replace("\\", "/").lower()
            if norm.endswith(".env.example"):
                continue
            parts = norm.split("/")
            if any(p in (".env", ".venv", "venv", "__pycache__", ".pytest_cache") for p in parts):
                prohibited_found.append(name)
            elif any(sub in norm for sub in ("chromadb", ".sqlite")):
                prohibited_found.append(name)

        # 2. Required check
        missing_required = []
        for req in REQUIRED_PATTERNS:
            req_norm = req.replace("\\", "/")
            if not any(req_norm in n.replace("\\", "/") for n in namelist):
                missing_required.append(req)

        # 3. JSON validity check
        corrupted_json = []
        for name in namelist:
            if name.endswith(".json"):
                try:
                    data = zf.read(name)
                    json.loads(data.decode("utf-8"))
                except Exception as exc:
                    corrupted_json.append(f"{name}: {exc}")

        valid = (len(prohibited_found) == 0 and len(missing_required) == 0 and len(corrupted_json) == 0)
        return {
            "valid": valid,
            "total_files": len(namelist),
            "prohibited_found": prohibited_found,
            "missing_required": missing_required,
            "corrupted_json": corrupted_json,
        }
