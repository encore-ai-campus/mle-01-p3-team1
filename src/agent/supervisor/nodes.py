"""Supervisor policies and nodes, independent of the LangGraph dependency."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .adapters import empty_result, normalize_result
from .state import (AnswerDraft, Answerer, Config, RouteDecision, Router, SearchNode,
                    SupervisorState, VerificationResult, Verifier)


class SupervisorController:
    """Owns routing/retry/finalization. Search implementations are injected.

    The verifier is REQUIRED. Citation validation alone never establishes
    factual correctness. Use a real verifier in production, not demo helpers.
    """
    def __init__(self, *, hybrid_search: SearchNode, route_question: Router,
                 answer_question: Answerer, verify_answer: Verifier,
                 vector_search: SearchNode | None = None,
                 graph_search: SearchNode | None = None, max_retries: int = 1):
        if type(max_retries) is not int or not 0 <= max_retries <= 2:
            raise ValueError("max_retries must be 0, 1 or 2")
        for fn in (hybrid_search, route_question, answer_question, verify_answer):
            if not callable(fn):
                raise TypeError("Hybrid search, router, answerer and verifier are required callables")
        self.searchers = {"vector": vector_search, "graph": graph_search, "hybrid": hybrid_search}
        self.route_question = route_question
        self.answer_question = answer_question
        self.verify_answer = verify_answer
        self.max_retries = max_retries

    @staticmethod
    def _trace(state: SupervisorState, step: str, **values: Any) -> list[dict]:
        return [*state.get("trace", []), {"step": step,
                 "retry_count": state.get("retry_count", 0), **values}]

    @staticmethod
    def _error(state: SupervisorState, step: str, exc: Exception) -> list[dict]:
        # Exception messages can contain URIs/API keys/passwords. Store only type.
        return [*state.get("errors", []), {"step": step, "type": type(exc).__name__}]

    def initialize(self, state: SupervisorState) -> dict:
        question = state.get("question")
        top_k = state.get("top_k", 5)
        override = state.get("route_override", "auto")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a nonempty string")
        if type(top_k) is not int or not 1 <= top_k <= 50:
            raise ValueError("top_k must be an integer from 1 to 50")
        if override not in {"auto", "vector", "graph", "hybrid"}:
            raise ValueError("Unknown route_override")
        # A new request never inherits evidence or approval from a previous run.
        return {**empty_result(), "question": question, "top_k": top_k,
                "route_override": override, "route": "hybrid", "route_reason": "",
                "retry_count": 0, "feedback": "", "candidate_answer": "", "answer": "",
                "cited_evidence_ids": [], "verified": False, "verification_reason": "",
                "missing_aspects": [], "failure_reason": "", "next_action": "",
                "sources": [], "status": "running", "errors": [],
                "trace": [{"step": "initialize", "retry_count": 0}]}

    def supervisor(self, state: SupervisorState, config: Config = None) -> dict:
        try:
            if state["retry_count"] > 0:
                decision = RouteDecision("hybrid", "Retry with hybrid; keep original question and feedback")
            elif state["route_override"] != "auto":
                decision = RouteDecision(state["route_override"], "Explicit route_override")
            else:
                decision = self.route_question(deepcopy(state), config)
            if not isinstance(decision, RouteDecision):
                raise TypeError("Router must return RouteDecision")
            route, reason = decision.route, decision.reason
            if route != "abstain" and self.searchers[route] is None:
                reason = f"{route} unavailable; delegate to connected hybrid backend. {reason}"
                route = "hybrid"
            update = {"route": route, "route_reason": reason,
                      "trace": self._trace(state, "supervisor", route=route, reason=reason)}
            if route == "abstain":
                update["failure_reason"] = reason or "Request cannot be answered within this service"
            return update
        except Exception as exc:
            return {"route": "abstain", "route_reason": "Routing failed",
                    "failure_reason": f"Routing failed ({type(exc).__name__})",
                    "errors": self._error(state, "supervisor", exc),
                    "trace": self._trace(state, "supervisor", route="abstain")}

    def search(self, state: SupervisorState, config: Config = None) -> dict:
        route = state["route"]
        reset = {**empty_result(), "candidate_answer": "", "cited_evidence_ids": [],
                 "verified": False, "verification_reason": "", "missing_aspects": [],
                 "answer": "", "sources": [], "failure_reason": ""}
        try:
            fn = self.searchers.get(route)
            if fn is None:
                raise ValueError("Requested backend is not connected")
            # Every attempt starts without stale search results. Only feedback is carried.
            request = {**deepcopy(state), **reset}
            result = fn(request, config)
            normalized = normalize_result(route, result, state["top_k"])
            return {**reset, **normalized,
                    "trace": self._trace(state, f"{route}_search", route=route,
                                         evidence_count=len(normalized["evidence"]))}
        except Exception as exc:
            return {**reset, "failure_reason": f"Search failed ({type(exc).__name__})",
                    "errors": self._error(state, f"{route}_search", exc),
                    "trace": self._trace(state, f"{route}_search", route=route, evidence_count=0)}

    def answer(self, state: SupervisorState, config: Config = None) -> dict:
        if not state["evidence"]:
            return {"candidate_answer": "", "cited_evidence_ids": [],
                    "failure_reason": state["failure_reason"] or "No evidence returned",
                    "trace": self._trace(state, "answer", skipped=True)}
        try:
            draft = self.answer_question(deepcopy(state), config)
            if not isinstance(draft, AnswerDraft):
                raise TypeError("Answerer must return AnswerDraft")
            return {"candidate_answer": draft.text, "cited_evidence_ids": draft.cited_evidence_ids,
                    "trace": self._trace(state, "answer", skipped=False)}
        except Exception as exc:
            return {"candidate_answer": "", "cited_evidence_ids": [],
                    "failure_reason": f"Answer generation failed ({type(exc).__name__})",
                    "errors": self._error(state, "answer", exc),
                    "trace": self._trace(state, "answer", error=type(exc).__name__)}

    @staticmethod
    def _citation_problem(state: SupervisorState) -> str:
        if not state["evidence"]:
            return state["failure_reason"] or "No evidence returned"
        if not state["candidate_answer"].strip():
            return state["failure_reason"] or "Empty answer"
        selected = set(state["cited_evidence_ids"])
        available = {e["evidence_id"]: e for e in state["evidence"]}
        markers = set(re.findall(r"\[(E\d+)\]", state["candidate_answer"]))
        if not selected or not selected.issubset(available) or selected != markers:
            return "Missing, unknown, or inconsistent evidence citations"
        for key in selected:
            item = available[key]
            if not (item.get("source_doc_ids") or item.get("source_locator") or item.get("source_urls")):
                return "Cited evidence has no source provenance"
        return ""

    def verify(self, state: SupervisorState, config: Config = None) -> dict:
        problem = self._citation_problem(state)
        if problem:
            return {"verified": False, "verification_reason": problem,
                    "failure_reason": problem, "missing_aspects": [],
                    "trace": self._trace(state, "verify", passed=False, structural_failure=True)}
        try:
            verdict = self.verify_answer(deepcopy(state), config)
            if not isinstance(verdict, VerificationResult):
                raise TypeError("Verifier must return VerificationResult")
            # Partial vector status alone is NOT a failure. The verifier must
            # judge required conditions against ALL returned evidence/diagnostics.
            passed = verdict.passed and not verdict.missing_aspects
            reason = verdict.reason
            if verdict.missing_aspects:
                reason += "; unresolved: " + ", ".join(verdict.missing_aspects)
            if not passed and not reason:
                reason = "Verifier rejected the answer"
            return {"verified": passed, "verification_reason": reason,
                    "missing_aspects": verdict.missing_aspects,
                    "failure_reason": "" if passed else reason,
                    "trace": self._trace(state, "verify", passed=passed, structural_failure=False)}
        except Exception as exc:
            reason = f"Verification failed ({type(exc).__name__})"
            return {"verified": False, "verification_reason": reason, "failure_reason": reason,
                    "errors": self._error(state, "verify", exc),
                    "trace": self._trace(state, "verify", passed=False, error=type(exc).__name__)}

    def review(self, state: SupervisorState) -> dict:
        action = "finish" if state["verified"] else (
            "retry" if state["retry_count"] < self.max_retries else "abstain")
        return {"next_action": action, "trace": self._trace(state, "supervisor_review", action=action)}

    def retry(self, state: SupervisorState) -> dict:
        return {"retry_count": state["retry_count"] + 1,
                "feedback": state["failure_reason"],
                "trace": self._trace(state, "retry", next_attempt=state["retry_count"] + 1)}

    def finish(self, state: SupervisorState) -> dict:
        wanted = set(state["cited_evidence_ids"])
        sources = [deepcopy(e) for e in state["evidence"] if e["evidence_id"] in wanted]
        return {"answer": state["candidate_answer"], "status": "answered", "sources": sources,
                "trace": self._trace(state, "finish")}

    def abstain(self, state: SupervisorState) -> dict:
        message = "\ud655\uc778 \uac00\ub2a5\ud55c \uadfc\uac70\uac00 \ubd80\uc871\ud558\uc5ec \ub2f5\ubcc0\uc744 \ubcf4\ub958\ud588\uc74c."
        return {"answer": message, "verified": False, "status": "abstained", "sources": [],
                "candidate_answer": "", "cited_evidence_ids": [],
                "trace": self._trace(state, "abstain")}
