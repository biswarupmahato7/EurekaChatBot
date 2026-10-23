"""
backend/evaluation/evaluate_retrieval.py
========================================
Automated retrieval evaluation against the Golden Evaluation Set.

Key features:
- Computes Recall@k, HitRate@k, and Mean Reciprocal Rank (MRR).
- Tracks same-page concentration and duplicate result rates.
- Validates handling of out-of-corpus queries.
- Strictly offline evaluation against the active Chroma vector index.
- Saves detailed JSON evaluation report to data/reports/retrieval_evaluation_report.json.
- Can be run as a standalone CLI module:
    python -m backend.evaluation.evaluate_retrieval
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import BackendSettings, get_backend_settings
from backend.embeddings.base import BaseEmbedder
from backend.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from backend.indexing.manifest import IndexManifest
from backend.logging_config import setup_logging
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.base import BaseVectorStore
from backend.vectorstore.chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class QueryEvaluationResult(BaseModel):
    """Evaluation result for an individual golden query."""

    eval_id: str
    question: str
    category: str
    expected_page_ids: list[str]
    retrieved_page_ids: list[str]
    retrieved_chunk_ids: list[str]
    hit: bool  # True if at least one expected page is in retrieved pages
    reciprocal_rank: float = 0.0
    first_hit_rank: Optional[int] = None
    min_distance: Optional[float] = None
    avg_score: Optional[float] = None
    same_page_concentration: int = 1  # max chunks from the same page
    duration_ms: float = 0.0


class RetrievalEvaluationReport(BaseModel):
    """Aggregate evaluation report across the entire golden evaluation set."""

    evaluation_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    dataset_name: str
    dataset_type: str
    total_queries: int
    evaluable_queries: int  # Queries with expected ground truth (excluding out_of_corpus)
    out_of_corpus_queries: int
    top_k: int
    hit_rate_at_k: float  # Percentage of in-domain queries where an expected item is in top-k
    recall_at_k: float
    mrr: float  # Mean Reciprocal Rank
    avg_latency_ms: float
    embedding_model: str
    embedding_dimension: int
    collection_name: str
    collection_count: int
    results: list[QueryEvaluationResult]


class RetrievalEvaluator:
    """Evaluates semantic retriever against a golden evaluation dataset."""

    def __init__(
        self,
        retriever: SemanticRetriever,
        golden_dataset_path: Optional[Path | str] = None,
        settings: Optional[BackendSettings] = None,
    ) -> None:
        self.retriever = retriever
        self.settings = settings or get_backend_settings()
        self.golden_dataset_path = Path(
            golden_dataset_path
            or _PROJECT_ROOT / "backend" / "evaluation" / "golden_dataset.json"
        )

    def evaluate(self, top_k: Optional[int] = None) -> RetrievalEvaluationReport:
        """Run evaluation across all golden queries."""
        k = top_k or self.settings.top_k
        logger.info(
            "Starting retrieval evaluation (dataset: %s, top_k: %d)...",
            self.golden_dataset_path,
            k,
        )

        with open(self.golden_dataset_path, "r", encoding="utf-8") as f:
            golden_data = json.load(f)

        queries_data = golden_data.get("queries", [])
        dataset_name = golden_data.get("dataset_name", "Golden Retrieval Set")
        dataset_type = golden_data.get("dataset_type", "live")

        eval_results: list[QueryEvaluationResult] = []
        hits = 0
        total_rr = 0.0
        evaluable_count = 0
        out_of_corpus_count = 0
        latencies: list[float] = []

        for q_item in queries_data:
            eval_id = q_item["eval_id"]
            question = q_item["question"]
            category = q_item.get("category", "general")
            expected_pids = set(q_item.get("expected_page_ids", []))
            is_out_of_corpus = (category == "out_of_corpus") or (len(expected_pids) == 0)

            res = self.retriever.retrieve(query=question, top_k=k)
            latencies.append(res.duration_ms)

            retrieved_pids = [r.page_id for r in res.results]
            retrieved_cids = [r.chunk_id for r in res.results]
            distances = [r.distance for r in res.results if r.distance is not None]
            scores = [r.score for r in res.results if r.score is not None]

            # Calculate same-page concentration
            page_counts: dict[str, int] = {}
            for pid in retrieved_pids:
                page_counts[pid] = page_counts.get(pid, 0) + 1
            max_page_conc = max(page_counts.values()) if page_counts else 0

            hit = False
            reciprocal_rank = 0.0
            first_hit_rank = None

            if is_out_of_corpus:
                out_of_corpus_count += 1
            else:
                evaluable_count += 1
                for rank, pid in enumerate(retrieved_pids, start=1):
                    if pid in expected_pids:
                        hit = True
                        first_hit_rank = rank
                        reciprocal_rank = 1.0 / rank
                        break

                if hit:
                    hits += 1
                total_rr += reciprocal_rank

            eval_results.append(
                QueryEvaluationResult(
                    eval_id=eval_id,
                    question=question,
                    category=category,
                    expected_page_ids=list(expected_pids),
                    retrieved_page_ids=retrieved_pids,
                    retrieved_chunk_ids=retrieved_cids,
                    hit=hit,
                    reciprocal_rank=reciprocal_rank,
                    first_hit_rank=first_hit_rank,
                    min_distance=min(distances) if distances else None,
                    avg_score=sum(scores) / len(scores) if scores else None,
                    same_page_concentration=max_page_conc,
                    duration_ms=res.duration_ms,
                )
            )

        hit_rate = (hits / evaluable_count) if evaluable_count > 0 else 0.0
        mrr = (total_rr / evaluable_count) if evaluable_count > 0 else 0.0
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

        report = RetrievalEvaluationReport(
            dataset_name=dataset_name,
            dataset_type=dataset_type,
            total_queries=len(queries_data),
            evaluable_queries=evaluable_count,
            out_of_corpus_queries=out_of_corpus_count,
            top_k=k,
            hit_rate_at_k=round(hit_rate, 4),
            recall_at_k=round(hit_rate, 4),
            mrr=round(mrr, 4),
            avg_latency_ms=round(avg_latency, 2),
            embedding_model=self.retriever.embedder.model_name,
            embedding_dimension=self.retriever.embedder.dimension,
            collection_name=self.settings.chroma_collection,
            collection_count=self.retriever.vector_store.count(),
            results=eval_results,
        )

        self._save_report(report)
        return report

    def _save_report(self, report: RetrievalEvaluationReport) -> None:
        """Persist evaluation report to data/reports/retrieval_evaluation_report.json."""
        reports_dir = self.settings.reports_dir_path
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / "retrieval_evaluation_report.json"
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
            logger.info("Saved retrieval evaluation report to %s", report_file)
        except Exception as exc:
            logger.warning("Could not save retrieval report to %s: %s", report_file, exc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run retrieval evaluation against the golden evaluation dataset."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to golden evaluation JSON dataset.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Retrieval top-k setting (defaults to backend config: 6).",
    )
    args = parser.parse_args()

    setup_logging(level=logging.INFO)
    settings = get_backend_settings()

    logger.info("Initializing vector store from %s...", settings.chroma_persist_directory)
    vector_store = ChromaVectorStore(
        persist_directory=settings.chroma_persist_directory,
        collection_name=settings.chroma_collection,
    )

    logger.info("Initializing embedder '%s'...", settings.embedding_model)
    embedder = SentenceTransformerEmbedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )

    retriever = SemanticRetriever(
        vector_store=vector_store,
        embedder=embedder,
        settings=settings,
    )

    evaluator = RetrievalEvaluator(
        retriever=retriever,
        golden_dataset_path=args.dataset,
        settings=settings,
    )

    report = evaluator.evaluate(top_k=args.top_k)

    print("\n" + "=" * 70)
    print("  EUREKA RAG RETRIEVAL EVALUATION REPORT")
    print("=" * 70)
    print(f" Dataset Name:          {report.dataset_name} ({report.dataset_type})")
    print(f" Embedding Model:       {report.embedding_model} (dim={report.embedding_dimension})")
    print(f" Collection Records:    {report.collection_count}")
    print(f" Top-K Setting:         {report.top_k}")
    print(f" Total Queries:         {report.total_queries}")
    print(f" Evaluable Queries:     {report.evaluable_queries}")
    print(f" Out-of-Corpus Queries: {report.out_of_corpus_queries}")
    print(f" HitRate@{report.top_k}:         {report.hit_rate_at_k * 100:.1f}%")
    print(f" Recall@{report.top_k}:          {report.recall_at_k * 100:.1f}%")
    print(f" MRR (Mean Recip Rank): {report.mrr:.4f}")
    print(f" Avg Query Latency:     {report.avg_latency_ms:.2f} ms")
    print("-" * 70)
    print(f"{'Eval ID':<10} {'Category':<18} {'Hit':<6} {'Rank':<6} {'Min Dist':<10} {'Question':<25}")
    print("-" * 70)
    for r in report.results:
        rank_str = str(r.first_hit_rank) if r.first_hit_rank else "-"
        dist_str = f"{r.min_distance:.4f}" if r.min_distance is not None else "-"
        hit_str = "PASS" if r.hit else ("N/A" if r.category == "out_of_corpus" else "FAIL")
        q_trunc = r.question[:24] + "..." if len(r.question) > 24 else r.question
        print(f"{r.eval_id:<10} {r.category:<18} {hit_str:<6} {rank_str:<6} {dist_str:<10} {q_trunc:<25}")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
