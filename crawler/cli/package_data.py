"""
crawler/cli/package_data.py
===========================
CLI for creating and verifying the final Phase A deliverable: eureka-rag-data.zip.

Usage:
    python -m crawler.cli.package_data [options]

PowerShell:
    .\.venv\Scripts\python.exe -m crawler.cli.package_data
    .\.venv\Scripts\python.exe -m crawler.cli.package_data --verify-only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m crawler.cli.package_data",
        description="Package and verify eureka-rag-data.zip Phase A deliverable",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eureka-rag-data.zip",
        help="Path for destination ZIP file (default: eureka-rag-data.zip)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        default=False,
        help="Only verify existing zip without re-creating",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).parent.parent.parent
    zip_path = Path(args.output)
    if not zip_path.is_absolute():
        zip_path = project_root / zip_path

    from crawler.packaging import create_zip_archive, verify_zip_archive

    if not args.verify_only:
        print(f"Creating zip deliverable at: {zip_path}")
        create_zip_archive(zip_path, project_root)
        print("Archive created successfully.")

    print(f"Verifying zip deliverable: {zip_path}")
    result = verify_zip_archive(zip_path)

    if not result.get("valid"):
        print("ZIP VERIFICATION FAILED:")
        for err in result.get("prohibited_found", []):
            print(f"  [PROHIBITED] {err}")
        for missing in result.get("missing_required", []):
            print(f"  [MISSING] {missing}")
        for corrupted in result.get("corrupted_json", []):
            print(f"  [CORRUPTED JSON] {corrupted}")
        if result.get("error"):
            print(f"  [ERROR] {result['error']}")
        return 1

    print("ZIP VERIFICATION PASSED:")
    print(f"  Total files packed : {result['total_files']}")
    print(f"  Prohibited items   : 0")
    print(f"  Missing required   : 0")
    print(f"  Valid JSON files   : All parsed cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
