"""Independent museum BM25 + Chroma hybrid retrieval package."""

from .adapters import BM25CallableAdapter, ExistingVectorRetriever
from .config import HybridConfig
from .fusion import fuse_rrf
from .reranker import CrossEncoderReranker
from .service import HybridSearchService

__all__ = [
    "BM25CallableAdapter",
    "ExistingVectorRetriever",
    "HybridConfig",
    "HybridSearchService",
    "CrossEncoderReranker",
    "fuse_rrf",
    "BM25Reranker",
    "BM25SpanRetriever",
    "SpanDocument",
    "build_hybrid_service",
    "HybridRAGAgent",
    "HybridSearchRAGAgent",
    "get_tool_definition",
    "get_retrieval_tool_definition",
]


def __getattr__(name: str):
    # Keep lightweight RRF functionality available without rank-bm25/Kiwi.
    if name in {"BM25SpanRetriever", "SpanDocument", "BM25Reranker", "build_hybrid_service",
                "HybridRAGAgent", "HybridSearchRAGAgent", "get_tool_definition", "get_retrieval_tool_definition"}:
        if name in {"HybridRAGAgent", "HybridSearchRAGAgent", "get_tool_definition", "get_retrieval_tool_definition"}:
            from .hybrid_rag_agent import (HybridRAGAgent, HybridSearchRAGAgent,
                                          get_tool_definition, get_retrieval_tool_definition)
            return {"HybridRAGAgent": HybridRAGAgent, "HybridSearchRAGAgent": HybridSearchRAGAgent,
                    "get_tool_definition": get_tool_definition,
                    "get_retrieval_tool_definition": get_retrieval_tool_definition}[name]
        if name == "build_hybrid_service":
            from .factory import build_hybrid_service
            return build_hybrid_service
        if name == "BM25SpanRetriever":
            from .bm25_retriever import BM25SpanRetriever
            return BM25SpanRetriever
        from .bm25_reranker import BM25Reranker, SpanDocument
        return {"BM25Reranker": BM25Reranker, "SpanDocument": SpanDocument}[name]
    raise AttributeError(name)
