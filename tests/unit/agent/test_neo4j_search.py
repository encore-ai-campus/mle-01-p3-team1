import unittest

from neo4j import RoutingControl

from src.agent.neo4j_search import Neo4jSpanSearch, extract_search_terms


class FakeDriver:
    def __init__(self):
        self.query = None
        self.parameters = None
        self.database = None
        self.routing = None

    def execute_query(self, query, *, parameters_, database_, routing_):
        self.query = query
        self.parameters = parameters_
        self.database = database_
        self.routing = routing_
        return ([{
            "museum_id": "M1",
            "name": "전통문화박물관",
            "text": "전통문화 유물을 전시합니다.",
            "span_id": "M1:000",
            "source_doc_ids": ["D1"],
            "source_urls": ["https://example.org/source"],
            "sido": "서울특별시",
            "sigungu": "종로구",
            "matched_terms": ["전통문화"],
        }], None, [])


class Neo4jSpanSearchTests(unittest.TestCase):
    def test_extracts_meaningful_korean_terms_and_removes_particles(self):
        self.assertEqual(
            extract_search_terms("서울에서 전통문화 관련 박물관 추천해줘"),
            ["서울", "전통문화"],
        )

    def test_search_uses_read_routing_and_maps_graph_provenance(self):
        driver = FakeDriver()
        search = Neo4jSpanSearch(driver, "museum-db")

        results = search.search("서울 전통문화", 3)

        self.assertEqual(driver.parameters, {"terms": ["서울", "전통문화"], "k": 3})
        self.assertEqual(driver.database, "museum-db")
        self.assertEqual(driver.routing, RoutingControl.READ)
        self.assertNotIn("서울", driver.query)
        self.assertEqual(results[0]["museum_id"], "M1")
        self.assertEqual(results[0]["source_doc_ids"], ["D1"])
        self.assertEqual(results[0]["source_urls"], ["https://example.org/source"])
        self.assertEqual(results[0]["retriever"], "graph")

    def test_rejects_invalid_k_and_questions_without_search_terms(self):
        search = Neo4jSpanSearch(FakeDriver(), "museum-db")

        for k in (0, True, 1.5):
            with self.subTest(k=k):
                with self.assertRaises(ValueError):
                    search.search("서울", k)

        with self.assertRaises(ValueError):
            search.search("박물관 추천", 3)


if __name__ == "__main__":
    unittest.main()
