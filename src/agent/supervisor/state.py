"""Supervisor-only contracts. Existing src/agent/state.py is not replaced."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, TypedDict

Route = Literal["vector", "graph", "hybrid", "abstain"]
Config = Mapping[str, Any] | None


class RequestState(TypedDict, total=False):
    question: str
    top_k: int
    route_override: Literal["auto", "vector", "graph", "hybrid"]


class SupervisorState(RequestState, total=False):
    route: Route
    route_reason: str
    retry_count: int
    feedback: str
    vector_evidence: list[dict[str, Any]]
    vector_source_ids: list[str]  # Museum IDs, NOT SourceDocument IDs.
    vector_search_status: str
    vector_search_diagnostics: dict[str, Any]
    graph_evidence: list[dict[str, Any]]
    hybrid_search_diagnostics: dict[str, Any]
    evidence: list[dict[str, Any]]
    candidate_answer: str
    cited_evidence_ids: list[str]
    answer: str
    verified: bool
    verification_reason: str
    missing_aspects: list[str]
    failure_reason: str
    next_action: str
    status: str
    sources: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    errors: list[dict[str, str]]


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str

    def __post_init__(self):
        if self.route not in {"vector", "graph", "hybrid", "abstain"}:
            raise ValueError("Unknown route")
        if not isinstance(self.reason, str):
            raise TypeError("Route reason must be a string")


@dataclass(frozen=True)
class AnswerDraft:
    text: str
    cited_evidence_ids: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError("Answer must be a string")
        if not isinstance(self.cited_evidence_ids, list) or any(
            not isinstance(item, str) for item in self.cited_evidence_ids
        ):
            raise TypeError("cited_evidence_ids must be list[str]")


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    reason: str
    missing_aspects: list[str] = field(default_factory=list)

    def __post_init__(self):
        # bool('false') is True; never coerce arbitrary strings to verdicts.
        if type(self.passed) is not bool:
            raise TypeError("passed must be a boolean")
        if not isinstance(self.reason, str):
            raise TypeError("Verification reason must be a string")
        if not isinstance(self.missing_aspects, list) or any(
            not isinstance(item, str) for item in self.missing_aspects
        ):
            raise TypeError("missing_aspects must be list[str]")


SearchNode = Callable[[SupervisorState, Config], Mapping[str, Any]]
Router = Callable[[SupervisorState, Config], RouteDecision]
Answerer = Callable[[SupervisorState, Config], AnswerDraft]
Verifier = Callable[[SupervisorState, Config], VerificationResult]
