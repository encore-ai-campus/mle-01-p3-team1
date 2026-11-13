"""Interface adapters, not retrievers. Hybrid search belongs to the teammate."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Mapping

from .state import Config, SearchNode, SupervisorState


class ContractError(ValueError):
    """A retriever did not return the documented integration contract."""


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise ContractError("Evidence must be a mapping, dataclass, or Pydantic model")


def _strings(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        if value.lstrip().startswith("["):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ContractError("Malformed JSON list in metadata") from exc
        else:
            value = [value]
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise ContractError("Expected a string or list[str]")
    return list(dict.fromkeys(v.strip() for v in value if v.strip()))


def _evidence(rows: Any, origin: str, limit: int | None = None) -> list[dict[str, Any]]:
    if not isinstance(rows, (list, tuple)):
        raise ContractError("Evidence must be a list")
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        item = _mapping(row)
        metadata = _mapping(item.get("metadata") or {})
        museum_id = item.get("museum_id") or metadata.get("museum_id")
        text = item.get("text") or item.get("document")
        if not isinstance(museum_id, str) or not museum_id.strip():
            raise ContractError("Evidence lacks a nonempty string museum_id")
        if not isinstance(text, str) or not text.strip():
            raise ContractError("Evidence lacks nonempty text/document")
        item.update(museum_id=museum_id.strip(), text=text, metadata=metadata)
        for key in ("name", "sido", "sigungu", "span_id", "chunk_id", "source_locator"):
            item[key] = item.get(key) or metadata.get(key) or ""
        for key in ("source_doc_ids", "source_urls"):
            item[key] = _strings(item.get(key) or metadata.get(key))
        # A public URL can identify evidence, but a museum homepage is not
        # silently treated as the direct source URL.
        source_url = item.get("source_url") or metadata.get("source_url")
        if source_url:
            item["source_urls"] = list(dict.fromkeys(item["source_urls"] + _strings(source_url)))
        item["retriever"] = item.get("retriever") or origin
        item["retrievers"] = _strings(item.get("retrievers") or item["retriever"])
        key = (item["museum_id"], str(item["span_id"] or item["chunk_id"]),
               " ".join(text.split()).casefold())
        if key in unique:
            old = unique[key]
            for field in ("source_doc_ids", "source_urls", "retrievers"):
                old[field] = list(dict.fromkeys(old[field] + item[field]))
            if len(old["retrievers"]) > 1:
                old["retriever"] = "hybrid"
        else:
            unique[key] = item
    result = list(unique.values())
    if limit is not None:
        result = result[:limit]
    for index, item in enumerate(result, 1):
        item["evidence_id"] = f"E{index}"
    return result


def normalize_result(route: str, result: Mapping[str, Any], top_k: int) -> dict[str, Any]:
    """Whitelist search fields; prevent a backend from setting verified/retry_count.

    Keep the teammate's final ranking. Do not fuse incomparable scores and do
    not deduplicate by museum_id alone. Each call replaces previous evidence.
    """
    if not isinstance(result, Mapping):
        raise ContractError("Search result must be a mapping")
    component_key = {"vector": "vector_evidence", "graph": "graph_evidence"}.get(route)
    if "evidence" not in result and (not component_key or component_key not in result):
        raise ContractError("Hybrid result requires a final evidence list")
    vector = _evidence(result.get("vector_evidence", []), "vector")
    graph = _evidence(result.get("graph_evidence", []), "graph")
    final_rows = result["evidence"] if "evidence" in result else result[component_key]
    final = _evidence(final_rows, route, top_k)
    status = result.get("vector_search_status", "not_run")
    if status not in {"ok", "partial", "no_results", "not_run", "error"}:
        raise ContractError("Unknown vector_search_status")
    return {
        "vector_evidence": vector,
        "vector_source_ids": _strings(result.get("vector_source_ids")),
        "vector_search_status": status,
        "vector_search_diagnostics": _mapping(result.get("vector_search_diagnostics") or {}),
        "graph_evidence": graph,
        "hybrid_search_diagnostics": _mapping(result.get("hybrid_search_diagnostics") or {}),
        "evidence": final,
    }


def empty_result() -> dict[str, Any]:
    return {"vector_evidence": [], "vector_source_ids": [],
            "vector_search_status": "not_run", "vector_search_diagnostics": {},
            "graph_evidence": [], "hybrid_search_diagnostics": {}, "evidence": []}


def adapt_vector(retriever: Any) -> SearchNode:
    """Adapt the supplied VectorSearchRetriever.retrieve(query, top_k) contract."""
    def call(state: SupervisorState, config: Config = None) -> Mapping[str, Any]:
        result = retriever.retrieve(query=state["question"], top_k=state["top_k"])
        if not isinstance(result, Mapping):
            raise ContractError("Vector retrieve() must return a mapping")
        required = {"results", "source_ids", "status", "warnings", "unsupported_constraints", "search_summary"}
        if not required.issubset(result):
            raise ContractError("Vector result is missing documented fields")
        return {"evidence": result["results"], "vector_evidence": result["results"],
                "vector_source_ids": result["source_ids"],
                "vector_search_status": result["status"],
                "vector_search_diagnostics": {**dict(result["search_summary"]),
                    "warnings": result["warnings"],
                    "unsupported_constraints": result["unsupported_constraints"]}}
    return call


def adapt_graph(retriever: Any) -> SearchNode:
    """Adapt the supplied Neo4jText2Cypher.search(question, k) contract."""
    def call(state: SupervisorState, config: Config = None) -> Mapping[str, Any]:
        rows = retriever.search(state["question"], k=state["top_k"])
        return {"evidence": rows, "graph_evidence": rows}
    return call


def adapt_hybrid(search_node: Callable, *, accepts_config: bool = False) -> SearchNode:
    """Connect the teammate's state -> state-update function or graph.invoke.

    This adapter does NOT perform Vector + Graph retrieval. Set accepts_config
    only if the supplied callable accepts config=, e.g. a compiled graph.invoke.
    """
    def call(state: SupervisorState, config: Config = None) -> Mapping[str, Any]:
        payload = {"question": state["question"], "top_k": state["top_k"],
                   "retry_count": state.get("retry_count", 0),
                   "feedback": state.get("feedback", "")}
        if accepts_config:
            return search_node(deepcopy(payload), config=config)
        return search_node(deepcopy(payload))
    return call
