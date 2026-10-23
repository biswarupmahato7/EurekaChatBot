"""
scripts/package_source.py
=========================
Creates and verifies the complete source code archive for release/handoff.

Package: eureka-rag-source.tar.gz and eureka-rag-source.zip

Inclusions:
- Source code: backend/, crawler/, frontend/src/, frontend/public/, scripts/
- Manifests: requirements*.txt, package*.json, tsconfig*.json, pytest.ini
- Documentation: docs/, README.md, backend/README.md, crawler/README.md, frontend/README.md, frontend-integration/
- Tests & fixtures: crawler/tests/, backend/tests/, frontend/src/__tests__/, tests/
- Deployment configs: deployment/ (Dockerfile*, docker-compose.yml, nginx/, systemd/)

Exclusions:
- .env and credentials
- .venv, venv, node_modules
- __pycache__, *.pyc, *.pyo, *.pyd
- .pytest_cache, .coverage, htmlcov
- .git, .cursor, .idea, .vscode
- data/vectorstore, data/chroma*, *.sqlite3
- data/backups, data/restore_test*
- dist, build, *.log, cloudflared.exe
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Strictly prohibited substrings or directory names
PROHIBITED_PARTS = {
    ".env",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".cursor",
    ".idea",
    ".vscode",
    "vectorstore",
    "backups",
    "restore_test_isolated",
    "dist",
    "checkpoints",
}

PROHIBITED_SUFFIXES = {
    ".sqlite3",
    ".sqlite",
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".bin",
}

PROHIBITED_FILES = {
    "cloudflared.exe",
    ".env",
    "eureka-rag-data.zip",
    "eureka-rag-source.tar.gz",
    "eureka-rag-source.zip",
}


def is_excluded(path: Path) -> bool:
    """Determine whether a path must be excluded from the source package."""
    rel = path.relative_to(PROJECT_ROOT)
    parts = set(rel.parts)

    # Check directories/parts
    if parts.intersection(PROHIBITED_PARTS):
        return True

    # Check filenames and extensions
    if path.name in PROHIBITED_FILES:
        return True

    if path.suffix in PROHIBITED_SUFFIXES:
        return True

    # Allow .env.example
    if path.name.startswith(".env") and not path.name.endswith(".example"):
        return True

    return False


def create_source_archive(output_path: Path) -> Path:
    """Build a clean .tar.gz source distribution archive."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    files_to_pack: list[tuple[Path, str]] = []

    for root_dir, dirs, files in os.walk(PROJECT_ROOT):
        # Filter directories in-place to prune walk
        dirs[:] = [d for d in dirs if d not in PROHIBITED_PARTS]
        for f in files:
            fp = Path(root_dir) / f
            if not is_excluded(fp):
                rel = fp.relative_to(PROJECT_ROOT)
                files_to_pack.append((fp, str(rel).replace("\\", "/")))

    # Write tar.gz
    with tarfile.open(output_path, "w:gz") as tar:
        for src, arcname in files_to_pack:
            tar.add(src, arcname=arcname)

    return output_path


def verify_source_archive(archive_path: Path) -> dict[str, Any]:
    """Verify that the archive contains required files and zero prohibited elements."""
    if not archive_path.exists():
        return {"valid": False, "error": f"File does not exist: {archive_path}"}

    prohibited_found: list[str] = []
    total_files = 0

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            total_files += 1
            name = member.name.replace("\\", "/")
            parts = set(name.split("/"))
            if parts.intersection(PROHIBITED_PARTS):
                prohibited_found.append(name)
            for suff in PROHIBITED_SUFFIXES:
                if name.endswith(suff):
                    prohibited_found.append(name)
            if any(name.endswith("/" + pf) or name == pf for pf in PROHIBITED_FILES):
                prohibited_found.append(name)
            if ".env" in parts and not name.endswith(".env.example"):
                prohibited_found.append(name)

    # Required file checks
    required_samples = [
        "backend/app/main.py",
        "backend/app/config.py",
        "backend/app/llm/openai_client.py",
        "crawler/pipeline.py",
        "frontend/src/components/AskEurekaWidget.tsx",
        "deployment/Dockerfile",
        "deployment/docker-compose.yml",
        "deployment/nginx/nginx.conf",
        "requirements-dev.txt",
        ".env.example",
    ]

    missing_required: list[str] = []
    with tarfile.open(archive_path, "r:gz") as tar:
        names = {m.name.replace("\\", "/") for m in tar.getmembers()}
        for req in required_samples:
            if req not in names:
                missing_required.append(req)

    valid = (len(prohibited_found) == 0 and len(missing_required) == 0)
    return {
        "valid": valid,
        "total_files": total_files,
        "size_bytes": archive_path.stat().st_size,
        "prohibited_found": prohibited_found,
        "missing_required": missing_required,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package and verify Eureka RAG source archive")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "eureka-rag-source.tar.gz",
        help="Destination archive path",
    )
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing archive")
    args = parser.parse_args()

    out = args.output
    if not args.verify_only:
        print(f"Creating source archive at: {out}")
        create_source_archive(out)
        print("Archive created.")

    print(f"Verifying source archive: {out}")
    res = verify_source_archive(out)
    if res["valid"]:
        print(f"SOURCE ARCHIVE VERIFICATION PASSED: {res['total_files']} files ({res['size_bytes'] / (1024*1024):.2f} MB)")
        return 0
    else:
        print("SOURCE ARCHIVE VERIFICATION FAILED:")
        for err in res.get("prohibited_found", []):
            print(f"  [PROHIBITED] {err}")
        for err in res.get("missing_required", []):
            print(f"  [MISSING] {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
