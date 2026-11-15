"""Sparse + Dense hybrid retrieval configuration. No external dependencies."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class HybridConfig:
    """Initial defaults: BM25 20 + Vector 20 -> RRF 20 -> CrossEncoder 10.

    Set weights to 0 to disable a signal. Both weights cannot be zero.
    """

    vector_top_k: int = 20
    bm25_top_k: int = 20
    fusion_top_k: int = 20
    final_top_k: int = 10
    rrf_k: int = 60
    vector_weight: float = 1.0
    bm25_weight: float = 1.0
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_local_dir: str | None = None  # path under project by default
    reranker_revision: str | None = None  # optional explicit Hugging Face commit/revision
    reranker_batch_size: int = 8
    reranker_max_chars: int = 2000
    rerank_failure_policy: str = "rrf_fallback"  # or "raise"
    # When the best Cross-Encoder score is below this, the reranker has no confident
    # candidate and its order is not trusted: keep the RRF order instead (0 disables).
    rerank_min_confidence: float = 0.1
    retriever_failure_policy: str = "raise"  # or "partial"
    parallel_retrieval: bool = True

    def __post_init__(self) -> None:
        for name in ("vector_top_k", "bm25_top_k", "fusion_top_k", "final_top_k", "rrf_k", "reranker_batch_size", "reranker_max_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.vector_top_k > 40:
            # Existing VectorSearchService enforces top_k<=40.
            raise ValueError("vector_top_k must be at most 40 (existing VectorSearchService limit)")
        if self.final_top_k > self.fusion_top_k:
            raise ValueError("final_top_k must be <= fusion_top_k")
        if self.fusion_top_k > self.vector_top_k + self.bm25_top_k:
            raise ValueError("fusion_top_k cannot exceed the sum of retrieval limits")
        for name in ("vector_weight", "bm25_weight"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.vector_weight == 0 and self.bm25_weight == 0:
            raise ValueError("at least one of vector_weight and bm25_weight must be positive")
        if not isinstance(self.reranker_model, str) or not self.reranker_model.strip():
            raise ValueError("reranker_model must be a non-empty string")
        for name in ("reranker_local_dir", "reranker_revision"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")
        if self.rerank_failure_policy not in {"raise", "rrf_fallback"}:
            raise ValueError("rerank_failure_policy must be 'raise' or 'rrf_fallback'")
        if (isinstance(self.rerank_min_confidence, bool) or not isinstance(self.rerank_min_confidence, (int, float))
                or not math.isfinite(self.rerank_min_confidence) or not 0 <= self.rerank_min_confidence <= 1):
            raise ValueError("rerank_min_confidence must be between 0 and 1")
        if self.retriever_failure_policy not in {"raise", "partial"}:
            raise ValueError("retriever_failure_policy must be 'raise' or 'partial'")
        if not isinstance(self.parallel_retrieval, bool):
            raise ValueError("parallel_retrieval must be boolean")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HybridConfig:
        """Read environment overrides, preserving explicit constructor defaults elsewhere."""
        source = os.environ if env is None else env
        fields = {
            "vector_top_k": ("HYBRID_VECTOR_TOP_K", int),
            "bm25_top_k": ("HYBRID_BM25_TOP_K", int),
            "fusion_top_k": ("HYBRID_FUSION_TOP_K", int),
            "final_top_k": ("HYBRID_FINAL_TOP_K", int),
            "rrf_k": ("HYBRID_RRF_K", int),
            "vector_weight": ("HYBRID_VECTOR_WEIGHT", float),
            "bm25_weight": ("HYBRID_BM25_WEIGHT", float),
            "reranker_model": ("HYBRID_RERANK_MODEL", str),
            "reranker_local_dir": ("HYBRID_RERANK_LOCAL_DIR", str),
            "reranker_revision": ("HYBRID_RERANK_REVISION", str),
            "reranker_batch_size": ("HYBRID_RERANK_BATCH_SIZE", int),
            "reranker_max_chars": ("HYBRID_RERANK_MAX_CHARS", int),
            "rerank_failure_policy": ("HYBRID_RERANK_FAILURE_POLICY", str),
            "rerank_min_confidence": ("HYBRID_RERANK_MIN_CONFIDENCE", float),
            "retriever_failure_policy": ("HYBRID_RETRIEVER_FAILURE_POLICY", str),
            "parallel_retrieval": ("HYBRID_PARALLEL_RETRIEVAL", str),
        }
        kwargs: dict[str, object] = {}
        for name, (key, cast) in fields.items():
            raw = source.get(key)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                if name == "parallel_retrieval":
                    if raw.lower() not in {"true", "false", "1", "0", "yes", "no"}:
                        raise ValueError("expected true/false")
                    kwargs[name] = raw.lower() in {"true", "1", "yes"}
                else:
                    kwargs[name] = cast(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid environment variable {key}: {raw!r}") from exc
        return cls(**kwargs)
