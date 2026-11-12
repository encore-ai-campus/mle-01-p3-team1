"""검색과 답변 기능을 주입받아 GraphRAG 흐름만 조립하는 LangGraph."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .state import AgentState, Evidence, Route

SearchFn = Callable[[str, int], list[Evidence]]
RouterFn = Callable[[str], Route]
AnswerFn = Callable[[str, list[Evidence]], str]
VerifyFn = Callable[[str, str, list[Evidence]], bool]


def _is_integer(value: object) -> bool:
    """bool은 int의 하위 타입이므로 정수 설정값에서 제외한다."""
    return type(value) is int


def _dedupe_key(item: Evidence) -> tuple[str, str, tuple[str, ...], str]:
    source_ids = tuple(sorted(set(item.get("source_doc_ids", []))))
    return (
        item.get("museum_id", ""),
        item.get("chunk_id") or item.get("span_id", ""),
        source_ids,
        item.get("text", ""),
    )


def _retriever_labels(item: Evidence, fallback: str) -> list[str]:
    labels: list[str] = []
    for label in [*item.get("retrievers", []), item.get("retriever"), fallback]:
        if isinstance(label, str) and label and label not in labels:
            labels.append(label)
    return labels


def build_graph(
    *,
    vector_search: SearchFn,
    graph_search: SearchFn,
    route_question: RouterFn,
    make_answer: AnswerFn,
    verify_answer: VerifyFn,
    top_k: int = 5,
    max_retries: int = 1,
):
    """외부 검색·LLM 함수를 연결해 질의 처리 그래프를 만든다.

    검증에 실패하면 Hybrid 검색을 최대 ``max_retries``회 수행하고,
    그래도 답변을 검증하지 못하면 근거 부족 응답으로 종료한다.
    """
    if not _is_integer(top_k) or top_k < 1:
        raise ValueError("top_k는 1 이상의 정수여야 합니다.")
    if not _is_integer(max_retries) or max_retries < 0:
        raise ValueError("max_retries는 0 이상의 정수여야 합니다.")

    def supervisor(state: AgentState) -> dict:
        raw_question = state.get("question")
        if not isinstance(raw_question, str) or not raw_question.strip():
            raise ValueError("question은 비어 있지 않은 문자열이어야 합니다.")
        question = raw_question.strip()

        retry_count = state.get("retry_count", 0)
        if not _is_integer(retry_count) or retry_count < 0:
            raise ValueError("retry_count는 0 이상의 정수여야 합니다.")

        route = "hybrid" if retry_count > 0 else route_question(question)
        if route not in {"vector", "graph", "hybrid"}:
            raise ValueError(f"지원하지 않는 검색 경로: {route}")

        return {
            "question": question,
            "route": route,
            "route_trace": [*state.get("route_trace", []), route],
            "failure_reason": "",
        }

    def select_search(state: AgentState) -> Route:
        return state["route"]

    def vector_node(state: AgentState) -> dict:
        return {"evidence": vector_search(state["question"], top_k)}

    def graph_node(state: AgentState) -> dict:
        return {"evidence": graph_search(state["question"], top_k)}

    def hybrid_node(state: AgentState) -> dict:
        merged: list[Evidence] = []
        positions: dict[tuple[str, str, tuple[str, ...], str], int] = {}

        for source, results in (
            ("vector", vector_search(state["question"], top_k)),
            ("graph", graph_search(state["question"], top_k)),
        ):
            for result in results:
                item = dict(result)
                key = _dedupe_key(item)
                labels = _retriever_labels(item, source)

                if key not in positions:
                    item["retrievers"] = labels
                    item["retriever"] = labels[0] if len(labels) == 1 else "hybrid"
                    positions[key] = len(merged)
                    merged.append(item)
                    continue

                existing = merged[positions[key]]
                combined = _retriever_labels(existing, source)
                for label in labels:
                    if label not in combined:
                        combined.append(label)
                existing["retrievers"] = combined
                existing["retriever"] = combined[0] if len(combined) == 1 else "hybrid"

        return {"evidence": merged}

    def answer_node(state: AgentState) -> dict:
        evidence = state.get("evidence", [])
        if not evidence:
            return {"answer": "", "failure_reason": "검색된 근거가 없음"}

        answer = make_answer(state["question"], evidence)
        if not isinstance(answer, str):
            raise TypeError("make_answer는 문자열을 반환해야 합니다.")
        answer = answer.strip()
        if not answer:
            return {"answer": "", "failure_reason": "답변 생성 결과가 비어 있음"}
        return {"answer": answer, "failure_reason": ""}

    def verify_node(state: AgentState) -> dict:
        answer = state.get("answer", "")
        evidence = state.get("evidence", [])
        if not evidence:
            return {
                "verified": False,
                "failure_reason": state.get("failure_reason") or "검색된 근거가 없음",
            }
        if not answer:
            return {
                "verified": False,
                "failure_reason": state.get("failure_reason") or "답변 생성 결과가 비어 있음",
            }

        verified = verify_answer(state["question"], answer, evidence)
        if not isinstance(verified, bool):
            raise TypeError("verify_answer는 bool을 반환해야 합니다.")
        return {
            "verified": verified,
            "failure_reason": "" if verified else "답변 검증 실패",
        }

    def next_after_verify(state: AgentState) -> Literal["done", "retry", "abstain"]:
        if state.get("verified", False):
            return "done"
        if state.get("retry_count", 0) < max_retries:
            return "retry"
        return "abstain"

    def retry_node(state: AgentState) -> dict:
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "evidence": [],
            "answer": "",
            "verified": False,
        }

    def abstain_node(state: AgentState) -> dict:
        return {
            "answer": "현재 확보된 근거만으로는 정확한 답변을 확인할 수 없습니다.",
            "verified": False,
            "failure_reason": state.get("failure_reason") or "근거 부족",
        }

    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("vector_search", vector_node)
    workflow.add_node("graph_search", graph_node)
    workflow.add_node("hybrid_search", hybrid_node)
    workflow.add_node("answer", answer_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("retry", retry_node)
    workflow.add_node("abstain", abstain_node)

    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        select_search,
        {"vector": "vector_search", "graph": "graph_search", "hybrid": "hybrid_search"},
    )
    for node in ("vector_search", "graph_search", "hybrid_search"):
        workflow.add_edge(node, "answer")
    workflow.add_edge("answer", "verify")
    workflow.add_conditional_edges(
        "verify",
        next_after_verify,
        {"done": END, "retry": "retry", "abstain": "abstain"},
    )
    workflow.add_edge("retry", "supervisor")
    workflow.add_edge("abstain", END)
    return workflow.compile()
