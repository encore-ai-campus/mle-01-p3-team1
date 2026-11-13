"""Ready-to-use hybrid service factory, without Neo4j/Graph dependencies."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .bm25_retriever import BM25SpanRetriever
from .config import HybridConfig
from .service import HybridSearchService


def build_hybrid_service(
    *,
    corpus_source: Literal["chroma", "file"] = "chroma",
    corpus_path: str | Path | None = None,
    chroma_collection: Any | None = None,
    chroma_db_path: str | Path | None = None,
    chroma_collection_name: str = "museum_documents",
    config: HybridConfig | None = None,
    tokenize: Callable[[str], list[str]] | None = None,
    vector_retriever: Any | None = None,
    reranker: Any | None = None,
) -> HybridSearchService:
    """Load BM25 index once at startup, reuse the existing Chroma vector service.

    Chroma corpus default needs no TextSpan export; CSV/JSONL `file` mode
    accepts a full TextSpan export without connecting to Neo4j.
    """
    if config is None:
        # The original project's env loading happens later during Vector
        # analysis, so read .env first for HYBRID_* config overrides.
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            project_root = Path(__file__).resolve().parents[2]
            load_dotenv(project_root / ".env", override=False)
        config = HybridConfig.from_env()
    if corpus_source == "chroma":
        if corpus_path is not None:
            raise ValueError("corpus_path is only valid for corpus_source='file'")
        bm25 = BM25SpanRetriever.from_chroma(
            collection=chroma_collection,
            db_path=chroma_db_path,
            collection_name=chroma_collection_name,
            tokenize=tokenize,
        )
    elif corpus_source == "file":
        if corpus_path is None:
            raise ValueError("corpus_path is required for corpus_source='file'")
        bm25 = BM25SpanRetriever.from_file(corpus_path, tokenize=tokenize)
    else:
        raise ValueError(f"Unsupported corpus_source: {corpus_source!r}")
    return HybridSearchService(
        bm25_retriever=bm25,
        vector_retriever=vector_retriever,
        reranker=reranker,
        config=config,
    )
