"""Supervisor policies and nodes, independent of the LangGraph dependency."""
from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .adapters import empty_result, normalize_result
from .state import (AnswerDraft, Answerer, Config, RouteDecision, Router, SearchNode,
                    SupervisorState, VerificationResult, Verifier)

STRUCTURED_FACT_PATTERN = re.compile(
    r"지역|소재|주소|위치|시\s*군\s*구|시·도|관람료|입장료|요금|비용|무료|운영\s*시간|개관|폐관|휴관|휴무|소유|운영\s*기관|관리\s*기관|관계|개수|"
    r"\b(?:location|address|region|fees?|price|hours|opening|closure|operator|ownership|relationship|count)\b",
    re.IGNORECASE,
)
# Wording that asks for something found in a museum description (exhibits, history,
# experiences). A relation question that also contains it needs both searches.
DESCRIPTIVE_CUE = re.compile(
    r"전시|유물|소장|체험|프로그램|역사|문화재|시대|특별전|상설전|볼 수|관람할 수|구경할 수|배울 수"
)


class SupervisorController:
    """Owns routing/retry/finalization. Search implementations are injected.

    The verifier is REQUIRED. Citation validation alone never establishes
    factual correctness. Use a real verifier in production, not demo helpers.
    """
    def __init__(self, *, hybrid_search: SearchNode, route_question: Router,
                 answer_question: Answerer, verify_answer: Verifier,
                 vector_search: SearchNode | None = None,
                 graph_search: SearchNode | None = None, max_retries: int = 1,
                 metadata_provenance=None, region_theme_routing: bool = False):
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
        if metadata_provenance is not None and not callable(metadata_provenance):
            raise TypeError("metadata_provenance must be callable")
        self.metadata_provenance = metadata_provenance
        self.region_theme_routing = region_theme_routing

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
        if override not in {"auto", "vector", "graph", "hybrid", "combined"}:
            raise ValueError("Unknown route_override")
        # A new request never inherits evidence or approval from a previous run.
        return {**empty_result(), "question": question, "top_k": top_k,
                "route_override": override, "route": "hybrid", "route_reason": "",
                "retry_count": 0, "feedback": "", "candidate_answer": "", "answer": "",
                "cited_evidence_ids": [], "verified": False, "verification_reason": "",
                "missing_aspects": [], "failure_reason": "", "no_record_reason": "", "next_action": "",
                "sources": [], "status": "running", "errors": [],
                "trace": [{"step": "initialize", "retry_count": 0}]}

    def supervisor(self, state: SupervisorState, config: Config = None) -> dict:
        try:
            if state["retry_count"] > 0:
                missing = " ".join(str(value) for value in state.get("missing_aspects", []))
                missing += " " + str(state.get("feedback", ""))
                graph_needed = bool(STRUCTURED_FACT_PATTERN.search(missing))
                current_route = state.get("route")
                if state.get("route_override") != "auto" and (self.searchers.get(current_route) or current_route == "combined"):
                    retry_route = current_route
                elif current_route == "combined":
                    # The combined attempt already used both searches; ask the document search again.
                    retry_route = "hybrid"
                elif current_route == "graph":
                    # Repeating a graph attempt that found nothing rarely helps (2026-11-14
                    # eval: 17 of 27 graph-routed v1 questions abstained). Retry graph only
                    # when it found evidence and the missing part is a structured fact.
                    had_evidence = bool(state.get("evidence"))
                    retry_route = "graph" if had_evidence and graph_needed else "hybrid"
                elif self.searchers["graph"] and graph_needed:
                    retry_route = "graph"
                else:
                    retry_route = "hybrid"
                decision = RouteDecision(retry_route, f"Retry with {retry_route}; keep original question and feedback")
            elif state["route_override"] != "auto":
                decision = RouteDecision(state["route_override"], "Explicit route_override")
            elif self.region_theme_routing and self._simple_region_theme(state["question"]):
                decision = RouteDecision("hybrid", "지역 필터와 주제 검색을 함께 적용")
            elif self.region_theme_routing and self._structured_conditions(state["question"]):
                decision = RouteDecision(
                    "hybrid", "구조 조건은 온톨로지 후보 필터로 거르고 Hybrid가 그 안에서 순위를 정함"
                )
            elif self.searchers["graph"] is not None and (template := self._graph_template(state["question"])):
                if DESCRIPTIVE_CUE.search(state["question"]):
                    decision = RouteDecision(
                        "combined", f"준비된 그래프 쿼리({template})로 관계를 조회하고 문서 검색으로 설명 근거를 함께 모음")
                else:
                    decision = RouteDecision("graph", f"준비된 그래프 쿼리({template})로 관계를 조회")
            else:
                route_state = deepcopy(state)
                route_state["available_routes"] = [name for name, searcher in self.searchers.items() if searcher is not None]
                if self.searchers["graph"] is not None:
                    route_state["available_routes"].append("combined")
                decision = self.route_question(route_state, config)
            if not isinstance(decision, RouteDecision):
                raise TypeError("Router must return RouteDecision")
            route, reason = decision.route, decision.reason
            if route == "combined" and self.searchers["graph"] is None:
                reason = f"graph unavailable; use document search only. {reason}"
                route = "hybrid"
            if route not in ("abstain", "combined") and self.searchers[route] is None:
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

    @staticmethod
    def _simple_region_theme(question: str) -> str | None:
        from src.hybrid.region_theme import simple_region_theme
        return simple_region_theme(question)

    @staticmethod
    def _graph_template(question: str) -> str | None:
        """Name of the prepared (LLM-free) graph query this question matches, if any."""
        try:
            from src.agent.neo4j_text2cypher import _prepare_common_query
            prepared = _prepare_common_query(question, 5)
        except Exception:
            return None
        return prepared[0] if prepared else None

    @staticmethod
    def _structured_conditions(question: str) -> bool:
        from src.hybrid.ontology_filter import default_candidate_filter, extract_conditions
        if default_candidate_filter() is None:
            return False
        return extract_conditions(question).has_hard_conditions

    @staticmethod
    def _no_record_reason(summary: Mapping[str, Any]) -> str:
        """Korean reason when the ontology filter matched no recorded facility."""
        decision = summary.get("ontology_filter") if isinstance(summary, Mapping) else None
        if not isinstance(decision, Mapping) or decision.get("status") != "empty":
            return ""
        conditions = decision.get("conditions") or {}
        parts = []
        region = " ".join(str(conditions[key]) for key in ("sido", "sigungu") if conditions.get(key))
        if region:
            parts.append(region)
        if conditions.get("amenities"):
            parts.append("편의시설 " + "·".join(conditions["amenities"]))
        if conditions.get("open_weekdays"):
            parts.append("".join(conditions["open_weekdays"]) + "요일 개관")
        return f"기록된 데이터에서 조건({', '.join(parts)})을 모두 만족하는 시설을 찾지 못했습니다."

    def search(self, state: SupervisorState, config: Config = None) -> dict:
        route = state["route"]
        reset = {**empty_result(), "candidate_answer": "", "cited_evidence_ids": [],
                 "verified": False, "verification_reason": "", "missing_aspects": [],
                 "answer": "", "sources": [], "failure_reason": "", "no_record_reason": ""}
        if route == "combined":
            return self._search_combined(state, reset, config)
        try:
            fn = self.searchers.get(route)
            if fn is None:
                raise ValueError("Requested backend is not connected")
            # Every attempt starts without stale search results. Only feedback is carried.
            request = {**deepcopy(state), **reset}
            result = fn(request, config)
            normalized = normalize_result(route, result, state["top_k"])
            normalized["evidence"] = self._prepare_evidence(route, normalized["evidence"])
            diagnostics = (normalized["graph_search_diagnostics"] if route == "graph" else
                           normalized["hybrid_search_diagnostics"].get("search_summary", {}) if route == "hybrid" else {})
            no_record = self._no_record_reason(diagnostics) if route == "hybrid" else ""
            if no_record:
                reset = {**reset, "failure_reason": no_record}
            return {**reset, **normalized, "no_record_reason": no_record,
                    "trace": self._trace(state, f"{route}_search", route=route,
                                         evidence_count=len(normalized["evidence"]),
                                         search_timings=deepcopy(diagnostics))}
        except Exception as exc:
            return {**reset, "failure_reason": f"Search failed ({type(exc).__name__})",
                    "errors": self._error(state, f"{route}_search", exc),
                    "trace": self._trace(state, f"{route}_search", route=route, evidence_count=0)}

    def _prepare_evidence(self, route: str, items: list[dict]) -> list[dict]:
        """Drop backend-supplied provenance and attach the CSV provenance (not for graph rows)."""
        prepared = []
        for item in items:
            cleaned = dict(item)
            cleaned.pop("metadata_provenance", None)
            if isinstance(cleaned.get("metadata"), Mapping):
                cleaned["metadata"] = dict(cleaned["metadata"])
                cleaned["metadata"].pop("metadata_provenance", None)
            if self.metadata_provenance is not None and route != "graph":
                cleaned = dict(self.metadata_provenance(cleaned))
            prepared.append(cleaned)
        return prepared

    def _search_combined(self, state: SupervisorState, reset: dict, config: Config = None) -> dict:
        """Graph first, then the document search inside the facilities the graph found.

        The graph result decides which facilities qualify (same operator, same region ...);
        the document search ranks their descriptions. Without graph facilities the document
        search runs unrestricted. Scores are never mixed: document evidence keeps its
        ranking, graph rows carry no relevance score, so the lists are appended (document
        first) and renumbered. One branch failing leaves the other branch's evidence in place.
        """
        top_k = state["top_k"]
        request = {**deepcopy(state), **reset}

        def run(name: str, extra: Mapping[str, Any] | None = None):
            try:
                result = self.searchers[name](deepcopy({**request, **(extra or {})}), config)
                return normalize_result(name, result, top_k), None
            except Exception as exc:
                return None, exc

        graph, graph_error = run("graph")
        graph_ids = list(dict.fromkeys(
            str(row["museum_id"]) for row in (graph["evidence"] if graph else [])
            if row.get("museum_id") and row.get("evidence_role") != "anchor"))
        document, document_error = run("hybrid", {"candidate_museum_ids": graph_ids} if graph_ids else None)
        document_rows = self._prepare_evidence("hybrid", document["evidence"]) if document else []
        graph_rows = self._prepare_evidence("graph", graph["evidence"]) if graph else []
        for row in document_rows:
            row["retrieval_branch"] = "document"
        seen = {(row.get("museum_id"), " ".join(str(row.get("text", "")).split()).casefold()) for row in document_rows}
        graph_kept = []
        for row in graph_rows:
            key = (row.get("museum_id"), " ".join(str(row.get("text", "")).split()).casefold())
            if key in seen:
                continue
            seen.add(key)
            row["retrieval_branch"] = "graph"
            graph_kept.append(row)
        evidence = document_rows + graph_kept
        for index, row in enumerate(evidence, 1):
            row["evidence_id"] = f"E{index}"

        errors = list(state.get("errors", []))
        for name, exc in (("hybrid_search", document_error), ("graph_search", graph_error)):
            if exc is not None:
                errors.append({"step": name, "type": type(exc).__name__})
        merged = dict(document) if document else empty_result()
        merged["graph_evidence"] = graph_kept
        merged["graph_search_diagnostics"] = graph["graph_search_diagnostics"] if graph else {}
        merged["evidence"] = evidence
        document_diagnostics = (document["hybrid_search_diagnostics"].get("search_summary", {})
                                if document else {})
        no_record = ""
        failure = ""
        if not evidence:
            no_record = self._no_record_reason(document_diagnostics) if document else ""
            if no_record:
                failure = no_record
            elif document_error is not None and graph_error is not None:
                failure = f"Search failed ({type(document_error).__name__}, {type(graph_error).__name__})"
        failed = [name for name, exc in (("document", document_error), ("graph", graph_error)) if exc is not None]
        return {**reset, **merged, "failure_reason": failure, "no_record_reason": no_record, "errors": errors,
                "trace": self._trace(state, "combined_search", route="combined",
                                     evidence_count=len(evidence), document_evidence=len(document_rows),
                                     graph_evidence=len(graph_kept), branch_errors=failed,
                                     restricted_to=len(graph_ids),
                                     search_timings=deepcopy(document_diagnostics))}

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
        if state.get("no_record_reason") and not state["verified"]:
            # Same filter, same data: a retry would return the same empty set.
            return {"next_action": "abstain",
                    "trace": self._trace(state, "supervisor_review", action="abstain", no_record=True)}
        if state.get("route") == "combined" and not state["verified"]:
            # Both searches already ran on the same question: a document-only retry would
            # replace the graph relation with unrelated passages (2026-11-15 run).
            return {"next_action": "abstain",
                    "trace": self._trace(state, "supervisor_review", action="abstain", combined=True)}
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
        message = "확인 가능한 근거가 부족하여 답변을 보류했습니다."
        missing = [str(item).strip() for item in state.get("missing_aspects", []) if str(item).strip()]
        if missing:
            message += " 확인하지 못한 내용: " + ", ".join(missing[:3]) + "."
        if state.get("no_record_reason"):
            message = (state["no_record_reason"]
                       + " \ud3b8\uc758\uc2dc\uc124\u00b7\ud734\uad00 \uc815\ubcf4\ub294 \uc77c\ubd80 \uc2dc\uc124\uc5d0\ub9cc \uae30\ub85d\ub418\uc5b4 \uc788\uc5b4, \uae30\ub85d\uc774 \uc5c6\ub2e4\uace0 \uc2e4\uc81c\ub85c \uc5c6\ub2e4\ub294 \ub73b\uc740 \uc544\ub2d9\ub2c8\ub2e4."
                       + " \uc870\uac74\uc744 \uc904\uc5ec \ub2e4\uc2dc \uc9c8\ubb38\ud574 \uc8fc\uc138\uc694.")
        return {"answer": message, "verified": False, "status": "abstained", "sources": [],
                "candidate_answer": "", "cited_evidence_ids": [],
                "trace": self._trace(state, "abstain")}
