"""Connect Supervisor orchestration to the team's actual retrieval services."""
from __future__ import annotations

import os

from . import adapt_graph, adapt_hybrid, adapt_hybrid_retriever, adapt_vector, build_supervisor


def build_connected_supervisor(*, hybrid_node=None, hybrid_retriever=None, vector_retriever=None,
                               graph_retriever=None, llm=None,
                               model_name: str | None = None,
                               hybrid_accepts_config: bool = False,
                               provenance_csv=None,
                               guardrails_factory=None,
                               max_retries: int = 1,
                               region_theme_routing: bool | None = None):
    """Connect actual team services; retrieve/search constructor details stay external.

    By default, connect src.hybrid.HybridRAGAgent lazily. Alternatively inject
    hybrid_retriever.retrieve(query, top_k), or hybrid_node(state) -> dict.
    vector_retriever: optional existing VectorSearchRetriever instance.
    graph_retriever: optional existing Neo4jText2Cypher instance.
    llm: optional configured ChatOpenAI-compatible model (e.g. team default).
    With only hybrid connected, vector/graph selections fall back to hybrid
    explicitly. Hybrid is BM25 + vector; it does not perform Neo4j traversal.
    The original CSV provides source records only for exactly matching text.
    """
    from .provenance import CsvProvenanceIndex, DEFAULT_PROVENANCE_CSV
    provenance = CsvProvenanceIndex(provenance_csv if provenance_csv is not None else DEFAULT_PROVENANCE_CSV)
    if hybrid_node is not None and hybrid_retriever is not None:
        raise ValueError("Pass only one of hybrid_node or hybrid_retriever")
    # Deterministic routes (region+theme, ontology-filter conditions) assume the
    # default HybridRAGAgent. Callers that replay its results (evaluation) may
    # opt in explicitly.
    routing_override = region_theme_routing
    region_theme_routing = False
    if hybrid_node is None:
        from src.hybrid.hybrid_rag_agent import HybridRAGAgent
        if hybrid_accepts_config:
            raise ValueError("hybrid_accepts_config applies only to hybrid_node")
        if hybrid_retriever is None:
            hybrid_retriever = HybridRAGAgent()
        region_theme_routing = (isinstance(HybridRAGAgent, type)
                                and isinstance(hybrid_retriever, HybridRAGAgent)
                                and hybrid_retriever._search_service is None)
        hybrid_search = adapt_hybrid_retriever(hybrid_retriever, provenance_index=provenance)
    else:
        hybrid_search = adapt_hybrid(hybrid_node, accepts_config=hybrid_accepts_config)
    if routing_override is not None:
        region_theme_routing = routing_override
    from .llm import LLMNodes
    if llm is None:
        model_name = model_name or os.getenv("SUPERVISOR_MODEL")
        if not model_name:
            raise ValueError("Pass llm/model_name or set SUPERVISOR_MODEL to your team's model")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=model_name, timeout=60, max_retries=1)
    nodes = LLMNodes(llm)
    if guardrails_factory is None:
        def guardrails_factory():
            from src.guardrails import get_guardrails
            return get_guardrails()
    return build_supervisor(
        hybrid_search=hybrid_search,
        vector_search=adapt_vector(vector_retriever, provenance_index=provenance) if vector_retriever is not None else None,
        graph_search=adapt_graph(graph_retriever) if graph_retriever is not None else None,
        route_question=nodes.route, answer_question=nodes.answer,
        verify_answer=nodes.verify, max_retries=max_retries,
        metadata_provenance=provenance.attach,
        region_theme_routing=region_theme_routing,
        guardrails_factory=guardrails_factory,
    )
