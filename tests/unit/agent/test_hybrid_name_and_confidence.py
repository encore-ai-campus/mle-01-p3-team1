"""Exact-name candidates, low-confidence rerank fallback, and Ragas re-judging (offline)."""

import types
from pathlib import Path

import pandas as pd
import pytest

from src.hybrid.bm25_reranker import SpanDocument
from src.hybrid.bm25_retriever import BM25SpanRetriever
from src.hybrid.config import HybridConfig
from src.hybrid.name_match import MuseumNameIndex
from src.hybrid.service import HybridSearchService


# ---------------------------------------------------------------- name index

def test_named_museum_from_baseline_failure_is_recognized():
    index = MuseumNameIndex.from_csv()
    assert index.match("소수박물관 제2전시실의 주제와 주요 전시물은 무엇인가요?") == [("소수박물관", ["M0301"])]


def test_overlapping_shorter_name_is_not_reported():
    index = MuseumNameIndex({"서대문자연사박물관": ["A"], "박물관수": ["B"], "바움": ["C"]})
    assert index.match("서대문자연사박물관 수유실") == [("서대문자연사박물관", ["A"])]
    assert index.match("바움 커피") == []  # names under 4 characters are ignored


def test_parenthetical_suffix_and_spaces_are_ignored():
    index = MuseumNameIndex({"서대문형무소역사관": ["X1", "X2"]})
    assert index.match("서대문 형무소역사관 관람") == [("서대문형무소역사관", ["X1", "X2"])]


# ---------------------------------------------------------------- service

class FakeVector:
    def __init__(self, hits):
        self.hits = hits

    def prepare(self, query):
        return None

    def search(self, query, *, top_k, prepared_plan=None, candidate_ids=None):
        return {"results": [h for h in self.hits if candidate_ids is None or h["museum_id"] in candidate_ids]}


class ScoreBy:
    """Cross-Encoder stub: score per museum name appearing in the passage."""

    def __init__(self, scores):
        self.scores = scores

    def score(self, query, passages):
        return [next((v for k, v in self.scores.items() if k in p), 0.0) for p in passages]


def hit(mid, name):
    return {"museum_id": mid, "name": name, "document": f"{name} 설명", "metadata": {"name": name}}


def bm25():
    # Z's text does not contain its own name, so only the name index can surface it.
    texts = {"A": "가박물관 고유어A", "B": "나박물관 고유어B", "C": "다박물관 고유어C", "Z": "유교 전래 성학십도"}
    spans = [SpanDocument(m, f"{m}:0", t) for m, t in texts.items()]
    meta = {m: {"name": n, "sido": "경기도"} for m, n in
            (("A", "가박물관"), ("B", "나박물관"), ("C", "다박물관"), ("Z", "소수박물관"))}
    return BM25SpanRetriever(spans, metadata_by_museum=meta, tokenize=str.split)


def config(**kwargs):
    return HybridConfig(vector_top_k=5, bm25_top_k=5, fusion_top_k=5, final_top_k=3, parallel_retrieval=False, **kwargs)


def test_named_museum_missing_from_retrieval_is_injected_and_reranked():
    service = HybridSearchService(
        bm25_retriever=bm25(), vector_retriever=FakeVector([hit("A", "가박물관"), hit("B", "나박물관")]),
        reranker=ScoreBy({"소수박물관": 0.9, "가박물관": 0.3}), config=config(),
        name_index=MuseumNameIndex({"소수박물관": ["Z"]}))
    result = service.search("소수박물관 제2전시실")
    assert result["source_ids"][0] == "Z"
    assert result["search_summary"]["name_match"]["injected"] == ["Z"]


def test_named_museum_outside_ontology_candidates_is_not_injected():
    from src.hybrid.ontology_filter import FilterDecision, StructuredConditions

    class Only:
        def resolve(self, question):
            return FilterDecision("applied", StructuredConditions(amenities=("수유실",)), "t", ["A"], {"A": {}})

    service = HybridSearchService(
        bm25_retriever=bm25(), vector_retriever=FakeVector([hit("A", "가박물관")]),
        reranker=ScoreBy({"가박물관": 0.5}), config=config(), candidate_filter=Only(),
        name_index=MuseumNameIndex({"소수박물관": ["Z"]}))
    assert "Z" not in service.search("소수박물관 수유실 있는 곳")["source_ids"]


def test_low_confidence_rerank_keeps_rrf_order():
    vector = FakeVector([hit("A", "가박물관"), hit("B", "나박물관"), hit("C", "다박물관")])
    reranker = ScoreBy({"다박물관": 0.008, "나박물관": 0.004, "가박물관": 0.001})
    low = HybridSearchService(bm25_retriever=bm25(), vector_retriever=vector, reranker=reranker, config=config())
    result = low.search("질문")
    assert result["source_ids"][:3] == ["A", "B", "C"]
    assert result["search_summary"]["rerank_low_confidence"] is True
    assert result["results"][0]["score_type"] == "rrf_low_confidence_rerank"


def test_confident_rerank_still_decides_order():
    vector = FakeVector([hit("A", "가박물관"), hit("B", "나박물관"), hit("C", "다박물관")])
    confident = HybridSearchService(bm25_retriever=bm25(), vector_retriever=vector,
                                    reranker=ScoreBy({"다박물관": 0.9}), config=config())
    result = confident.search("질문")
    assert result["source_ids"][0] == "C"
    assert result["search_summary"]["rerank_low_confidence"] is False


def test_min_confidence_is_validated():
    with pytest.raises(ValueError):
        HybridConfig(rerank_min_confidence=1.5)
    assert HybridConfig.from_env({"HYBRID_RERANK_MIN_CONFIDENCE": "0"}).rerank_min_confidence == 0.0


# ---------------------------------------------------------------- Ragas re-judging

def test_zero_or_missing_faithfulness_is_rejudged(monkeypatch, tmp_path):
    from src.evaluation.hybrid import ragas_eval

    calls = []

    def fake_evaluate(dataset, metrics, run_config, show_progress):
        calls.append(len(dataset.samples))
        first = len(calls) == 1
        values = [0.0, float("nan"), 0.8] if first else [1.0, 0.6]
        rows = [{"faithfulness": v, "context_recall": 1.0, "context_precision_with_reference": 1.0,
                 "factual_correctness": None} for v in values]
        return types.SimpleNamespace(to_pandas=lambda: pd.DataFrame(rows))

    import ragas

    monkeypatch.setattr(ragas, "evaluate", fake_evaluate)
    monkeypatch.setattr("src.evaluation.langgraph.ragas_eval.build_ragas_metrics", lambda *a, **k: [])
    rows = [{"question_id": q, "answerable": "yes", "user_input": q, "reference": "r",
             "reference_contexts_parsed": ["c"]} for q in ("Q1", "Q2", "Q3")]
    records = {q: {"answer": "답", "evidence": [{"text": "근거"}]} for q in ("Q1", "Q2", "Q3")}
    scores, n = ragas_eval._ragas_results(rows, records, "judge", Path(tmp_path), workers=1)
    assert calls == [3, 2]  # only the 0 and the missing score are re-judged
    assert scores["Q1"]["faithfulness"] == 0.5 and scores["Q1"]["faithfulness_rescored"] is True
    assert scores["Q2"]["faithfulness"] == 0.6
    assert scores["Q3"]["faithfulness"] == 0.8 and "faithfulness_rescored" not in scores["Q3"]
