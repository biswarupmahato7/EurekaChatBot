# Backend — `backend/`

## Responsibility

This directory contains the core backend services for the Eureka RAG Chatbot:
- **Phase B (Complete):** Semantic retrieval foundation, ChromaDB persistent storage, SentenceTransformer embedder, batch index builder, and golden retrieval evaluation.
- **Phase C (Complete):** FastAPI web service, OpenAI LLM integration (Responses API / Chat Completions, `gpt-4o-mini`), prompt construction, and chat endpoints.
- **Phase D & E (Complete):** Smart conversation routing, abuse/profanity handling, context-aware clarification with quick-reply options, and comprehensive regression suite.
- **Phase F (Complete):** Production deployment configurations, containerization, persistent volume mounts, and automated backup/restore verification.

The backend is the **only** component permitted to access the vector store (ChromaDB) and LLM APIs. The browser/frontend must never receive database credentials or query ChromaDB/OpenAI directly.

---

## Current Status: Phase F Complete

The **Backend & Retrieval Engine** is fully implemented, verified, and operational:
- **ChromaDB Persistent Store:** Stored at `./data/vectorstore` (collection: `eureka_website_chunks`, 3,796 records).
- **Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors, L2-normalized for cosine similarity).
- **Index Builder:** Reproducible batch indexing (`scripts/build_index.py`), SHA-256 content-hash skip logic, atomic manifest tracking, and model compatibility guards.
- **Semantic Retriever:** Configurable top-k retrieval (`TOP_K=6`, same-page concentration cap, optional threshold support).
- **Primary LLM Client:** OpenAI official SDK (`gpt-4o-mini`, Responses API, 30s timeout, bounded retries).
- **Smart Conversation Router:** Off-topic/trivia redirection, profanity/insult de-escalation, contact clarification with quick-reply options.
- **Automated Tests:** 88 unit and integration tests passing in `backend/tests/` (part of 337 total backend/eval tests).

---

## Package Structure

```text
backend/
├── config.py             # Validated Pydantic settings from .env
├── logging_config.py     # Structured console logging
├── embeddings/
│   ├── base.py           # BaseEmbedder abstract interface & text preprocessing
│   ├── mock_embedder.py  # Deterministic unit-normalized mock embedder for offline tests
│   └── sentence_transformer_embedder.py  # SentenceTransformers wrapper with model caching
├── vectorstore/
│   ├── base.py           # VectorRecord, VectorQueryResult & BaseVectorStore interface
│   └── chroma_store.py   # ChromaDB persistent client adapter (collection: eureka_website_chunks)
├── indexing/
│   ├── manifest.py       # IndexManifest provenance & compatibility tracking
│   └── index_builder.py  # Batch chunk validation, skip logic, and upsert engine
├── retrieval/
│   ├── models.py         # SearchResult & RetrievalResponse contracts
│   └── retriever.py      # SemanticRetriever with deduplication and thresholding
├── evaluation/
│   ├── golden_dataset.json     # Grounded evaluation queries across all required styles
│   └── evaluate_retrieval.py   # CLI evaluation runner (Recall@k, HitRate@k, MRR)
├── tests/
│   ├── fixtures/
│   │   └── sample_chunks.json  # Offline test fixtures
│   ├── test_embeddings.py
│   ├── test_storage.py
│   ├── test_indexing.py
│   ├── test_retrieval.py
│   ├── test_evaluation.py
│   └── test_phase_boundaries.py
└── requirements.txt
```

---

## CLI Commands

### 1. Build / Update the Vector Index

Build the ChromaDB vector index from the validated Phase A chunk dataset:
```bash
# Standard build (skips unchanged chunks automatically)
python -m scripts.build_index

# Specify custom batch size
python -m scripts.build_index --batch-size 64

# Dry-run validation only (does not write to ChromaDB)
python -m scripts.build_index --dry-run

# Force full index rebuild / reset
python -m scripts.build_index --rebuild

# View options
python -m scripts.build_index --help
```

### 2. Run Retrieval Evaluation

Evaluate retrieval quality against the golden query set:
```bash
python -m backend.evaluation.evaluate_retrieval

# Evaluate with custom top_k
python -m backend.evaluation.evaluate_retrieval --top-k 10
```

### 3. Query Python Smoke-Test

To query the retrieval index directly without any LLM calls:
```python
from backend.config import get_backend_settings
from backend.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.chroma_store import ChromaVectorStore

settings = get_backend_settings()
store = ChromaVectorStore(
    persist_directory=settings.chroma_persist_directory,
    collection_name=settings.chroma_collection,
)
embedder = SentenceTransformerEmbedder(model_name=settings.embedding_model)
retriever = SemanticRetriever(vector_store=store, embedder=embedder)

response = retriever.retrieve("What enterprise software solutions does Eureka provide?", top_k=6)
for res in response.results:
    print(f"[{res.score:.3f}] {res.page_title} - {res.source_url}")
    print(f"       {res.text[:120]}...\n")
```

## Conversational Style Policy & Capability Answers

To ensure the chatbot sounds natural, friendly, direct, and helpful while remaining strictly grounded in the approved Eureka Solutions website corpus, the backend applies the following conversational engineering rules:

### 1. Tone & Natural Voice
- **Direct & Friendly:** Answers begin with a direct answer in the very first sentence (e.g., *"Yes, Eureka Solutions provides..."*).
- **Everyday Professional English:** Simple, clear language is favored over corporate jargon or promotional hype.
- **Zero Robotic Meta-Hedging:** Phrasing such as *"Based on the available website content..."*, *"According to the provided sources..."*, or *"The company positions itself as having significant expertise..."* is strictly forbidden.
- **Conversational Structure:** Prefers natural paragraphs over reflexive bullet lists. Bullet points are used only when enumerating distinct services or implementation stages.
- **Forgiving Intent Understanding:** Gracefully interprets informal phrasing, typos (e.g., *"Are they gud at AI solutins?"*), and slang without lecturing or correcting grammar.

### 2. Evidence-Aware Capability Matrix (Cases A–D)
When asked capability questions (e.g., *"Are they good with AI solutions?"*, *"Have they delivered AI projects before?"*), the system distinguishes between four evidence levels:

| Evidence Level | Scenario | Grounded Response Behavior |
|---|---|---|
| **Case A** | Strong, specific project evidence exists | Summarize verified outcomes (e.g., Municipality WhatsApp Service Bot: 50,000 accounts, 70% fewer routine visits) and cite source with confidence. |
| **Case B** | Service capabilities documented, but no completed case study | Explain what services Eureka Solutions offers (e.g., Agentic AI, AI Strategy, Copilots, IDP), emphasize governance and enterprise integration, clearly note that specific client case studies should be requested from the team, and provide a helpful next step. |
| **Case C** | Adjacent capabilities documented only | Clarify distinctions honestly (e.g., software engineering and cloud vs. custom quantum chips or hardware manufacturing). |
| **Case D** | Absent or insufficient evidence | Abstain helpfully or clarify the limitation directly without inventing facts or forcing an unverified "Yes". |

---

## Testing & Quality Assurance

Run all unit, integration, and conversational tone quality tests:
```bash
# Run all backend unit and regression tests
pytest backend/tests/ -v

# Run the 10 conversational tone and capability regression tests
pytest tests/test_conversational_tone_quality.py -v

# Run full integration suite
pytest backend/tests/ tests/ -v
```
