"""Run with: python -m unittest discover -s src/for_build/build_neo4j -p 'test_*.py'."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graph_db import GraphStore, LoadVerificationError  # noqa: E402
from parsing import ParsedData  # noqa: E402


class CountDriver:
    def __init__(self, values: list[int]) -> None:
        self.values = iter(values)

    def execute_query(self, query, **kwargs):
        return ([{"value": next(self.values)}], None, ["value"])


class MultiHopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = ParsedData(
            museums=[{"museum_id": "M1", "sido": "서울", "region_key": '["서울", "종로구"]'}],
            sources=[{"doc_id": "D1"}],
            spans=[{"span_id": "S1"}],
            evidence=[{"span_id": "S1", "doc_id": "D1"}],
        )

    def test_complete_two_to_four_hop_paths_pass(self) -> None:
        store = GraphStore(CountDriver([1, 1, 1, 1, 1, 0]), "neo4j")
        result = store.verify_multihop(self.data)
        self.assertEqual(result["region_source_three_hop_paths"], 1)
        self.assertEqual(result["span_text_mismatches"], 0)

    def test_missing_provenance_path_fails(self) -> None:
        store = GraphStore(CountDriver([1, 1, 0]), "neo4j")
        with self.assertRaisesRegex(LoadVerificationError, "provenance_two_hop_paths"):
            store.verify_multihop(self.data)


if __name__ == "__main__":
    unittest.main()
