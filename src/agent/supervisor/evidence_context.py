"""One evidence representation for answer, verifier and evaluation judge.

Input must already have passed the retrieval/provenance boundary. A locator
identifies a recorded source; it does not imply independent human verification.
Never include raw retrieval metadata or diagnostic scores as factual evidence.
"""
import json
from collections.abc import Mapping
from typing import Any

from .state import SupervisorState

EVIDENCE_CONTEXT_VERSION = "grounded-evidence-v2"


def evidence_context(item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    payload = {
        "evidence_context_version": EVIDENCE_CONTEXT_VERSION,
        "museum_id": str(item.get("museum_id") or metadata.get("museum_id") or ""),
        "name": str(item.get("name") or metadata.get("name") or ""),
        "text": str(item.get("text") or item.get("document") or ""),
    }
    for key in ("evidence_id", "evidence_role", "source_scope", "source_doc_ids",
                "source_documents", "source_spans", "source_urls", "source_locator",
                "source_locators", "retrieval_branch"):
        if item.get(key) is not None:
            payload[key] = item[key]
    if item.get("retriever") == "graph":
        # These fields originate at the graph adapter, not arbitrary vector metadata.
        for key in ("sido", "sigungu", "ownership_type", "adult_fee", "youth_fee",
                    "child_fee", "adult_fee_status", "fee_notes", "address", "latitude",
                    "longitude", "distance_m", "distance_type", "organization", "org_key",
                    "org_type", "relation", "verification_status", "operator_raw_name",
                    "anchor_operator_raw_name", "amenities", "facility_type", "closure_weekdays",
                    "open_all_year", "topic", "theme", "confidence", "activity_types",
                    "graph_path", "matched_span_id", "matched_span_text", "related_span_id",
                    "related_span_text", "source_count"):
            if item.get(key) is not None:
                payload[key] = item[key]
    provenance = item.get("metadata_provenance") or metadata.get("metadata_provenance")
    if (isinstance(provenance, Mapping)
            and provenance.get("source_kind") == "derived_csv_row"
            and provenance.get("source_locator")
            and isinstance(provenance.get("fields"), Mapping)):
        payload["metadata_provenance"] = dict(provenance)
        # These are rule-derived matches, not extra independently verified facts.
        if metadata.get("structured_match"):
            payload["structured_match"] = metadata["structured_match"]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def prompt_context(state: SupervisorState) -> dict[str, Any]:
    # Do not leak raw candidate documents through diagnostics into the answer prompt.
    def diagnostics(key):
        source = state.get(key, {})
        return {name: source[name] for name in ("warnings", "unsupported_constraints", "status") if name in source}
    return {"question": state["question"], "evidence": [evidence_context(row) for row in state.get("evidence", [])],
            "vector_search_status": state.get("vector_search_status", "not_run"),
            "vector_search_diagnostics": diagnostics("vector_search_diagnostics"),
            "hybrid_search_diagnostics": diagnostics("hybrid_search_diagnostics"),
            "feedback": state.get("feedback", ""),
            # Present only while rewriting an answer that failed verification.
            **({"previous_answer": state["previous_answer"]} if state.get("previous_answer") else {})}
