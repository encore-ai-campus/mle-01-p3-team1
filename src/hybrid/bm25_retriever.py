"""Independent sparse retrieval adapter for the supplied BM25Reranker.

The teammate's ``bm25_reranker.py`` is included unchanged. Its public ``rerank``
method restricts BM25 competition to IDs supplied by the caller, so this
adapter intentionally supplies *all eligible corpus museum IDs* and disables
its vector contribution. This yields a true independent BM25 ranking before
the outer HybridSearchService's weighted RRF fusion.

No Neo4j import, graph query, or graph dependency is required. A TextSpan
export can be supplied as JSONL/CSV, or one document per museum can be read
from the existing Chroma collection (read-only).
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .bm25_reranker import BM25Reranker, SpanDocument

_FILTER_KEYS = frozenset({
    "sido", "sidos", "sigungu", "ownership_type", "adult_fee_min",
    "adult_fee_max", "youth_fee_max", "child_fee_max",
})

# These are equivalent place spellings used by the existing Chroma tool.
_SIDO_GROUPS = (
    {"서울", "서울시", "서울특별시"},
    {"인천", "인천시", "인천광역시"},
    {"부산", "부산광역시"}, {"대구", "대구광역시"},
    {"대전", "대전광역시"}, {"광주", "광주광역시"},
    {"울산", "울산광역시"}, {"경기", "경기도"},
    {"강원", "강원도", "강원특별자치도"},
    {"충북", "충청북도"}, {"충남", "충청남도"},
    {"경북", "경상북도"}, {"경남", "경상남도"},
    {"전북", "전라북도", "전북특별자치도"},
    {"전남", "전라남도", "전남광주통합특별시"},
    {"제주", "제주도", "제주특별자치도"},
    {"세종", "세종특별자치시", "세종특별시"},
)
_SIDO_CANON = {name: sorted(group)[0] for group in _SIDO_GROUPS for name in group}


def _normalized_sido(value: Any) -> str:
    stripped = str(value or "").strip()
    return _SIDO_CANON.get(stripped, stripped)


def _match_metadata(metadata: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    """Apply the existing Vector analyzer's supported hard filters locally.

    Missing fields do NOT pass filters. Silently ignoring a hard constraint is
    worse than returning fewer search hits.
    """
    if "sido" in filters and filters["sido"] is not None:
        if _normalized_sido(metadata.get("sido")) != _normalized_sido(filters["sido"]):
            return False
    if "sidos" in filters and filters["sidos"] is not None:
        requested = filters["sidos"]
        if not isinstance(requested, (list, tuple)) or not requested:
            raise ValueError("sidos must be a nonempty list")
        if _normalized_sido(metadata.get("sido")) not in {_normalized_sido(x) for x in requested}:
            return False
    for name in ("sigungu", "ownership_type"):
        expected = filters.get(name)
        if expected is not None and str(metadata.get(name, "")).strip() != str(expected).strip():
            return False
    comparisons = (
        ("adult_fee", "adult_fee_min", "min"),
        ("adult_fee", "adult_fee_max", "max"),
        ("youth_fee", "youth_fee_max", "max"),
        ("child_fee", "child_fee_max", "max"),
    )
    for column, constraint, bound in comparisons:
        expected = filters.get(constraint)
        if expected is None:
            continue
        actual = metadata.get(column)
        if actual is None or isinstance(actual, bool):
            return False
        try:
            actual_number, expected_number = float(actual), float(expected)
        except (ValueError, TypeError):
            return False
        if not math.isfinite(actual_number) or not math.isfinite(expected_number):
            return False
        if bound == "min" and actual_number < expected_number:
            return False
        if bound == "max" and actual_number > expected_number:
            return False
    return True


def _metadata_fields_for_filter(key: str) -> str:
    return {"sidos": "sido", "adult_fee_min": "adult_fee", "adult_fee_max": "adult_fee",
            "youth_fee_max": "youth_fee", "child_fee_max": "child_fee"}.get(key, key)


def _parse_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    """Handle nested JSON metadata plus flat columns from a TextSpan export."""
    raw = record.get("metadata") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, Mapping):
        raise ValueError("metadata must be a dictionary or JSON object string")
    metadata = dict(raw)
    for key in ("name", "sido", "sigungu", "ownership_type", "adult_fee", "youth_fee", "child_fee"):
        if key not in metadata and record.get(key) not in (None, ""):
            metadata[key] = record[key]
    return metadata


class BM25SpanRetriever:
    """Corpus-wide BM25 search via the uploaded BM25Reranker's public method.

    Pass one global corpus during startup and reuse this object for queries.
    ``search`` accepts the existing HybridSearchService BM25 contract.
    """

    def __init__(
        self,
        spans: Sequence[SpanDocument],
        *,
        metadata_by_museum: Mapping[str, Mapping[str, Any]] | None = None,
        tokenize: Callable[[str], list[str]] | None = None,
    ) -> None:
        copied_spans = tuple(spans)
        if not copied_spans:
            raise ValueError("BM25 corpus is empty: supply TextSpan export or populated Chroma collection")
        self._ranker = BM25Reranker(copied_spans, tokenize=tokenize)
        self._museum_ids = tuple(sorted({span.museum_id for span in copied_spans}))
        provided = metadata_by_museum or {}
        self._metadata = {str(mid): dict(meta) for mid, meta in provided.items()}
        self.span_count = len(copied_spans)
        self.museum_count = len(self._museum_ids)

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("BM25 query must be nonempty")
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        cleaned_filters = {key: value for key, value in dict(filters or {}).items() if value is not None}
        unexpected = set(cleaned_filters) - _FILTER_KEYS
        if unexpected:
            raise ValueError(f"Unsupported BM25 metadata filters: {sorted(unexpected)}")
        if cleaned_filters:
            # Guard against an export without metadata: never silently ignore filters.
            missing = sorted({
                _metadata_fields_for_filter(key) for key in cleaned_filters
                if not any(_metadata_fields_for_filter(key) in meta for meta in self._metadata.values())
            })
            if missing:
                raise ValueError(f"BM25 corpus lacks required filter metadata: {missing}")
        eligible = [mid for mid in self._museum_ids if _match_metadata(self._metadata.get(mid, {}), cleaned_filters)]
        if not eligible:
            return []

        # The provided rerank() already computes *global* IDF using ALL spans.
        # With ALL eligible museum IDs passed here, vector_weight=0 suppresses
        # vector contributions entirely. Its BM25-only RRF is monotone in BM25
        # rank, so the resulting order is exactly independent BM25 order.
        ranked = self._ranker.rerank(
            query, eligible, top_k=top_k, vector_weight=0.0, bm25_weight=1.0,
        )
        results: list[dict[str, Any]] = []
        for museum in ranked:
            # Original ranker includes zero-score IDs as fallback; do not pass
            # these to RRF as misleading sparse evidence.
            if museum.bm25_score <= 0 or museum.bm25_rank is None:
                continue
            meta = dict(self._metadata.get(museum.museum_id, {}))
            results.append({
                "museum_id": museum.museum_id,
                "name": meta.get("name"),
                "document": museum.best_span_text or "",
                "metadata": meta,
                "score": museum.bm25_score,
                "rank": len(results) + 1,
                "retriever": "bm25",
                "best_span_id": museum.best_span_id,
                "best_span_text": museum.best_span_text,
            })
        return results

    @classmethod
    def from_file(
        cls, path: str | Path, *, tokenize: Callable[[str], list[str]] | None = None,
    ) -> BM25SpanRetriever:
        """Load an exported corpus; JSONL/CSV rows need museum_id, span_id, text.

        Optional name/sido/sigungu/fee columns or `metadata` map enable filters.
        This reads files locally and makes no graph/database queries.
        """
        source = Path(path)
        if source.suffix.lower() == ".jsonl":
            with source.open("r", encoding="utf-8-sig") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
        elif source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        else:
            raise ValueError("Only .jsonl and .csv TextSpan corpus files are supported")
        spans: list[SpanDocument] = []
        metadata: dict[str, dict[str, Any]] = {}
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise ValueError(f"Corpus row {i} is not an object")
            mid = str(row.get("museum_id") or "").strip()
            sid = str(row.get("span_id") or "").strip()
            body = str(row.get("text") or "").strip()
            if not mid or not sid or not body:
                raise ValueError(f"Corpus row {i} requires museum_id, span_id, text")
            spans.append(SpanDocument(museum_id=mid, span_id=sid, text=body))
            info = _parse_metadata(row)
            if info:
                existing = metadata.setdefault(mid, {})
                for key, value in info.items():
                    if key in existing and existing[key] != value:
                        raise ValueError(f"Inconsistent metadata for museum {mid}, field {key}")
                    existing[key] = value
        return cls(spans, metadata_by_museum=metadata, tokenize=tokenize)

    @classmethod
    def from_chroma(
        cls,
        *,
        collection: Any | None = None,
        db_path: str | Path | None = None,
        collection_name: str = "museum_documents",
        batch_size: int = 256,
        tokenize: Callable[[str], list[str]] | None = None,
    ) -> BM25SpanRetriever:
        """Build the same BM25 algorithm from existing Chroma docs, read-only.

        The existing Chroma collection stores one museum per document. This
        fallback intentionally uses the same corpus as Vector; it does not
        claim to have the graph's TextSpan/SourceDocument provenance.
        """
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if collection is None:
            import chromadb
            project_root = Path(__file__).resolve().parents[2]
            path = Path(db_path) if db_path is not None else Path("data/vector_db/museum_chroma")
            path = path if path.is_absolute() else project_root / path
            if not path.is_dir():
                raise FileNotFoundError(f"Chroma collection path does not exist: {path}")
            client = chromadb.PersistentClient(path=str(path))
            collection = client.get_collection(collection_name)
        count = int(collection.count())
        spans: list[SpanDocument] = []
        metadata: dict[str, dict[str, Any]] = {}
        for offset in range(0, count, batch_size):
            page = collection.get(
                include=["documents", "metadatas"], limit=batch_size, offset=offset,
            )
            ids = page.get("ids") or []
            documents = page.get("documents") or []
            metadatas = page.get("metadatas") or []
            if len(ids) != len(documents) or len(ids) != len(metadatas):
                raise ValueError("Chroma returned misaligned ids/documents/metadatas")
            for raw_id, document, info in zip(ids, documents, metadatas):
                mid = str(raw_id).strip()
                if not mid:
                    raise ValueError("Chroma returned an empty document ID")
                details = dict(info or {})
                meta_id = details.get("museum_id")
                if meta_id is not None and str(meta_id).strip() != mid:
                    raise ValueError(f"Chroma ID mismatches metadata museum_id: {mid}")
                if not str(document or "").strip():
                    continue
                # One museum document in the current Chroma schema. Document IDs
                # must be unique, and span_id is intentionally synthetic.
                spans.append(SpanDocument(museum_id=mid, span_id=f"chroma:{mid}", text=str(document)))
                metadata[mid] = details
        return cls(spans, metadata_by_museum=metadata, tokenize=tokenize)
