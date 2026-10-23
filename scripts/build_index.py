"""
scripts/build_index.py
======================
Executable CLI entry point for building and maintaining the Eureka RAG vector index.

Usage:
    python -m scripts.build_index [--rebuild] [--batch-size 64] [--dry-run]
    python -m scripts.build_index --help
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import get_backend_settings
from backend.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from backend.indexing.index_builder import IndexBuilder
from backend.logging_config import setup_logging
from backend.vectorstore.chroma_store import ChromaVectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or incrementally update the ChromaDB vector index from Phase A chunk datasets.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to the input chunks JSON file (defaults to backend config setting).",
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=None,
        help="Directory where ChromaDB vector data is persisted.",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="ChromaDB collection name.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="SentenceTransformer embedding model name.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Batch size for computing embeddings and upserting into ChromaDB.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force a full reset and re-index of all chunks even if unchanged.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate chunks and report planned indexing operations without writing to storage.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(level=logging.INFO)
    logger = logging.getLogger("scripts.build_index")

    settings = get_backend_settings()
    persist_dir = args.persist_dir or settings.chroma_persist_directory
    collection_name = args.collection or settings.chroma_collection
    model_name = args.model or settings.embedding_model

    logger.info("Initializing vector store at '%s' (collection: '%s')...", persist_dir, collection_name)
    vector_store = ChromaVectorStore(
        persist_directory=persist_dir,
        collection_name=collection_name,
    )

    logger.info("Initializing embedder '%s'...", model_name)
    try:
        embedder = SentenceTransformerEmbedder(
            model_name=model_name,
            device=settings.embedding_device,
            batch_size=args.batch_size or settings.embedding_batch_size,
        )
    except Exception as exc:
        logger.error("Failed to initialize embedder: %s", exc)
        return 1

    builder = IndexBuilder(
        vector_store=vector_store,
        embedder=embedder,
        settings=settings,
    )

    report = builder.build_index(
        chunks_file_path=args.input,
        batch_size=args.batch_size,
        rebuild=args.rebuild,
        dry_run=args.dry_run,
    )

    if report.status == "FAILED":
        logger.error("Index build failed. Errors: %s", report.errors)
        return 1

    print("\n" + "=" * 60)
    print("  EUREKA RAG VECTOR INDEX BUILD REPORT")
    print("=" * 60)
    print(f" Status:                  {report.status}")
    print(f" Dataset:                 {report.dataset_path}")
    print(f" Dataset Type:            {report.dataset_type}")
    print(f" Total Input Chunks:      {report.total_input_chunks}")
    print(f" Valid Chunks:            {report.valid_chunks}")
    print(f" Added:                   {report.added_chunks}")
    print(f" Updated:                 {report.updated_chunks}")
    print(f" Unchanged (Skipped):     {report.skipped_chunks}")
    print(f" Embeddings Calculated:   {report.embeddings_calculated}")
    print(f" Collection Count:        {report.final_collection_count}")
    print(f" Embedding Model:         {report.embedding_model} (dim={report.embedding_dimension})")
    print(f" Build Duration:          {report.duration_seconds:.2f}s")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
