"""The single integration point for the team. No invented Hybrid module import."""
from __future__ import annotations

import os

from . import adapt_graph, adapt_hybrid, adapt_vector, build_supervisor


def build_connected_supervisor(*, hybrid_node, vector_retriever=None,
                               graph_retriever=None, llm=None,
                               model_name: str | None = None,
                               hybrid_accepts_config: bool = False,
                               max_retries: int = 1):
    """Connect actual team services; retrieve/search constructor details stay external.

    hybrid_node: teammate's function(state) -> dict, or compiled_hybrid.invoke.
    vector_retriever: optional existing VectorSearchRetriever instance.
    graph_retriever: optional existing Neo4jText2Cypher instance.
    llm: optional configured ChatOpenAI-compatible model (e.g. team default).
    With only hybrid_node connected, vector/graph selections fall back to hybrid
    explicitly; do not report three independent backends as implemented.
    """
    from .llm import LLMNodes
    if llm is None:
        model_name = model_name or os.getenv("SUPERVISOR_MODEL")
        if not model_name:
            raise ValueError("Pass llm/model_name or set SUPERVISOR_MODEL to your team's model")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=model_name, temperature=0, timeout=60, max_retries=1)
    nodes = LLMNodes(llm)
    return build_supervisor(
        hybrid_search=adapt_hybrid(hybrid_node, accepts_config=hybrid_accepts_config),
        vector_search=adapt_vector(vector_retriever) if vector_retriever is not None else None,
        graph_search=adapt_graph(graph_retriever) if graph_retriever is not None else None,
        route_question=nodes.route, answer_question=nodes.answer,
        verify_answer=nodes.verify, max_retries=max_retries,
    )
