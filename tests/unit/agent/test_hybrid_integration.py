"""Regression tests for the team hybrid/Supervisor boundary."""

from types import SimpleNamespace

from src.agent.supervisor import AnswerDraft, RouteDecision, VerificationResult, build_supervisor
from src.hybrid.config import HybridConfig
from src.hybrid.hybrid_rag_agent import HybridRAGAgent
from src.hybrid.service import HybridSearchService


def test_legacy_and_hybrid_bm25_use_the_same_document_type():
    from src.agent.bm25_reranker import BM25Reranker, SpanDocument
    from src.hybrid.bm25_reranker import BM25Reranker as HybridBM25

    index = HybridBM25([SpanDocument("M1", "S1", "museum")], tokenize=str.split)
    assert BM25Reranker is HybridBM25
    assert index.rerank("museum", ["M1"], top_k=1)[0].museum_id == "M1"


def test_default_vector_adapter_uses_current_service_module(monkeypatch):
    import src.service.vector_search_service as vector_module
    from src.hybrid.adapters import ExistingVectorRetriever

    class LocalService:
        def analyze_query(self, query):
            return {"query": query}

    monkeypatch.setattr(vector_module, "VectorSearchService", LocalService)
    assert ExistingVectorRetriever().prepare("museum") == {"query": "museum"}


def _team_retriever(*, partial=False, provenance=True):
    metadata = {"name": "Museum", "source_doc_ids": ["DOC1"]} if provenance else {"name": "Museum"}

    class Vector:
        def prepare(self, query):
            return SimpleNamespace(filters={}, unsupported_constraints=[])

        def search(self, query, *, top_k, prepared_plan):
            if partial:
                raise RuntimeError("vector unavailable")
            return {"results": [{"museum_id": "M1", "document": "museum history", "metadata": metadata}], "warnings": []}

    class BM25:
        def search(self, query, *, top_k, filters):
            return [{"museum_id": "M1", "document": "museum history", "metadata": metadata,
                     "score": 2.0, "best_span_id": "S1", "best_span_text": "museum history"}]

    class Reranker:
        def score(self, query, passages):
            return [0.9 for _ in passages]

    cfg = HybridConfig(retriever_failure_policy="partial", parallel_retrieval=False)
    return HybridRAGAgent(HybridSearchService(bm25_retriever=BM25(), vector_retriever=Vector(),
                                               reranker=Reranker(), config=cfg))


def test_team_hybrid_pipeline_connects_to_supervisor_with_diagnostics():
    from src.agent.supervisor.adapters import adapt_hybrid_retriever

    search = adapt_hybrid_retriever(_team_retriever(partial=True))
    graph = build_supervisor(
        hybrid_search=search,
        route_question=lambda state, config: RouteDecision("hybrid", "hybrid"),
        answer_question=lambda state, config: AnswerDraft("History [E1]", ["E1"]),
        verify_answer=lambda state, config: VerificationResult(True, "supported", []),
        max_retries=0,
    )
    result = graph.invoke({"question": "museum history", "top_k": 1})
    assert result["status"] == "answered"
    assert result["sources"][0]["source_doc_ids"] == ["DOC1"]
    assert result["sources"][0]["retrievers"] == ["bm25"]
    assert result["vector_search_status"] == "error"
    assert result["hybrid_search_diagnostics"]["search_summary"]["retriever_errors"] == ["vector"]
    assert result["hybrid_search_diagnostics"]["warnings"]


def test_hybrid_does_not_invent_source_provenance():
    from src.agent.supervisor.adapters import adapt_hybrid_retriever

    graph = build_supervisor(
        hybrid_search=adapt_hybrid_retriever(_team_retriever(provenance=False)),
        route_question=lambda state, config: RouteDecision("hybrid", "hybrid"),
        answer_question=lambda state, config: AnswerDraft("History [E1]", ["E1"]),
        verify_answer=lambda state, config: VerificationResult(True, "supported", []),
        max_retries=0,
    )
    result = graph.invoke({"question": "museum history", "top_k": 1})
    assert result["status"] == "abstained"
    assert result["failure_reason"] == "Cited evidence has no source provenance"


def test_hybrid_does_not_attach_bm25_source_to_different_vector_text():
    from src.agent.supervisor.adapters import adapt_hybrid_retriever, normalize_result

    class Vector:
        def search(self, query, *, top_k, prepared_plan):
            return [{"museum_id": "M1", "document": "vector passage", "metadata": {}}]

    class BM25:
        def search(self, query, *, top_k, filters):
            return [{"museum_id": "M1", "document": "different bm25 passage", "score": 2,
                     "metadata": {"source_doc_ids": ["BM25_DOC"]}, "best_span_id": "S1",
                     "best_span_text": "different bm25 passage"}]

    service = HybridSearchService(bm25_retriever=BM25(), vector_retriever=Vector(),
                                  config=HybridConfig(parallel_retrieval=False))
    class Unranked:
        def retrieve(self, query, top_k):
            return service.search(query, top_k=top_k, rerank=False)

    raw = adapt_hybrid_retriever(Unranked())({"question": "museum", "top_k": 1})
    evidence = normalize_result("hybrid", raw, 1)["evidence"][0]
    assert evidence["text"] == "vector passage"
    assert evidence["source_doc_ids"] == []
    assert evidence["span_id"] == ""


def test_bm25_text_does_not_inherit_provenance_from_empty_vector_text():
    from src.agent.supervisor.adapters import adapt_hybrid_retriever, normalize_result

    class Vector:
        def search(self, query, *, top_k, prepared_plan):
            return [{"museum_id": "M1", "document": "", "metadata": {"source_doc_ids": ["VECTOR_DOC"]}}]

    class BM25:
        def search(self, query, *, top_k, filters):
            return [{"museum_id": "M1", "document": "bm25 passage", "score": 2,
                     "metadata": {"source_doc_ids": ["BM25_DOC"]}, "best_span_id": "S1",
                     "best_span_text": "bm25 passage"}]

    service = HybridSearchService(bm25_retriever=BM25(), vector_retriever=Vector(),
                                  config=HybridConfig(parallel_retrieval=False))
    class Unranked:
        def retrieve(self, query, top_k):
            return service.search(query, top_k=top_k, rerank=False)

    raw = adapt_hybrid_retriever(Unranked())({"question": "museum", "top_k": 1})
    evidence = normalize_result("hybrid", raw, 1)["evidence"][0]
    assert evidence["text"] == "bm25 passage"
    assert evidence["source_doc_ids"] == ["BM25_DOC"]


def test_connected_supervisor_uses_the_team_retriever_by_default(monkeypatch):
    import src.agent.supervisor.llm as llm_module
    import src.hybrid.hybrid_rag_agent as hybrid_module
    from src.agent.supervisor.connect import build_connected_supervisor

    class LocalNodes:
        def __init__(self, llm):
            pass

        def route(self, state, config):
            return RouteDecision("hybrid", "hybrid")

        def answer(self, state, config):
            return AnswerDraft("History [E1]", ["E1"])

        def verify(self, state, config):
            return VerificationResult(True, "supported", [])

    monkeypatch.setattr(llm_module, "LLMNodes", LocalNodes)
    monkeypatch.setattr(hybrid_module, "HybridRAGAgent", _team_retriever)
    graph = build_connected_supervisor(llm=object(), max_retries=0)
    assert graph.invoke({"question": "museum history", "top_k": 1})["status"] == "answered"


def test_connected_supervisor_rejects_ambiguous_hybrid_inputs():
    import pytest
    from src.agent.supervisor.connect import build_connected_supervisor

    with pytest.raises(ValueError, match="hybrid_node.*hybrid_retriever"):
        build_connected_supervisor(hybrid_node=lambda state: {}, hybrid_retriever=_team_retriever(), llm=object())


def test_real_bm25_and_fusion_feed_reranked_evidence_to_supervisor():
    from src.agent.supervisor.adapters import adapt_hybrid_retriever
    from src.hybrid.bm25_retriever import BM25SpanRetriever
    from src.hybrid.bm25_reranker import SpanDocument

    corpus = [SpanDocument("M1", "S1", "history museum"),
              SpanDocument("M2", "S2", "art sculpture"),
              SpanDocument("M3", "S3", "science planet")]
    bm25 = BM25SpanRetriever(corpus, tokenize=str.split,
                             metadata_by_museum={"M1": {"source_doc_ids": ["DOC1"]}})

    class Vector:
        def search(self, query, *, top_k, prepared_plan):
            return [{"museum_id": "M2", "document": "art sculpture", "metadata": {}}]

    class Reranker:
        def score(self, query, passages):
            return [0.9 if "history" in text else 0.1 for text in passages]

    service = HybridSearchService(bm25_retriever=bm25, vector_retriever=Vector(), reranker=Reranker(),
                                  config=HybridConfig(parallel_retrieval=False))
    graph = build_supervisor(
        hybrid_search=adapt_hybrid_retriever(HybridRAGAgent(service)),
        route_question=lambda state, config: RouteDecision("hybrid", "hybrid"),
        answer_question=lambda state, config: AnswerDraft("History [E1]", ["E1"]),
        verify_answer=lambda state, config: VerificationResult(True, "supported", []),
        max_retries=0,
    )
    result = graph.invoke({"question": "history", "top_k": 2})
    assert result["status"] == "answered"
    assert result["sources"][0]["museum_id"] == "M1"
    assert result["sources"][0]["source_doc_ids"] == ["DOC1"]
    assert result["hybrid_search_diagnostics"]["search_summary"]["rerank_applied"] is True
