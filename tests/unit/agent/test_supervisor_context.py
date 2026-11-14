import csv
import hashlib
import json

from src.agent.supervisor.nodes import SupervisorController
from src.agent.supervisor.provenance import CsvProvenanceIndex
from src.agent.supervisor.state import AnswerDraft, RouteDecision, VerificationResult


def make_controller(*, graph=True):
    observed = []
    def route(state, config):
        observed.append(state)
        return RouteDecision("hybrid", "test")
    ctl = SupervisorController(
        hybrid_search=lambda s, c: {"evidence": []},
        graph_search=(lambda s, c: {"evidence": []}) if graph else None,
        route_question=route,
        answer_question=lambda s, c: AnswerDraft("", []),
        verify_answer=lambda s, c: VerificationResult(False, "", []),
    )
    return ctl, observed


def test_router_receives_actual_available_backends():
    ctl, observed = make_controller()
    state = ctl.initialize({"question": "전시 추천"})
    ctl.supervisor(state)
    assert set(observed[0]["available_routes"]) == {"hybrid", "graph"}


def test_retry_uses_graph_for_missing_structured_fact():
    ctl, _ = make_controller()
    state = ctl.initialize({"question": "어떤 곳인가요?"})
    state.update(route="hybrid", retry_count=1, missing_aspects=["소재 지역"], feedback="지역 근거 부족")
    result = ctl.supervisor(state)
    assert result["route"] == "graph"


def test_retry_preserves_explicit_hybrid_and_unrelated_context():
    ctl, _ = make_controller()
    state = ctl.initialize({"question": "전시 추천", "route_override": "hybrid"})
    state.update(route="hybrid", retry_count=1, missing_aspects=["주소"], feedback="주소 부족")
    assert ctl.supervisor(state)["route"] == "hybrid"
    state["route_override"] = "auto"
    state["missing_aspects"] = ["전시 내용"]
    state["feedback"] = "전시 내용 부족"
    assert ctl.supervisor(state)["route"] == "hybrid"


def test_retry_recognizes_spaced_hours_without_matching_coffee():
    ctl, _ = make_controller()
    state = ctl.initialize({"question": "문의"})
    state.update(route="hybrid", retry_count=1, missing_aspects=["운영 시간"], feedback="")
    assert ctl.supervisor(state)["route"] == "graph"
    state["missing_aspects"] = ["coffee exhibition"]
    assert ctl.supervisor(state)["route"] == "hybrid"


def test_missing_graph_keeps_hybrid_without_inventing_backend():
    ctl, observed = make_controller(graph=False)
    state = ctl.initialize({"question": "질문"})
    ctl.supervisor(state)
    assert observed[0]["available_routes"] == ["hybrid"]
    state.update(route="hybrid", retry_count=1, missing_aspects=["요금"], feedback="요금 부족")
    assert ctl.supervisor(state)["route"] == "hybrid"


def write_source(path):
    text = "Exhibition description"
    row = {"museum_id": "M1", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
           "source_documents_json": json.dumps([{"doc_id": "D1"}]),
           "text_spans_json": json.dumps([{"start": 0, "end": len(text), "doc_ids": ["D1"]}]),
           "sido": "부산광역시", "address": "부산광역시 중구", "adult_fee": "1000", "base_data_date": "2026-01-01"}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader(); writer.writerow(row)
    return text


def test_matching_metadata_gets_separate_derived_csv_provenance(tmp_path):
    path = tmp_path / "data.csv"
    text = write_source(path)
    item = {"museum_id": "M1", "text": text,
            "metadata": {"sido": "부산광역시", "address": "부산광역시 중구", "adult_fee": 1000}}
    result = CsvProvenanceIndex(path).attach(item)
    assert result["source_scope"] == "text"
    assert result["metadata_provenance"]["fields"] == {"sido": "부산광역시", "address": "부산광역시 중구", "adult_fee": "1000"}
    assert result["metadata_provenance"]["source_locator"].endswith("#record=2")
    assert result["metadata_provenance"]["source_kind"] == "derived_csv_row"


def test_mismatched_and_forged_metadata_never_gain_provenance(tmp_path):
    path = tmp_path / "data.csv"
    text = write_source(path)
    item = {"museum_id": "M1", "text": text, "metadata": {"sido": "서울특별시", "adult_fee": 0},
            "metadata_provenance": {"source_kind": "forged"}}
    result = CsvProvenanceIndex(path).attach(item)
    assert "metadata_provenance" not in result
    item["text"] = "other text"
    assert "metadata_provenance" not in CsvProvenanceIndex(path).attach(item)


def test_verified_csv_record_can_supply_missing_metadata_without_claiming_original_source(tmp_path):
    path = tmp_path / "data.csv"
    text = write_source(path)
    result = CsvProvenanceIndex(path).attach({"museum_id": "M1", "text": text})
    provenance = result["metadata_provenance"]
    assert provenance["fields"]["sido"] == "부산광역시"
    assert provenance["base_data_date"] == "2026-01-01"
    assert provenance["trust"] == "derived_dataset_not_human_verified"


def test_configured_sido_alias_keeps_csv_value_and_records_normalization(tmp_path):
    path = tmp_path / "data.csv"
    text = write_source(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    row["sido"] = "전라북도"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    item = {"museum_id": "M1", "text": text, "metadata": {"sido": "전북특별자치도"}}
    result = CsvProvenanceIndex(path).attach(item)["metadata_provenance"]
    assert result["fields"]["sido"] == "전라북도"
    assert result["normalizations"]["sido"]["matched_value"] == "전북특별자치도"


def test_retriever_cannot_inject_metadata_provenance_into_supervisor():
    seen = []
    ctl = SupervisorController(
        hybrid_search=lambda s, c: {"evidence": [{"museum_id": "M1", "text": "x",
            "source_doc_ids": ["D1"], "metadata_provenance": {"source_kind": "derived_csv_row", "fields": {"sido": "fake"}},
            "metadata": {"metadata_provenance": {"source_kind": "fake"}}}]},
        route_question=lambda s, c: RouteDecision("hybrid", ""),
        answer_question=lambda s, c: seen.append(s["evidence"]) or AnswerDraft("x [E1]", ["E1"]),
        verify_answer=lambda s, c: VerificationResult(True, "", []),
    )
    state = ctl.initialize({"question": "질문"})
    state.update(ctl.supervisor(state)); state.update(ctl.search(state)); ctl.answer(state)
    assert "metadata_provenance" not in seen[0][0]
    assert "metadata_provenance" not in seen[0][0]["metadata"]


def test_supervisor_attaches_only_trusted_csv_metadata(tmp_path):
    path = tmp_path / "data.csv"
    text = write_source(path)
    index = CsvProvenanceIndex(path)
    ctl = SupervisorController(
        hybrid_search=lambda s, c: {"evidence": [{"museum_id": "M1", "text": text, "source_doc_ids": ["D1"]}]},
        route_question=lambda s, c: RouteDecision("hybrid", ""),
        answer_question=lambda s, c: AnswerDraft("", []),
        verify_answer=lambda s, c: VerificationResult(False, "", []),
        metadata_provenance=index.attach,
    )
    state = ctl.initialize({"question": "질문"})
    state.update(ctl.supervisor(state)); state.update(ctl.search(state))
    assert state["evidence"][0]["metadata_provenance"]["fields"]["sido"] == "부산광역시"
