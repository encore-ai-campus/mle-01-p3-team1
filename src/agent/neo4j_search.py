"""Neo4j TextSpan keyword search adapter for the LangGraph graph route."""

from __future__ import annotations

import re
from typing import Any

from neo4j import RoutingControl

from .region_normalization import canonicalize_sido, expand_sido_terms
from .state import Evidence


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
_STOP_WORDS = {
    "관련", "박물관", "추천", "추천해줘", "알려줘", "찾아줘", "찾아", "소개",
    "소개해줘", "어디", "무엇", "어떤", "있는", "있나요", "있어", "주세요",
    "검색", "검색해줘", "운영", "운영하는", "대해", "대해서",
}
_PARTICLES = tuple(sorted({
    "에서", "으로", "에게", "부터", "까지", "은", "는", "이", "가", "을", "를",
    "에", "의", "로", "와", "과", "도", "만", "랑", "하고", "이나", "나",
}, key=len, reverse=True))


READ_SPANS_QUERY = """
MATCH (museum:Museum)-[:HAS_SPAN]->(span:TextSpan)
WITH museum, span,
     [term IN $terms WHERE
        toLower(coalesce(span.text, "")) CONTAINS term OR
        toLower(coalesce(museum.museum_id, "")) CONTAINS term OR
        toLower(coalesce(museum.name, "")) CONTAINS term OR
        toLower(coalesce(museum.address, "")) CONTAINS term OR
        toLower(coalesce(museum.sido, "")) CONTAINS term OR
        toLower(coalesce(museum.sigungu, "")) CONTAINS term
     ] AS matched_terms
WHERE size(matched_terms) > 0
OPTIONAL MATCH (span)-[:SUPPORTED_BY]->(source:SourceDocument)
WITH museum, span, matched_terms,
     collect(DISTINCT source.doc_id) AS source_doc_ids,
     collect(DISTINCT source.source_url) AS source_urls
OPTIONAL MATCH (museum)-[:LOCATED_IN]->(sigungu:Sigungu)
OPTIONAL MATCH (sigungu)-[:PART_OF]->(sido:Sido)
RETURN museum.museum_id AS museum_id,
       museum.name AS name,
       coalesce(span.text, "") AS text,
       span.span_id AS span_id,
       source_doc_ids AS source_doc_ids,
       source_urls AS source_urls,
       coalesce(sido.name, museum.sido) AS sido,
       coalesce(sigungu.name, museum.sigungu) AS sigungu,
       matched_terms AS matched_terms,
       span.start AS span_start
ORDER BY size(matched_terms) DESC, span_start ASC, name ASC
LIMIT $k
"""


def extract_search_terms(question: str, *, max_terms: int = 8) -> list[str]:
    """Extract a small set of literal Korean/English keywords from a question.

    This is a deterministic keyword baseline for exercising the live graph. It
    is not semantic retrieval; the vector route remains a separate adapter.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question은 비어 있지 않은 문자열이어야 합니다.")
    if type(max_terms) is not int or max_terms < 1:
        raise ValueError("max_terms는 1 이상의 정수여야 합니다.")

    terms: list[str] = []
    for raw in _TOKEN_PATTERN.findall(question.casefold()):
        token = raw
        for particle in _PARTICLES:
            if token.endswith(particle) and len(token) - len(particle) >= 2:
                token = token[:-len(particle)]
                break
        if len(token) < 2 or token in _STOP_WORDS or token in terms:
            continue
        terms.append(token)
        if len(terms) == max_terms:
            break

    if not terms:
        raise ValueError("검색할 키워드가 없습니다. 박물관명이나 설명의 핵심어를 넣어 주세요.")
    return terms


class Neo4jSpanSearch:
    """Run a parameterized, read-only keyword search against loaded graph spans."""

    def __init__(self, driver: Any, database: str):
        if not isinstance(database, str) or not database.strip():
            raise ValueError("database 이름이 필요합니다.")
        self.driver = driver
        self.database = database.strip()

    def search(self, question: str, k: int = 5) -> list[Evidence]:
        if type(k) is not int or k < 1:
            raise ValueError("k는 1 이상의 정수여야 합니다.")
        terms = expand_sido_terms(extract_search_terms(question))
        records, _, _ = self.driver.execute_query(
            READ_SPANS_QUERY,
            parameters_={"terms": terms, "k": k},
            database_=self.database,
            routing_=RoutingControl.READ,
        )

        results: list[Evidence] = []
        for record in records:
            source_doc_ids = [value for value in (record.get("source_doc_ids") or []) if value]
            source_urls = [value for value in (record.get("source_urls") or []) if value]
            evidence: Evidence = {
                "museum_id": record.get("museum_id", ""),
                "name": record.get("name", ""),
                "text": record.get("text", ""),
                "span_id": record.get("span_id", ""),
                "source_doc_ids": source_doc_ids,
                "source_urls": source_urls,
                "source_url": source_urls[0] if source_urls else "",
                "sido": canonicalize_sido(record.get("sido", "")),
                "sigungu": record.get("sigungu", ""),
                "matched_terms": list(record.get("matched_terms") or []),
                "retriever": "graph",
            }
            results.append(evidence)
        return results
