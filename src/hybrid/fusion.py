"""Weighted RRF fusion; no LLM, Chroma or Neo4j dependency."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .config import HybridConfig


def _clean_hits(hits: Sequence[Mapping[str, Any]], source: str) -> list[dict[str, Any]]:
    """Deduplicate per retriever without inventing scores or positions.

    Rank is the ORDER of the supplied list (1-based). Callers must sort the
    BM25 list by descending score; the Vector list is expected by similarity.
    """
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for original_rank, hit in enumerate(hits, 1):
        if not isinstance(hit, Mapping):
            raise TypeError(f"{source} result #{original_rank} must be a mapping")
        museum_id = str(hit.get("museum_id") or "").strip()
        if not museum_id:
            raise ValueError(f"{source} result #{original_rank} has no museum_id")
        if museum_id in seen:
            continue
        seen.add(museum_id)
        metadata = hit.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            raise ValueError(f"{source} result {museum_id}: metadata must be a mapping")
        cleaned.append({**hit, "museum_id": museum_id, "metadata": dict(metadata), "_rank": original_rank})
    return cleaned


def _float_or_none(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric or null")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be numeric or null") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def fuse_rrf(
    vector_hits: Sequence[Mapping[str, Any]],
    bm25_hits: Sequence[Mapping[str, Any]],
    *,
    config: HybridConfig | None = None,
) -> list[dict[str, Any]]:
    """Return deduplicated, RRF-sorted museum candidates (<=fusion_top_k).

    BM25 hits with score<=0 provide no lexical evidence (and are omitted if
    they have no positive-weight vector signal). Scores are never directly added.
    """
    settings = config or HybridConfig()
    vectors = _clean_hits(vector_hits, "vector")[:settings.vector_top_k]
    sparse = _clean_hits(bm25_hits, "bm25")[:settings.bm25_top_k]
    merged: dict[str, dict[str, Any]] = {}

    def acquire(item: Mapping[str, Any]) -> dict[str, Any]:
        museum_id = item["museum_id"]
        if museum_id not in merged:
            merged[museum_id] = {
                "museum_id": museum_id,
                "name": item.get("name") or item["metadata"].get("name"),
                "document": "",
                "metadata": dict(item["metadata"]),
                "vector_rank": None,
                "bm25_rank": None,
                "vector_distance": None,
                "vector_score": None,
                "bm25_score": None,
                "vector_document": "",
                "bm25_document": "",
                "best_span_id": None,
                "best_span_text": None,
                "fusion_score": 0.0,
                "retrieved_by": [],
            }
        entry = merged[museum_id]
        # A later retrieval source may supply richer data.
        if not entry["name"]:
            entry["name"] = item.get("name") or item["metadata"].get("name")
        for key, value in item["metadata"].items():
            if key not in entry["metadata"] or entry["metadata"][key] in (None, ""):
                entry["metadata"][key] = value
        return entry

    if settings.vector_weight > 0:
        for item in vectors:
            entry = acquire(item)
            entry["vector_rank"] = item["_rank"]
            entry["vector_distance"] = _float_or_none(item.get("distance"), field_name="vector.distance")
            entry["vector_score"] = _float_or_none(item.get("score"), field_name="vector.score")
            entry["vector_document"] = str(item.get("document") or item.get("text") or "")
            entry["fusion_score"] += settings.vector_weight / (settings.rrf_k + item["_rank"])
            entry["retrieved_by"].append("vector")

    if settings.bm25_weight > 0:
        for item in sparse:
            score = _float_or_none(item.get("score"), field_name="bm25.score")
            if score is None:
                raise ValueError(f"BM25 result {item['museum_id']} must include a numeric score")
            if score <= 0:
                continue
            entry = acquire(item)
            entry["bm25_rank"] = item["_rank"]
            entry["bm25_score"] = score
            entry["bm25_document"] = str(item.get("document") or item.get("text") or item.get("snippet") or "")
            entry["best_span_id"] = item.get("best_span_id")
            entry["best_span_text"] = item.get("best_span_text")
            entry["fusion_score"] += settings.bm25_weight / (settings.rrf_k + item["_rank"])
            entry["retrieved_by"].append("bm25")

    for entry in merged.values():
        entry["document"] = entry["vector_document"] or entry["bm25_document"]
        if not entry["name"]:
            entry["name"] = entry["metadata"].get("name")

    # Ties: vector rank, BM25 rank, then museum_id. Stable across processes.
    ranked = sorted(
        merged.values(),
        key=lambda item: (
            -item["fusion_score"],
            item["vector_rank"] if item["vector_rank"] is not None else math.inf,
            item["bm25_rank"] if item["bm25_rank"] is not None else math.inf,
            item["museum_id"],
        ),
    )
    return [dict(item, fusion_rank=i) for i, item in enumerate(ranked[:settings.fusion_top_k], 1)]
