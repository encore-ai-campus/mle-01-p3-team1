"""CSV provenance must belong to the exact retrieved museum text."""

import csv
import hashlib
import json

from src.agent.supervisor import AnswerDraft, RouteDecision, VerificationResult, build_supervisor
from src.agent.supervisor.adapters import adapt_hybrid_retriever


def _write_csv(path, *, text="Original museum text", spans=None, documents=None):
    documents = documents if documents is not None else [{
        "doc_id": "DOC1", "source_locator": "data/raw/source.csv#row=2",
        "source_url": "https://example.org/original", "match_trust": "AUTO_MATCH_NOT_HUMAN_VERIFIED",
    }]
    spans = spans if spans is not None else [{"start": 0, "end": len(text), "doc_ids": ["DOC1"]}]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["museum_id", "text", "text_sha256", "source_documents_json", "text_spans_json"])
        writer.writeheader()
        writer.writerow({"museum_id": "M1", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "source_documents_json": json.dumps(documents), "text_spans_json": json.dumps(spans)})


class Retriever:
    def __init__(self, text):
        self.text = text

    def retrieve(self, query, top_k):
        return {"results": [{"museum_id": "M1", "document": self.text, "metadata": {"homepage_url": "https://example.org/home"},
                             "retrieved_by": ["vector"]}], "status": "ok", "source_ids": ["M1"],
                "warnings": [], "unsupported_constraints": [], "search_summary": {"stages": []}}


def _graph(retriever, index):
    return build_supervisor(
        hybrid_search=adapt_hybrid_retriever(retriever, provenance_index=index),
        route_question=lambda s, c: RouteDecision("hybrid", "test"),
        answer_question=lambda s, c: AnswerDraft("Museum [E1]", ["E1"]),
        verify_answer=lambda s, c: VerificationResult(True, "supported", []), max_retries=0,
    )


def test_matching_csv_text_supplies_source_and_preserves_review_status(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path)
    result = _graph(Retriever("Original museum text"), CsvProvenanceIndex(path)).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "answered"
    source = result["sources"][0]
    assert source["source_doc_ids"] == ["DOC1"]
    assert source["source_urls"] == ["https://example.org/original"]
    assert source["source_documents"][0]["source_locator"] == "data/raw/source.csv#row=2"
    assert source["source_documents"][0]["match_trust"] == "AUTO_MATCH_NOT_HUMAN_VERIFIED"
    assert source["source_scope"] == "text"


def test_changed_text_does_not_receive_csv_provenance(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path)
    result = _graph(Retriever("Different museum text"), CsvProvenanceIndex(path)).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "abstained"
    assert result["failure_reason"] == "Cited evidence has no source provenance"


def test_incomplete_span_coverage_cannot_claim_whole_text_as_sourced(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path, spans=[{"start": 0, "end": 8, "doc_ids": ["DOC1"]}])
    result = _graph(Retriever("Original museum text"), CsvProvenanceIndex(path)).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "abstained"


def test_homepage_is_not_treated_as_original_source_url(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path, documents=[{"doc_id": "DOC1", "source_locator": "data/raw/source.csv#row=2",
                                "source_url": "", "museum_homepage_url": "https://example.org/home"}])
    result = _graph(Retriever("Original museum text"), CsvProvenanceIndex(path)).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "answered"
    assert result["sources"][0]["source_urls"] == []


def test_duplicate_museum_id_does_not_select_an_ambiguous_source(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    valid = rows[0]
    invalid = {**valid, "text_sha256": "invalid"}
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=valid.keys())
        writer.writeheader()
        writer.writerows([invalid, valid])
    result = _graph(Retriever("Original museum text"), CsvProvenanceIndex(path)).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "abstained"


def test_actual_csv_is_used_by_the_connected_supervisor(monkeypatch):
    import src.agent.supervisor.llm as llm_module
    from src.agent.supervisor.connect import build_connected_supervisor
    from src.agent.supervisor.provenance import DEFAULT_PROVENANCE_CSV

    with DEFAULT_PROVENANCE_CSV.open(encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))

    class LocalNodes:
        def __init__(self, llm):
            pass
        def route(self, state, config):
            return RouteDecision("hybrid", "test")
        def answer(self, state, config):
            return AnswerDraft("Museum [E1]", ["E1"])
        def verify(self, state, config):
            return VerificationResult(True, "supported", [])

    class RealCsvRetriever(Retriever):
        def retrieve(self, query, top_k):
            result = super().retrieve(query, top_k)
            result["results"][0]["museum_id"] = row["museum_id"]
            result["source_ids"] = [row["museum_id"]]
            return result

    monkeypatch.setattr(llm_module, "LLMNodes", LocalNodes)
    graph = build_connected_supervisor(hybrid_retriever=RealCsvRetriever(row["text"]), llm=object(), max_retries=0)
    result = graph.invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "answered"
    assert result["sources"][0]["source_doc_ids"] == [json.loads(row["source_documents_json"])[0]["doc_id"]]
    assert result["sources"][0]["source_locator"]


def test_missing_csv_is_reported_and_does_not_supply_provenance(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    index = CsvProvenanceIndex(tmp_path / "missing.csv")
    result = _graph(Retriever("Original museum text"), index).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "abstained"
    assert result["hybrid_search_diagnostics"]["provenance_csv_status"] == "unavailable"


def test_vector_route_also_receives_csv_provenance(tmp_path):
    from src.agent.supervisor.adapters import adapt_vector
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path)
    graph = build_supervisor(
        hybrid_search=lambda s, c: {"evidence": []},
        vector_search=adapt_vector(Retriever("Original museum text"), provenance_index=CsvProvenanceIndex(path)),
        route_question=lambda s, c: RouteDecision("vector", "test"),
        answer_question=lambda s, c: AnswerDraft("Museum [E1]", ["E1"]),
        verify_answer=lambda s, c: VerificationResult(True, "supported", []), max_retries=0,
    )
    result = graph.invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "answered"
    assert result["sources"][0]["source_doc_ids"] == ["DOC1"]


def test_invalid_url_does_not_break_other_source_metadata(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    _write_csv(path, documents=[{"doc_id": "DOC1", "source_locator": "data/raw/source.csv#row=2",
                                "source_url": "https://[invalid"}])
    result = _graph(Retriever("Original museum text"), CsvProvenanceIndex(path)).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "answered"
    assert result["sources"][0]["source_urls"] == []


def test_csv_without_required_source_columns_is_reported(tmp_path):
    from src.agent.supervisor.provenance import CsvProvenanceIndex

    path = tmp_path / "source.csv"
    path.write_text("museum_id,text\nM1,Original museum text\n", encoding="utf-8")
    index = CsvProvenanceIndex(path)
    result = _graph(Retriever("Original museum text"), index).invoke({"question": "museum", "top_k": 1})
    assert result["status"] == "abstained"
    assert result["hybrid_search_diagnostics"]["provenance_csv_status"] == "unavailable"
