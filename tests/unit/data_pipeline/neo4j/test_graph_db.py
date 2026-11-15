"""Read-back checks for the database boundary; run with unittest discover."""

import unittest

from src.data_pipeline.neo4j.graph_db import GraphStore, LoadVerificationError
from src.data_pipeline.neo4j.parsing import ParsedData


class CountDriver:
    def __init__(self, counts: list[int]) -> None:
        self.counts = iter(counts)

    def execute_query(self, query, **kwargs):
        return ([{"value": next(self.counts)}], None, ["value"])


class GraphVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = ParsedData(
            museums=[{"museum_id": "M1", "sido": "서울", "region_key": '["서울", "종로구"]'}],
            sources=[{"doc_id": "D1"}],
            spans=[{"span_id": "S1"}],
            evidence=[{"span_id": "S1", "doc_id": "D1"}],
        )

    def test_read_back_count_mismatch_fails_the_load(self) -> None:
        store = GraphStore(CountDriver([1, 1, 0, 1, 1, 1]), "neo4j")
        with self.assertRaisesRegex(LoadVerificationError, "spans"):
            store.verify(self.data)

    def test_matching_read_back_counts_are_returned(self) -> None:
        store = GraphStore(CountDriver([1] * 10), "neo4j")
        self.assertEqual(store.verify(self.data)["evidence"], 1)

    def test_region_links_are_included_in_read_back(self) -> None:
        store = GraphStore(CountDriver([1] * 10), "neo4j")
        self.assertEqual(store.verify(self.data)["location_links"], 1)


if __name__ == "__main__":
    unittest.main()
