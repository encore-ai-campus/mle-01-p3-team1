"""Identity and complete text are retained in the v2 shared JSON context."""
import json
import pytest
from src.evaluation.hybrid.ragas_eval import ragas_context

@pytest.mark.parametrize("retriever", ["graph", "hybrid", "vector"])
def test_name_is_retained_for_all_routes(retriever):
    row = {"retriever": retriever, "museum_id": "M1", "name": "Museum", "text": "Text without its name"}
    data = json.loads(ragas_context(row))
    assert data["name"] == "Museum"
    assert data["museum_id"] == "M1"
    assert data["text"] == row["text"]

def test_metadata_name_and_unnamed_passage():
    assert json.loads(ragas_context({"metadata": {"name": "Museum"}, "text": "Body"}))["name"] == "Museum"
    assert json.loads(ragas_context({"text": "Body"}))["text"] == "Body"

def test_graph_anchor_and_zero_fee_survive():
    data = json.loads(ragas_context({"retriever": "graph", "evidence_role": "anchor", "adult_fee": 0, "text": "Record"}))
    assert data["evidence_role"] == "anchor"
    assert data["adult_fee"] == 0
