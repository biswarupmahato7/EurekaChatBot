"""
backend/app/main.py
===================
FastAPI Application Entrypoint for Eureka RAG Chatbot.
Follows Problem Statement §§9–11 and Architecture §6.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.chat import router as chat_router
from backend.app.api.health import router as health_router
from pathlib import Path

from backend.app.config import AppSettings, get_app_settings
from backend.app.llm.groq_client import GroqClient
from backend.app.llm.openai_client import OpenAIClient
from backend.app.middleware.rate_limit import RateLimitMiddleware
from backend.app.middleware.request_id import RequestIdMiddleware
from backend.app.schemas.errors import ErrorBody, ErrorDetail, ErrorResponse
from backend.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from backend.indexing.manifest import IndexManifest
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.chroma_store import ChromaVectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eureka_rag_backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Initializes vector store, embedder, retriever, and LLM client once at startup.
    Ensures graceful cleanup on shutdown.
    """
    settings: AppSettings = getattr(app.state, "settings", None) or get_app_settings()
    logger.info("Initializing Eureka RAG Chatbot backend (env=%s)...", settings.environment)

    # 1. Initialize Vector Store and Retriever
    vector_store = None
    retriever = None
    try:
        logger.info(
            "Connecting to Chroma vector store at '%s' (collection: %s)...",
            settings.vector_persist_directory,
            settings.vector_collection_name,
        )
        vector_store = ChromaVectorStore(
            persist_directory=settings.vector_persist_directory,
            collection_name=settings.vector_collection_name,
        )
        count = vector_store.count()
        logger.info("Vector store connected successfully. Records count: %d", count)

        if count > 0:
            manifest_file = Path(settings.vector_persist_directory) / "index_manifest.json"
            manifest = IndexManifest.load(manifest_file)
            logger.info("Initializing embedding model '%s'...", settings.embedding_model_name)
            embedder = SentenceTransformerEmbedder(
                model_name=settings.embedding_model_name,
                device="cpu",
            )
            if manifest and not manifest.is_compatible(
                model_name=settings.embedding_model_name,
                dimension=embedder.dimension,
                preprocessing_version=settings.preprocessing_version,
            ):
                logger.error(
                    "Vector store manifest is INCOMPATIBLE with configured embedder. "
                    "Manifest model: '%s' (dim=%d) vs Configured model: '%s' (dim=%d). "
                    "Refusing to initialize incompatible retriever to prevent vector corruption.",
                    manifest.embedding_model,
                    manifest.embedding_dimension,
                    settings.embedding_model_name,
                    embedder.dimension,
                )
                app.state.index_incompatible = True
                app.state.incompatibility_reason = (
                    f"Index model '{manifest.embedding_model}' (dim={manifest.embedding_dimension}) "
                    f"does not match configured embedder '{settings.embedding_model_name}' (dim={embedder.dimension})."
                )
                retriever = None
            else:
                retriever = SemanticRetriever(
                    vector_store=vector_store,
                    embedder=embedder,
                    settings=settings,
                )
                app.state.index_incompatible = False
                logger.info("Semantic retriever initialized and ready.")
        else:
            app.state.index_incompatible = False
            logger.warning(
                "Vector store collection '%s' is empty or not indexed yet.",
                settings.vector_collection_name,
            )
    except Exception as exc:
        app.state.index_incompatible = False
        logger.warning(
            "Vector store / retriever initialization deferred or encountered issue: %s",
            exc,
        )

    app.state.vector_store = vector_store
    app.state.retriever = retriever

    # 2. Initialize LLM Client
    provider = settings.llm_provider.strip().lower()
    if provider == "groq":
        llm_client = GroqClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            timeout_seconds=settings.groq_timeout_seconds,
            max_retries=settings.groq_max_retries,
            max_output_tokens=settings.groq_max_output_tokens,
        )
        if llm_client.is_configured:
            logger.info("Groq client configured with model '%s'.", settings.groq_model)
        else:
            logger.warning("Groq client is NOT fully configured (missing API key or model).")
    else:
        llm_client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            max_output_tokens=settings.openai_max_output_tokens,
        )
        if llm_client.is_configured:
            logger.info("OpenAI client configured with model '%s'.", settings.openai_model)
        else:
            logger.warning("OpenAI client is NOT fully configured (missing API key or model).")

    app.state.llm_client = llm_client
    app.state.openai_client = llm_client
    app.state.groq_client = llm_client

    yield

    # Shutdown logic
    logger.info("Shutting down Eureka RAG Chatbot backend...")
    if vector_store and hasattr(vector_store, "close"):
        try:
            vector_store.close()
            logger.info("Vector store connection closed cleanly.")
        except Exception as exc:
            logger.error("Error closing vector store: %s", exc)


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app_settings = settings or get_app_settings()

    docs_url = "/docs" if app_settings.enable_interactive_docs else None
    redoc_url = "/redoc" if app_settings.enable_interactive_docs else None
    openapi_url = "/openapi.json" if app_settings.enable_interactive_docs else None

    app = FastAPI(
        title="Eureka RAG Chatbot Backend",
        description="FastAPI service for grounded QA over the Eureka Solutions website corpus.",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    # Middleware Pipeline
    # 1. Rate Limiting Middleware (innermost of these three)
    app.add_middleware(
        RateLimitMiddleware,
        trusted_proxies=app_settings.trusted_proxies,
        rate_limit_per_minute=app_settings.rate_limit_per_minute,
    )

    # 2. Exact-Origin CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # 3. Request ID Middleware (outermost, attaches correlation IDs to every request/response)
    app.add_middleware(RequestIdMiddleware)

    # Exception Handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or "req-unknown"
        error_details = []
        for err in exc.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            msg = err.get("msg", "Validation error")
            error_details.append(ErrorDetail(field=loc, issue=msg))

        err_response = ErrorResponse(
            request_id=req_id,
            error=ErrorBody(
                code="validation_error",
                message="Invalid request payload or schema constraints not met.",
                request_id=req_id,
                details=error_details,
            ),
        )
        return JSONResponse(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            content=err_response.model_dump(),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or "req-unknown"
        err_response = ErrorResponse(
            request_id=req_id,
            error=ErrorBody(
                code="http_error",
                message=str(exc.detail),
                request_id=req_id,
            ),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=err_response.model_dump(),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or "req-unknown"
        logger.exception("Unhandled server exception for request %s: %s", req_id, exc)
        err_response = ErrorResponse(
            request_id=req_id,
            error=ErrorBody(
                code="internal_error",
                message="An unexpected internal server error occurred.",
                request_id=req_id,
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=err_response.model_dump(),
            headers={"X-Request-ID": req_id},
        )

    # Register Routers
    app.include_router(health_router)
    app.include_router(chat_router)

    return app


# Root application instance for ASGI servers (e.g. uvicorn backend.app.main:app)
app = create_app()
