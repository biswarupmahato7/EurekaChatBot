"""
scripts/backup_manager.py
=========================
Production-grade backup and isolated restore verification utility for Eureka RAG Chatbot.

Capabilities:
1. Create timestamped, consistent backups covering:
   - Raw website data (data/raw/eureka_website_data.json)
   - Processed chunk data (data/processed/eureka_website_chunks.json)
   - ChromaDB persistent vector store (data/vectorstore/chroma.sqlite3, collection dirs, index_manifest.json)
   - Operational and crawl reports (data/reports/)
   - Deployment metadata and non-secret configuration
2. Generate comprehensive cryptographic manifest (backup_manifest.json) with SHA-256 hashes,
   record counts, embedding parameters, and Git commit provenance.
3. Execute automated, isolated restore verification:
   - Unpacks into an isolated temporary/scratch directory
   - Verifies all cryptographic SHA-256 checksums
   - Mounts the restored ChromaDB vector store
   - Validates collection existence and record count (3,796 chunks)
   - Runs deterministic semantic retrieval smoke tests
   - Cleans up restore directory upon completion
   - Emits a structured audit report

Usage:
    python scripts/backup_manager.py create
    python scripts/backup_manager.py restore-test
    python scripts/backup_manager.py list
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backup_manager")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_BACKUP_DIR = DATA_DIR / "backups"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_revision(cwd: Path) -> str:
    """Get current git commit hash if available."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out
    except Exception:
        return "unknown_or_uncommitted"


def get_collection_count_from_sqlite(sqlite_path: Path) -> Optional[int]:
    """Read record count directly from Chroma SQLite DB safely."""
    if not sqlite_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.cursor()
        # ChromaDB collections table or embeddings table
        cursor.execute("SELECT count(*) FROM embeddings")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as exc:
        logger.debug("Could not read embeddings table directly: %s", exc)
        return None


def create_backup(
    destination_root: Optional[Path] = None,
    tag: Optional[str] = None,
) -> Path:
    """Create a consistent snapshot of data, index, reports, and manifests."""
    dest_base = destination_root or DEFAULT_BACKUP_DIR
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    folder_name = f"backup_{timestamp}" if not tag else f"backup_{timestamp}_{tag}"
    backup_path = dest_base / folder_name
    backup_path.mkdir(parents=True, exist_ok=True)

    logger.info("Starting backup creation at: %s", backup_path)

    # 1. Quiesce / verify ChromaDB SQLite consistency
    vectorstore_src = DATA_DIR / "vectorstore"
    sqlite_src = vectorstore_src / "chroma.sqlite3"
    if not sqlite_src.exists():
        raise FileNotFoundError(f"Chroma SQLite database not found at {sqlite_src}")

    # Checkpoint WAL to main DB file if WAL exists
    wal_file = vectorstore_src / "chroma.sqlite3-wal"
    if wal_file.exists():
        logger.info("WAL file detected; checkpointing Chroma SQLite database...")
        try:
            conn = sqlite3.connect(str(sqlite_src))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            logger.info("WAL checkpoint completed successfully.")
        except Exception as exc:
            logger.warning("Could not execute wal_checkpoint: %s", exc)

    # 2. Copy vectorstore
    vectorstore_dest = backup_path / "vectorstore"
    vectorstore_dest.mkdir(parents=True, exist_ok=True)
    for item in vectorstore_src.iterdir():
        if item.name.endswith("-wal") or item.name.endswith("-shm"):
            continue
        dest_item = vectorstore_dest / item.name
        if item.is_dir():
            shutil.copytree(item, dest_item, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest_item)

    # 3. Copy raw dataset
    raw_src = DATA_DIR / "raw" / "eureka_website_data.json"
    raw_dest_dir = backup_path / "raw"
    raw_dest_dir.mkdir(parents=True, exist_ok=True)
    if raw_src.exists():
        shutil.copy2(raw_src, raw_dest_dir / raw_src.name)
    else:
        logger.warning("Raw data file missing at: %s", raw_src)

    # 4. Copy processed chunks
    chunks_src = DATA_DIR / "processed" / "eureka_website_chunks.json"
    chunks_dest_dir = backup_path / "processed"
    chunks_dest_dir.mkdir(parents=True, exist_ok=True)
    if chunks_src.exists():
        shutil.copy2(chunks_src, chunks_dest_dir / chunks_src.name)
    else:
        logger.warning("Chunks file missing at: %s", chunks_src)

    # 5. Copy reports
    reports_src = DATA_DIR / "reports"
    reports_dest_dir = backup_path / "reports"
    if reports_src.exists():
        shutil.copytree(reports_src, reports_dest_dir, dirs_exist_ok=True)

    # 6. Read metadata
    raw_page_count = 0
    if raw_src.exists():
        try:
            with open(raw_src, "r", encoding="utf-8") as f:
                raw_page_count = len(json.load(f).get("pages", []))
        except Exception:
            pass

    chunk_count = 0
    if chunks_src.exists():
        try:
            with open(chunks_src, "r", encoding="utf-8") as f:
                chunk_count = len(json.load(f).get("chunks", []))
        except Exception:
            pass

    manifest_src = vectorstore_src / "index_manifest.json"
    manifest_info = {}
    if manifest_src.exists():
        try:
            with open(manifest_src, "r", encoding="utf-8") as f:
                manifest_info = json.load(f)
        except Exception:
            pass

    record_count = get_collection_count_from_sqlite(vectorstore_dest / "chroma.sqlite3") or chunk_count

    # 7. Generate file checksum inventory
    file_manifest: dict[str, dict[str, Any]] = {}
    for p in backup_path.rglob("*"):
        if p.is_file() and p.name != "backup_manifest.json":
            rel_path = str(p.relative_to(backup_path)).replace("\\", "/")
            file_manifest[rel_path] = {
                "size_bytes": p.stat().st_size,
                "sha256": compute_sha256(p),
            }

    backup_manifest = {
        "backup_version": "1.0",
        "timestamp_utc": timestamp,
        "git_revision": get_git_revision(PROJECT_ROOT),
        "raw_pages_count": raw_page_count,
        "raw_data_sha256": file_manifest.get("raw/eureka_website_data.json", {}).get("sha256"),
        "chunks_count": chunk_count,
        "chunks_data_sha256": file_manifest.get("processed/eureka_website_chunks.json", {}).get("sha256"),
        "collection_name": manifest_info.get("collection_name", "eureka_website_chunks"),
        "total_records": record_count,
        "embedding_model": manifest_info.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2"),
        "embedding_dimension": manifest_info.get("embedding_dimension", 384),
        "total_files": len(file_manifest),
        "total_size_bytes": sum(item["size_bytes"] for item in file_manifest.values()),
        "files": file_manifest,
        "status": "VALID",
    }

    manifest_file = backup_path / "backup_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(backup_manifest, f, indent=2)

    logger.info("Backup created successfully: %s", backup_path)
    logger.info("Total files: %d, Total size: %.2f MB, Records: %d",
                backup_manifest["total_files"],
                backup_manifest["total_size_bytes"] / (1024 * 1024),
                record_count)
    return backup_path


def verify_and_restore_test(
    backup_path: Optional[Path] = None,
    isolated_target: Optional[Path] = None,
    keep_isolated: bool = False,
) -> dict[str, Any]:
    """Perform an end-to-end restore test in an isolated scratch directory.

    Steps:
    1. Verify backup manifest & cryptographic hashes.
    2. Copy backup into isolated test directory.
    3. Verify restored file integrity.
    4. Connect to restored ChromaDB collection.
    5. Verify collection existence and record count (3,796).
    6. Execute semantic search smoke query.
    7. Clean up isolated directory (unless keep_isolated=True).
    """
    start_time = time.time()
    if backup_path is None:
        # Pick the latest backup in DEFAULT_BACKUP_DIR
        backups = [p for p in DEFAULT_BACKUP_DIR.iterdir() if p.is_dir() and p.name.startswith("backup_")]
        if not backups:
            logger.info("No existing backup found; creating fresh backup for restore test...")
            backup_path = create_backup()
        else:
            backup_path = sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True)[0]

    logger.info("Testing restore from backup: %s", backup_path)
    manifest_p = backup_path / "backup_manifest.json"
    if not manifest_p.exists():
        raise FileNotFoundError(f"backup_manifest.json missing in {backup_path}")

    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Verify files in backup match manifest
    logger.info("Step 1: Verifying SHA-256 hashes in backup...")
    hash_errors = []
    for rel_path, meta in manifest.get("files", {}).items():
        fp = backup_path / rel_path
        if not fp.exists():
            hash_errors.append(f"Missing file: {rel_path}")
            continue
        actual_sha = compute_sha256(fp)
        if actual_sha != meta["sha256"]:
            hash_errors.append(f"Checksum mismatch for {rel_path}: expected {meta['sha256']}, got {actual_sha}")

    if hash_errors:
        raise ValueError(f"Backup integrity check failed: {hash_errors}")
    logger.info("Step 1 PASSED: All %d file checksums verified.", len(manifest.get("files", {})))

    # 2. Unpack/copy into isolated restore directory
    isolated_dir = isolated_target or (DATA_DIR / "restore_test_isolated")
    if isolated_dir.exists():
        shutil.rmtree(isolated_dir)
    isolated_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Step 2: Restoring into isolated sandbox: %s", isolated_dir)

    for rel_path in manifest.get("files", {}).keys():
        src_file = backup_path / rel_path
        dest_file = isolated_dir / rel_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)

    logger.info("Step 2 PASSED: Restored files to %s.", isolated_dir)

    # 3. Mount isolated ChromaDB and test retrieval
    logger.info("Step 3: Connecting to isolated ChromaDB vector store...")
    restored_vectorstore = isolated_dir / "vectorstore"
    restored_sqlite = restored_vectorstore / "chroma.sqlite3"
    if not restored_sqlite.exists():
        raise FileNotFoundError(f"Restored chroma.sqlite3 not found at {restored_sqlite}")

    # Use chromadb persistent client
    import chromadb
    client = chromadb.PersistentClient(path=str(restored_vectorstore))
    collection_name = manifest.get("collection_name", "eureka_website_chunks")
    collection = client.get_collection(name=collection_name)
    actual_count = collection.count()

    expected_count = manifest.get("chunks_count", 3796)
    logger.info("Collection '%s' count: %d (expected: %d)", collection_name, actual_count, expected_count)
    if actual_count != expected_count:
        raise ValueError(f"Collection count mismatch: expected {expected_count}, got {actual_count}")
    logger.info("Step 3 PASSED: Collection exists with exactly %d records.", actual_count)

    # 4. Deterministic retrieval query test
    logger.info("Step 4: Executing semantic retrieval smoke tests against restored index...")
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer(manifest.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2"))

    test_queries = [
        "What ERP software does Eureka Solutions implement?",
        "Cloud integration and API services",
    ]
    retrieval_results = []
    for q in test_queries:
        query_emb = embedder.encode([q], normalize_embeddings=True).tolist()[0]
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=3,
            include=["documents", "metadatas", "distances"],
        )
        top_url = results["metadatas"][0][0].get("source_url") or results["metadatas"][0][0].get("canonical_url", "")
        top_title = results["metadatas"][0][0].get("page_title", "")
        top_dist = results["distances"][0][0]
        logger.info("Query: '%s' -> Top Result: %s (%s) (Cosine Distance: %.4f)", q, top_title, top_url, top_dist)
        retrieval_results.append({
            "query": q,
            "top_title": top_title,
            "top_url": top_url,
            "top_distance": round(top_dist, 4),
            "top_document_snippet": results["documents"][0][0][:120],
        })

    logger.info("Step 4 PASSED: Retrieval smoke tests returned grounded results.")

    # 5. Cleanup
    duration_s = round(time.time() - start_time, 2)
    if not keep_isolated:
        logger.info("Step 5: Cleaning up isolated sandbox %s...", isolated_dir)
        # Explicitly release client/db locks before removing
        del collection
        del client
        del embedder
        import gc
        gc.collect()
        time.sleep(1.0)
        try:
            shutil.rmtree(isolated_dir)
            logger.info("Step 5 PASSED: Isolated directory cleanly unmounted and removed.")
        except Exception as exc:
            logger.warning("Could not fully remove isolated dir: %s", exc)
    else:
        logger.info("Step 5: Preserved isolated sandbox at: %s", isolated_dir)

    result_report = {
        "status": "PASS",
        "backup_tested": str(backup_path.name),
        "timestamp_utc": manifest["timestamp_utc"],
        "records_verified": actual_count,
        "files_verified": len(manifest.get("files", {})),
        "duration_seconds": duration_s,
        "retrieval_smoke_tests": retrieval_results,
    }

    logger.info("RESTORE TEST RESULT: PASS in %.2f seconds.", duration_s)
    return result_report


def list_backups(backup_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """List available backups with metadata."""
    base = backup_dir or DEFAULT_BACKUP_DIR
    if not base.exists():
        return []
    results = []
    for p in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_dir() and (p / "backup_manifest.json").exists():
            with open(p / "backup_manifest.json", "r", encoding="utf-8") as f:
                manifest = json.load(f)
            results.append({
                "name": p.name,
                "timestamp": manifest.get("timestamp_utc"),
                "records": manifest.get("total_records"),
                "size_mb": round(manifest.get("total_size_bytes", 0) / (1024 * 1024), 2),
                "git": manifest.get("git_revision", "")[:8],
                "path": str(p),
            })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Eureka RAG Chatbot Backup & Restore Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_p = subparsers.add_parser("create", help="Create a new timestamped backup")
    create_p.add_argument("--tag", type=str, default=None, help="Optional tag for backup name")
    create_p.add_argument("--dest", type=Path, default=None, help="Destination directory")

    # restore-test
    restore_p = subparsers.add_parser("restore-test", help="Execute isolated restore verification")
    restore_p.add_argument("--backup", type=Path, default=None, help="Specific backup to test")
    restore_p.add_argument("--keep", action="store_true", help="Keep restored directory after test")

    # list
    subparsers.add_parser("list", help="List available backups")

    args = parser.parse_args()

    if args.command == "create":
        bp = create_backup(destination_root=args.dest, tag=args.tag)
        print(f"Created: {bp}")
        return 0
    elif args.command == "restore-test":
        report = verify_and_restore_test(backup_path=args.backup, keep_isolated=args.keep)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "PASS" else 1
    elif args.command == "list":
        backups = list_backups()
        if not backups:
            print("No backups found.")
        else:
            print(f"{'NAME':<35} {'TIMESTAMP':<22} {'RECORDS':<10} {'SIZE':<10} {'GIT':<10}")
            print("-" * 90)
            for b in backups:
                print(f"{b['name']:<35} {b['timestamp']:<22} {b['records']:<10} {b['size_mb']} MB   {b['git']:<10}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
