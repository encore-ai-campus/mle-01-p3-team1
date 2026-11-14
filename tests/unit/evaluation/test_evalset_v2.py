"""v2 evaluation set: deterministic gold, intended code paths, compatibility with the runner."""

import csv
import os
from unittest import mock

import pytest

from src.agent.neo4j_text2cypher import _organization_relation
from src.evaluation import build_evalset_v2 as builder
from src.evaluation.hybrid import ragas_eval
from src.hybrid.ontology_filter import LocalOntologyIndex, extract_conditions


@pytest.fixture(scope="module")
def items():
    return builder.build()


def test_build_is_deterministic_and_matches_committed_file(items):
    assert builder.build() == items
    with builder.OUT_PATH.open(encoding="utf-8-sig", newline="") as file:
        on_disk = list(csv.DictReader(file))
    assert [row["question_id"] for row in on_disk] == [item["question_id"] for item in items]
    assert [row["user_input"] for row in on_disk] == [item["user_input"] for item in items]


def test_v1_questions_are_carried_over_unchanged(items):
    with builder.V1_PATH.open(encoding="utf-8-sig", newline="") as file:
        v1 = list(csv.DictReader(file))
    carried = [item for item in items if item["source_set"] == "v1_2026-11-13"]
    assert [(r["question_id"], r["user_input"], r["reference"]) for r in v1] == \
        [(r["question_id"], r["user_input"], r["reference"]) for r in carried]


def test_question_ids_are_unique(items):
    ids = [item["question_id"] for item in items]
    assert len(ids) == len(set(ids))


def test_structured_questions_trigger_the_filter_with_matching_gold(items):
    index = LocalOntologyIndex.from_csv()
    structured = [i for i in items if i["category"].startswith("structured")]
    assert len(structured) >= 15
    for item in structured:
        conditions = extract_conditions(item["user_input"])
        assert conditions.has_hard_conditions, item["user_input"]
        gold = sorted(filter(None, item["gold_museum_ids"].split(";")))
        assert sorted(index.candidates(conditions)) == gold, item["question_id"]
        assert (item["answerable"] == "no") == (not gold)


def test_organization_questions_use_the_graph_template(items):
    org = [i for i in items if i["category"].startswith("org_")]
    assert org
    for item in org:
        expected = "OPERATED_BY" if item["category"] == "org_same_operator" else "MANAGED_BY"
        assert _organization_relation(item["user_input"]) == expected
        assert item["gold_museum_ids"]


def test_runner_reads_v2_and_knows_the_full_flow_mode():
    rows = ragas_eval.read_evalset(builder.OUT_PATH, 0)
    assert len(rows) >= 190
    assert ragas_eval.parse_modes("supervisor_full") == ["supervisor_full"]
    with mock.patch.dict(os.environ, {}, clear=True):
        missing = ragas_eval._required_env(["supervisor_full"], True, "")
    assert {"SUPERVISOR_MODEL", "NEO4J_URI"}.issubset(missing)
