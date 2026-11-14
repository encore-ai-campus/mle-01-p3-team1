"""Real LangGraph assembly. Does not reimplement teammate retrieval."""
from __future__ import annotations

from time import perf_counter
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from .nodes import SupervisorController
from .state import RequestState, SupervisorState


def build_supervisor(*, hybrid_search, route_question, answer_question, verify_answer,
                     vector_search=None, graph_search=None, max_retries: int = 1,
                     guardrails_factory=None, metadata_provenance=None, region_theme_routing=False):
    """Build a single-question supervisor (no implicit conversation memory).

    Search callables take (state, config) and return a state-update mapping.
    Use adapt_vector/adapt_graph/adapt_hybrid for the team's external interfaces.
    Max 2 retries bounds the graph below LangGraph's default recursion limit.
    RunnableConfig callbacks/tags are forwarded to LLM and injected node calls.
    """
    ctl = SupervisorController(
        hybrid_search=hybrid_search, vector_search=vector_search, graph_search=graph_search,
        route_question=route_question, answer_question=answer_question,
        verify_answer=verify_answer, max_retries=max_retries,
        metadata_provenance=metadata_provenance,
        region_theme_routing=region_theme_routing,
    )

    def timed(node):
        def wrapped(state: SupervisorState, config: RunnableConfig):
            started = perf_counter()
            update = node(state, config)
            trace = list(update.get("trace", []))
            if trace:
                trace[-1] = {**trace[-1], "duration_ms": round((perf_counter() - started) * 1000, 2)}
                update = {**update, "trace": trace}
            return update
        return wrapped

    # The config annotation is intentionally RunnableConfig, so LangGraph injects it.
    def supervisor_node(state: SupervisorState, config: RunnableConfig):
        return ctl.supervisor(state, config)

    def search_node(state: SupervisorState, config: RunnableConfig):
        return ctl.search(state, config)

    def answer_node(state: SupervisorState, config: RunnableConfig):
        return ctl.answer(state, config)

    def verify_node(state: SupervisorState, config: RunnableConfig):
        return ctl.verify(state, config)

    def guard_input(state: SupervisorState):
        try:
            verdict = guardrails_factory().check_input(state["question"])
            if verdict.allowed:
                return {"trace": ctl._trace(state, "guard_input", passed=True)}
            message = verdict.message
        except Exception:
            message = "안전 검사에 실패하여 요청을 처리할 수 없습니다."
        return {"status": "blocked", "answer": message, "verified": False,
                "sources": [], "candidate_answer": "", "cited_evidence_ids": [],
                "trace": ctl._trace(state, "guard_input", passed=False)}

    def guard_output(state: SupervisorState):
        try:
            verdict = guardrails_factory().check_output(state["question"], state["answer"])
            if verdict.allowed:
                return {"trace": ctl._trace(state, "guard_output", passed=True)}
            message = verdict.message
        except Exception:
            message = "안전 검사에 실패하여 답변을 표시할 수 없습니다."
        return {"status": "blocked", "answer": message, "verified": False,
                "sources": [], "candidate_answer": "", "cited_evidence_ids": [],
                "evidence": [], "vector_evidence": [], "graph_evidence": [],
                "failure_reason": "", "verification_reason": "",
                "trace": ctl._trace(state, "guard_output", passed=False)}

    workflow = StateGraph(SupervisorState, input_schema=RequestState)
    workflow.add_node("initialize", ctl.initialize)
    workflow.add_node("supervisor", timed(supervisor_node))
    workflow.add_node("vector_search", timed(search_node))
    workflow.add_node("graph_search", timed(search_node))
    workflow.add_node("hybrid_search", timed(search_node))
    workflow.add_node("answer_agent", timed(answer_node))
    workflow.add_node("verify", timed(verify_node))
    workflow.add_node("supervisor_review", ctl.review)
    workflow.add_node("retry", ctl.retry)
    workflow.add_node("finish", ctl.finish)
    workflow.add_node("abstain", ctl.abstain)
    if guardrails_factory is not None:
        workflow.add_node("guard_input", timed(lambda state, config: guard_input(state)))
        workflow.add_node("guard_output", timed(lambda state, config: guard_output(state)))

    workflow.add_edge(START, "initialize")
    if guardrails_factory is not None:
        workflow.add_edge("initialize", "guard_input")
        workflow.add_conditional_edges("guard_input", lambda state: state["status"], {
            "running": "supervisor", "blocked": END,
        })
    else:
        workflow.add_edge("initialize", "supervisor")
    workflow.add_conditional_edges("supervisor", lambda state: state["route"], {
        "vector": "vector_search", "graph": "graph_search",
        "hybrid": "hybrid_search", "abstain": "abstain",
    })
    for node in ("vector_search", "graph_search", "hybrid_search"):
        workflow.add_edge(node, "answer_agent")
    workflow.add_edge("answer_agent", "verify")
    workflow.add_edge("verify", "supervisor_review")
    workflow.add_conditional_edges("supervisor_review", lambda state: state["next_action"], {
        "finish": "finish", "retry": "retry", "abstain": "abstain",
    })
    workflow.add_edge("retry", "supervisor")
    if guardrails_factory is not None:
        workflow.add_edge("finish", "guard_output")
        workflow.add_edge("abstain", "guard_output")
        workflow.add_edge("guard_output", END)
    else:
        workflow.add_edge("finish", END)
        workflow.add_edge("abstain", END)
    return workflow.compile()
