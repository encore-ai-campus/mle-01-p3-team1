"""Real LangGraph assembly. Does not reimplement teammate retrieval."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from .nodes import SupervisorController
from .state import RequestState, SupervisorState


def build_supervisor(*, hybrid_search, route_question, answer_question, verify_answer,
                     vector_search=None, graph_search=None, max_retries: int = 1):
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
    )

    # The config annotation is intentionally RunnableConfig, so LangGraph injects it.
    def supervisor_node(state: SupervisorState, config: RunnableConfig):
        return ctl.supervisor(state, config)

    def search_node(state: SupervisorState, config: RunnableConfig):
        return ctl.search(state, config)

    def answer_node(state: SupervisorState, config: RunnableConfig):
        return ctl.answer(state, config)

    def verify_node(state: SupervisorState, config: RunnableConfig):
        return ctl.verify(state, config)

    workflow = StateGraph(SupervisorState, input_schema=RequestState)
    workflow.add_node("initialize", ctl.initialize)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("vector_search", search_node)
    workflow.add_node("graph_search", search_node)
    workflow.add_node("hybrid_search", search_node)
    workflow.add_node("answer_agent", answer_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("supervisor_review", ctl.review)
    workflow.add_node("retry", ctl.retry)
    workflow.add_node("finish", ctl.finish)
    workflow.add_node("abstain", ctl.abstain)

    workflow.add_edge(START, "initialize")
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
    workflow.add_edge("finish", END)
    workflow.add_edge("abstain", END)
    return workflow.compile()
