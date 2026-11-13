"""Rank vector-found museums with corpus-wide Korean BM25 and RRF.

This module does not query Chroma or Neo4j. Build one ``BM25Reranker`` from
the graph's full TextSpan corpus, then pass vector-ranked museum IDs to
``rerank``. The caller joins ``best_span_id`` to its sourced graph evidence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite

from rank_bm25 import BM25Okapi


@dataclass(frozen=True, slots=True)
class SpanDocument:
    museum_id: str
    span_id: str
    text: str


@dataclass(frozen=True, slots=True)
class RankedMuseum:
    museum_id: str
    vector_rank: int
    bm25_rank: int | None
    bm25_score: float
    rrf_score: float
    best_span_id: str | None
    best_span_text: str | None


def _kiwi_tokenizer() -> Callable[[str], list[str]]:
    """Use the same content-word analysis for stored spans and questions."""
    from kiwipiepy import Kiwi

    kiwi = Kiwi()

    def tokenize(text: str) -> list[str]:
        return [
            token.form.casefold()
            for token in kiwi.tokenize(text)
            if token.tag.startswith(("N", "V", "M")) or token.tag in {"SL", "SN", "XR"}
        ]

    return tokenize


def _nonnegative_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


class BM25Reranker:
    """Keep global IDF statistics and fuse candidate ranks without DB access."""

    def __init__(
        self,
        spans: Sequence[SpanDocument],
        *,
        tokenize: Callable[[str], list[str]] | None = None,
    ) -> None:
        if tokenize is not None and not callable(tokenize):
            raise TypeError("tokenize must be callable")
        self._tokenize = tokenize or _kiwi_tokenizer()
        if any(not isinstance(span, SpanDocument) for span in spans):
            raise TypeError("spans must contain SpanDocument values")
        self._spans = tuple(sorted(spans, key=lambda span: span.span_id))
        span_ids: set[str] = set()
        by_museum: dict[str, list[int]] = defaultdict(list)
        for index, span in enumerate(self._spans):
            if not span.museum_id or not span.span_id or not span.text.strip():
                raise ValueError("each span needs a museum_id, span_id, and text")
            if span.span_id in span_ids:
                raise ValueError(f"duplicate span_id: {span.span_id}")
            span_ids.add(span.span_id)
            by_museum[span.museum_id].append(index)
        self._by_museum = by_museum

        tokenized = [self._tokenize(span.text) for span in self._spans]
        self._bm25 = BM25Okapi(tokenized) if any(tokenized) else None

    def rerank(
        self,
        question: str,
        vector_museum_ids: Sequence[str],
        *,
        top_k: int = 5,
        rrf_constant: float = 60,
        vector_weight: float = 1.0,
        bm25_weight: float = 1.0,
    ) -> list[RankedMuseum]:
        """Return top museums in fused order; input IDs are vector-rank ordered.

        BM25 document frequencies come from all constructor spans. Only spans
        owned by input museums compete in this query's lexical ranking. A
        zero BM25 score contributes nothing and preserves vector ordering.
        """
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a nonempty string")
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        rrf_constant = _nonnegative_finite(rrf_constant, "rrf_constant")
        if rrf_constant == 0:
            raise ValueError("rrf_constant must be positive")
        vector_weight = _nonnegative_finite(vector_weight, "vector_weight")
        bm25_weight = _nonnegative_finite(bm25_weight, "bm25_weight")
        if vector_weight == bm25_weight == 0:
            raise ValueError("at least one rank weight must be positive")

        if isinstance(vector_museum_ids, (str, bytes)):
            raise ValueError("vector_museum_ids must be a sequence of IDs")
        museum_ids = list(dict.fromkeys(vector_museum_ids))
        if any(not isinstance(mid, str) or not mid.strip() for mid in museum_ids):
            raise ValueError("vector_museum_ids must contain nonempty strings")
        if not museum_ids:
            return []

        query_tokens = self._tokenize(question)
        scores = self._bm25.get_scores(query_tokens) if self._bm25 and query_tokens else ()
        best: dict[str, tuple[float, SpanDocument]] = {}
        for museum_id in museum_ids:
            for index in self._by_museum.get(museum_id, ()):
                score = float(scores[index]) if len(scores) else 0.0
                if score > 0 and (museum_id not in best or score > best[museum_id][0]):
                    best[museum_id] = (score, self._spans[index])

        vector_ranks = {museum_id: rank for rank, museum_id in enumerate(museum_ids, 1)}
        lexical_ids = sorted(best, key=lambda mid: (-best[mid][0], vector_ranks[mid], mid))
        bm25_ranks = {museum_id: rank for rank, museum_id in enumerate(lexical_ids, 1)}

        fused: list[RankedMuseum] = []
        for museum_id in museum_ids:
            vector_rank = vector_ranks[museum_id]
            bm25_rank = bm25_ranks.get(museum_id)
            bm25_score, span = best.get(museum_id, (0.0, None))
            rrf_score = vector_weight / (rrf_constant + vector_rank)
            if bm25_rank is not None:
                rrf_score += bm25_weight / (rrf_constant + bm25_rank)
            fused.append(RankedMuseum(
                museum_id=museum_id,
                vector_rank=vector_rank,
                bm25_rank=bm25_rank,
                bm25_score=bm25_score,
                rrf_score=rrf_score,
                best_span_id=span.span_id if span else None,
                best_span_text=span.text if span else None,
            ))
        fused.sort(key=lambda item: (-item.rrf_score, item.vector_rank, item.museum_id))
        return fused[:top_k]
