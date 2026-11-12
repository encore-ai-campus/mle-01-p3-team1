"""Parameterized Cypher and Neo4j operations for the museum import.

The Neo4j driver is supplied by load_neo4j.py. Run: python load_neo4j.py
"""

from __future__ import annotations

from parsing import ParsedData


class LoadVerificationError(RuntimeError):
    """Neo4j read-back counts do not match the CSV payloads."""


CONSTRAINTS = (
    "CREATE CONSTRAINT museum_id_unique IF NOT EXISTS FOR (m:Museum) REQUIRE m.museum_id IS UNIQUE",
    "CREATE CONSTRAINT source_doc_id_unique IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.doc_id IS UNIQUE",
    "CREATE CONSTRAINT span_id_unique IF NOT EXISTS FOR (s:TextSpan) REQUIRE s.span_id IS UNIQUE",
    "CREATE CONSTRAINT sido_name_unique IF NOT EXISTS FOR (s:Sido) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT sigungu_key_unique IF NOT EXISTS FOR (s:Sigungu) REQUIRE s.region_key IS UNIQUE",
)

UPSERT_MUSEUMS = """
UNWIND $rows AS row
MERGE (m:Museum {museum_id: row.museum_id})
SET m += row.properties
MERGE (s:Sido {name: row.sido})
MERGE (g:Sigungu {region_key: row.region_key})
SET g.name = row.sigungu, g.sido = row.sido
MERGE (m)-[:LOCATED_IN]->(g)
MERGE (g)-[:PART_OF]->(s)
"""

UPSERT_SOURCES = """
UNWIND $rows AS row
MATCH (m:Museum {museum_id: row.museum_id})
MERGE (d:SourceDocument {doc_id: row.doc_id})
SET d += row.properties
MERGE (m)-[:HAS_SOURCE]->(d)
"""

UPSERT_SPANS = """
UNWIND $rows AS row
MATCH (m:Museum {museum_id: row.museum_id})
MERGE (s:TextSpan {span_id: row.span_id})
SET s += row.properties
MERGE (m)-[:HAS_SPAN]->(s)
"""

UPSERT_EVIDENCE = """
UNWIND $rows AS row
MATCH (s:TextSpan {span_id: row.span_id})
MATCH (d:SourceDocument {doc_id: row.doc_id})
MERGE (s)-[:SUPPORTED_BY]->(d)
"""

COUNT_QUERIES = {
    "museums": "MATCH (m:Museum) WHERE m.museum_id IN $museum_ids RETURN count(m) AS value",
    "sources": "MATCH (d:SourceDocument) WHERE d.doc_id IN $doc_ids RETURN count(d) AS value",
    "spans": "MATCH (s:TextSpan) WHERE s.span_id IN $span_ids RETURN count(s) AS value",
    "source_links": "MATCH (m:Museum)-[:HAS_SOURCE]->(d:SourceDocument) WHERE m.museum_id IN $museum_ids AND d.doc_id IN $doc_ids RETURN count(*) AS value",
    "span_links": "MATCH (m:Museum)-[:HAS_SPAN]->(s:TextSpan) WHERE m.museum_id IN $museum_ids AND s.span_id IN $span_ids RETURN count(*) AS value",
    "evidence": "MATCH (s:TextSpan)-[:SUPPORTED_BY]->(d:SourceDocument) WHERE s.span_id IN $span_ids AND d.doc_id IN $doc_ids RETURN count(*) AS value",
    "sidos": "MATCH (s:Sido) WHERE s.name IN $sido_names RETURN count(s) AS value",
    "sigungu": "MATCH (g:Sigungu) WHERE g.region_key IN $region_keys RETURN count(g) AS value",
    "location_links": "MATCH (m:Museum)-[:LOCATED_IN]->(g:Sigungu) WHERE m.museum_id IN $museum_ids AND g.region_key IN $region_keys RETURN count(*) AS value",
    "part_of_links": "MATCH (g:Sigungu)-[:PART_OF]->(s:Sido) WHERE g.region_key IN $region_keys AND s.name IN $sido_names RETURN count(*) AS value",
}

MULTIHOP_QUERIES = {
    "region_two_hop_paths": """
        MATCH (m:Museum)-[:LOCATED_IN]->(g:Sigungu)-[:PART_OF]->(s:Sido)
        WHERE m.museum_id IN $museum_ids AND g.region_key IN $region_keys
          AND g.name = m.sigungu AND s.name = m.sido
        RETURN count(*) AS value
    """,
    "region_two_hop_unique_museums": """
        MATCH (m:Museum)-[:LOCATED_IN]->(g:Sigungu)-[:PART_OF]->(s:Sido)
        WHERE m.museum_id IN $museum_ids AND g.region_key IN $region_keys
          AND g.name = m.sigungu AND s.name = m.sido
        RETURN count(DISTINCT m) AS value
    """,
    "provenance_two_hop_paths": """
        MATCH (m:Museum)-[:HAS_SPAN]->(sp:TextSpan)-[:SUPPORTED_BY]->(d:SourceDocument)
        MATCH (m)-[:HAS_SOURCE]->(d)
        WHERE m.museum_id IN $museum_ids AND sp.span_id IN $span_ids AND d.doc_id IN $doc_ids
        RETURN count(*) AS value
    """,
    "region_source_three_hop_paths": """
        MATCH (s:Sido)<-[:PART_OF]-(g:Sigungu)<-[:LOCATED_IN]-(m:Museum)-[:HAS_SOURCE]->(d:SourceDocument)
        WHERE m.museum_id IN $museum_ids AND d.doc_id IN $doc_ids
          AND g.name = m.sigungu AND s.name = m.sido
        RETURN count(*) AS value
    """,
    "region_provenance_four_hop_paths": """
        MATCH (s:Sido)<-[:PART_OF]-(g:Sigungu)<-[:LOCATED_IN]-(m:Museum)-[:HAS_SPAN]->(sp:TextSpan)-[:SUPPORTED_BY]->(d:SourceDocument)
        MATCH (m)-[:HAS_SOURCE]->(d)
        WHERE m.museum_id IN $museum_ids AND sp.span_id IN $span_ids AND d.doc_id IN $doc_ids
          AND g.name = m.sigungu AND s.name = m.sido
        RETURN count(*) AS value
    """,
    "span_text_mismatches": """
        MATCH (m:Museum)-[:HAS_SPAN]->(sp:TextSpan)
        WHERE m.museum_id IN $museum_ids AND sp.span_id IN $span_ids
          AND (m.text IS NULL OR sp.text IS NULL OR sp.start IS NULL OR sp.end IS NULL
               OR substring(m.text, sp.start, sp.end - sp.start) <> sp.text)
        RETURN count(*) AS value
    """,
}


class GraphStore:
    def __init__(self, driver, database: str) -> None:
        self.driver = driver
        self.database = database

    def create_schema(self) -> None:
        for query in CONSTRAINTS:
            self.driver.execute_query(query, database_=self.database)

    @staticmethod
    def _write_batch(tx, museums: list[dict], sources: list[dict], spans: list[dict], evidence: list[dict]) -> None:
        for query, rows in (
            (UPSERT_MUSEUMS, museums),
            (UPSERT_SOURCES, sources),
            (UPSERT_SPANS, spans),
            (UPSERT_EVIDENCE, evidence),
        ):
            if rows:
                tx.run(query, rows=rows).consume()

    def load(self, data: ParsedData, batch_size: int = 50) -> int:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        source_by_museum: dict[str, list[dict]] = {}
        span_by_museum: dict[str, list[dict]] = {}
        evidence_by_span: dict[str, list[dict]] = {}
        for source in data.sources:
            source_by_museum.setdefault(source["museum_id"], []).append(source)
        for span in data.spans:
            span_by_museum.setdefault(span["museum_id"], []).append(span)
        for item in data.evidence:
            evidence_by_span.setdefault(item["span_id"], []).append(item)

        batches = 0
        with self.driver.session(database=self.database) as session:
            for offset in range(0, len(data.museums), batch_size):
                museums = data.museums[offset:offset + batch_size]
                sources = [source for museum in museums for source in source_by_museum.get(museum["museum_id"], [])]
                spans = [span for museum in museums for span in span_by_museum.get(museum["museum_id"], [])]
                evidence = [item for span in spans for item in evidence_by_span.get(span["span_id"], [])]
                session.execute_write(self._write_batch, museums, sources, spans, evidence)
                batches += 1
        return batches

    def verify(self, data: ParsedData) -> dict[str, int]:
        parameters = {
            "museum_ids": [item["museum_id"] for item in data.museums],
            "doc_ids": [item["doc_id"] for item in data.sources],
            "span_ids": [item["span_id"] for item in data.spans],
            "sido_names": list({item["sido"] for item in data.museums}),
            "region_keys": list({item["region_key"] for item in data.museums}),
        }
        expected = {
            "museums": len(data.museums),
            "sources": len(data.sources),
            "spans": len(data.spans),
            "source_links": len(data.sources),
            "span_links": len(data.spans),
            "evidence": len(data.evidence),
            "sidos": len(parameters["sido_names"]),
            "sigungu": len(parameters["region_keys"]),
            "location_links": len(data.museums),
            "part_of_links": len(parameters["region_keys"]),
        }
        actual = {}
        for name, query in COUNT_QUERIES.items():
            records, _, _ = self.driver.execute_query(
                query, parameters_=parameters, database_=self.database, routing_="r"
            )
            actual[name] = int(records[0]["value"])
            if actual[name] != expected[name]:
                raise LoadVerificationError(
                    f"{name}: expected {expected[name]}, read back {actual[name]}"
                )
        return actual

    def verify_multihop(self, data: ParsedData) -> dict[str, int]:
        """Read back complete two- to four-hop paths for the imported ID set."""
        parameters = {
            "museum_ids": [item["museum_id"] for item in data.museums],
            "doc_ids": [item["doc_id"] for item in data.sources],
            "span_ids": [item["span_id"] for item in data.spans],
            "region_keys": list({item["region_key"] for item in data.museums}),
        }
        expected = {
            "region_two_hop_paths": len(data.museums),
            "region_two_hop_unique_museums": len(data.museums),
            "provenance_two_hop_paths": len(data.evidence),
            "region_source_three_hop_paths": len(data.sources),
            "region_provenance_four_hop_paths": len(data.evidence),
            "span_text_mismatches": 0,
        }
        actual = {}
        for name, query in MULTIHOP_QUERIES.items():
            records, _, _ = self.driver.execute_query(
                query, parameters_=parameters, database_=self.database, routing_="r"
            )
            actual[name] = int(records[0]["value"])
            if actual[name] != expected[name]:
                raise LoadVerificationError(
                    f"{name}: expected {expected[name]}, read back {actual[name]}"
                )
        return actual
