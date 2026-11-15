"""Ontology candidate filter: structured conditions -> museum_id set for Hybrid.

The filter turns hard, recorded conditions in a question (amenities, a weekday
the museum must be open, and the region when one of those is present) into a
set of museum IDs. Hybrid then runs Vector + BM25 only inside that set, so
every final evidence item satisfies the conditions and one Cross-Encoder
ranks them.

Descriptive words (theme, "미술관"/"박물관") stay soft: they remain in the query
for semantic ranking and are never used to drop candidates, because users
apply them loosely ("홍주성역사관" is asked for as "전시관") and topic labels
are keyword-derived (UNVERIFIED) and cover only part of the facilities.

Two interchangeable backends give the same answer because both come from
src/data_pipeline/neo4j/ontology_v2/rules.py:
  - LocalOntologyIndex: computes attributes from the read-only CSV (default).
  - Neo4jOntologyIndex: reads the same attributes from the v2 graph.
Nothing here writes to the CSV, Chroma or Neo4j.
"""

from __future__ import annotations

import csv
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from src.data_pipeline.neo4j.ontology_v2.rules import (
    WEEKDAYS,
    map_amenity_token,
    parse_closure,
    split_amenity_tokens,
)
from src.region_aliases import canonicalize_sido, sido_aliases

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = PROJECT_ROOT / "data" / "processed" / "museum_final_738.csv"

# ---------------------------------------------------------------------------
# Condition extraction (rule-based, no LLM call)
# ---------------------------------------------------------------------------

# Question wording -> Amenity names from the v2 controlled vocabulary.
AMENITY_QUERY_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"수유실|수유\s*시설|기저귀", ("수유실",)),
    (r"장애인\s*주차", ("장애인 주차구역",)),
    (r"주차", ("주차장",)),
    (r"장애인\s*(?:용\s*)?화장실", ("장애인 화장실",)),
    (r"휠체어", ("휠체어 대여·이용",)),
    (r"엘리베이터|승강기", ("엘리베이터·리프트",)),
    (r"유모차", ("유모차 대여",)),
    (r"카페", ("카페",)),
    (r"식당|레스토랑", ("식당",)),
    (r"기념품|뮤지엄\s*[샵숍]|아트\s*[샵숍]", ("기념품점",)),
    (r"물품\s*보관", ("물품보관",)),
    (r"와이파이|무선\s*인터넷", ("무선인터넷",)),
    (r"자전거", ("자전거 보관대",)),
    (r"전기차\s*충전", ("전기차 충전",)),
)
# An amenity word only counts as a condition when the question asks for it.
_AMENITY_ASK = r"(?:이|가|도)?\s*(?:있|되|가능|갖춘|딸린|포함|제공|이용)"

_WEEKDAY_OPEN_RE = re.compile(
    r"(?P<day>[월화수목금토일])요일(?:에도|에|날에도|날)?\s*"
    r"(?:문\s*)?(?:여는|열려|열린|열어|개관|운영|관람\s*가능|갈\s*수\s*있)"
)
_WEEKEND_OPEN_RE = re.compile(r"주말(?:에도|에)?\s*(?:문\s*)?(?:여는|열려|열린|개관|운영|관람\s*가능|갈\s*수\s*있)")

_SIDO_TERMS = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주광역시": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도", "전북": "전북특별자치도", "전라북도": "전북특별자치도",
    "전남": "전라남도", "전라남도": "전라남도", "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도", "제주": "제주특별자치도",
}
_SIDO_RE = re.compile("|".join(sorted(map(re.escape, _SIDO_TERMS), key=len, reverse=True)))

# Same spelling groups as the BM25 / Chroma filters (query-time aliases only).
SIDO_SPELLINGS: dict[str, tuple[str, ...]] = {
    "세종특별자치시": ("세종특별자치시", "세종특별시"),
    "전북특별자치도": ("전북특별자치도", "전라북도"),
    "전라남도": ("전라남도", "전남광주통합특별시", "전남광주특별자치도"),
    "강원특별자치도": ("강원특별자치도", "강원도"),
}


def sido_spellings(sido: str) -> tuple[str, ...]:
    """Every stored spelling of one region (team alias families + legacy names)."""
    names = [*SIDO_SPELLINGS.get(sido, (sido,)), *sido_aliases(sido)]
    return tuple(dict.fromkeys(names))


@dataclass(frozen=True)
class StructuredConditions:
    """Hard conditions used to filter, plus the region that scopes them."""

    amenities: tuple[str, ...] = ()
    open_weekdays: tuple[str, ...] = ()
    sido: str | None = None
    matched_terms: tuple[str, ...] = field(default=(), compare=False)

    @property
    def has_hard_conditions(self) -> bool:
        return bool(self.amenities or self.open_weekdays)

    def describe(self) -> str:
        parts = []
        if self.sido:
            parts.append(f"지역 {self.sido}")
        if self.amenities:
            parts.append("편의시설 " + "·".join(self.amenities))
        if self.open_weekdays:
            parts.append("".join(self.open_weekdays) + "요일 개관")
        return ", ".join(parts)


def extract_conditions(question: str) -> StructuredConditions:
    """Extract hard conditions; return an empty result when there are none."""
    text = " ".join(str(question or "").split())
    amenities: list[str] = []
    terms: list[str] = []
    for pattern, names in AMENITY_QUERY_TERMS:
        match = re.search(rf"(?:{pattern})[가-힣]*(?:\s*(?:대여|이용|시설|공간)[가-힣]*)?\s*{_AMENITY_ASK}", text)
        if not match:
            continue
        if names == ("주차장",) and "장애인 주차구역" in amenities:
            continue  # "장애인 주차" already covers the parking request
        terms.append(match.group(0))
        amenities.extend(name for name in names if name not in amenities)
    weekdays: list[str] = []
    for match in _WEEKDAY_OPEN_RE.finditer(text):
        terms.append(match.group(0))
        weekdays.append(match.group("day"))
    if _WEEKEND_OPEN_RE.search(text):
        terms.append(_WEEKEND_OPEN_RE.search(text).group(0))
        weekdays.extend(("토", "일"))
    weekdays = [day for day in WEEKDAYS if day in weekdays]
    if not amenities and not weekdays:
        return StructuredConditions()
    region = _SIDO_RE.search(text)
    return StructuredConditions(
        amenities=tuple(amenities),
        open_weekdays=tuple(weekdays),
        sido=_SIDO_TERMS[region.group(0)] if region else None,
        matched_terms=tuple(terms),
    )


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MuseumFacts:
    museum_id: str
    sido: str
    amenities: dict[str, tuple[str, ...]]  # amenity -> raw tokens it came from
    closure: dict[str, Any]

    def is_open_on(self, day: str) -> bool:
        if self.closure.get("open_all_year"):
            return True
        if self.closure.get("closure_parse_status") != "parsed":
            return False  # unknown schedule never passes a hard filter
        return day not in self.closure.get("closure_weekdays", [])


class CandidateIndex(Protocol):
    backend: str

    def candidates(self, conditions: StructuredConditions) -> dict[str, dict[str, Any]]:
        """Return {museum_id: evidence of the matched conditions}."""


def _sido_matches(stored: str, wanted: str) -> bool:
    stored = canonicalize_sido(stored)
    return any(canonicalize_sido(name) == stored for name in sido_spellings(wanted))


def _match_evidence(facts: MuseumFacts, conditions: StructuredConditions) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    if conditions.amenities:
        evidence["amenities"] = {name: list(facts.amenities[name]) for name in conditions.amenities}
    if conditions.open_weekdays:
        evidence["closure_weekdays"] = list(facts.closure.get("closure_weekdays", []))
        evidence["open_all_year"] = bool(facts.closure.get("open_all_year"))
    return evidence


class LocalOntologyIndex:
    """Attributes computed from the processed CSV with the v2 rules."""

    backend = "local_csv"

    def __init__(self, facts: Iterable[MuseumFacts]):
        self._facts = {fact.museum_id: fact for fact in facts}

    @classmethod
    def from_csv(cls, path: str | Path = DEFAULT_CSV) -> LocalOntologyIndex:
        with Path(path).open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        facts = []
        for row in rows:
            amenities: dict[str, list[str]] = {}
            for token in split_amenity_tokens(row.get("amenities_raw")):
                for name in map_amenity_token(token):
                    amenities.setdefault(name, []).append(token)
            facts.append(MuseumFacts(
                museum_id=row["museum_id"],
                sido=row.get("sido") or "",
                amenities={name: tuple(tokens) for name, tokens in amenities.items()},
                closure=parse_closure(row.get("closure_rule_raw")),
            ))
        return cls(facts)

    def candidates(self, conditions: StructuredConditions) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for fact in self._facts.values():
            if conditions.sido and not _sido_matches(fact.sido, conditions.sido):
                continue
            if any(name not in fact.amenities for name in conditions.amenities):
                continue
            if any(not fact.is_open_on(day) for day in conditions.open_weekdays):
                continue
            found[fact.museum_id] = _match_evidence(fact, conditions)
        return found


NEO4J_CANDIDATE_QUERY = """
MATCH (m:Museum)
WHERE ($sidos IS NULL OR m.sido IN $sidos)
  AND all(name IN $amenities WHERE EXISTS { (m)-[:HAS_AMENITY]->(:Amenity {name: name}) })
  AND (size($open_days) = 0 OR m.open_all_year = true
       OR (m.closure_parse_status = 'parsed'
           AND none(day IN $open_days WHERE day IN m.closure_weekdays)))
OPTIONAL MATCH (m)-[r:HAS_AMENITY]->(a:Amenity) WHERE a.name IN $amenities
RETURN m.museum_id AS museum_id,
       collect([a.name, r.raw_tokens]) AS amenities,
       m.closure_weekdays AS closure_weekdays,
       coalesce(m.open_all_year, false) AS open_all_year
"""


class Neo4jOntologyIndex:
    """Same conditions answered from the ontology v2 graph."""

    backend = "neo4j_v2"

    def __init__(self, driver: Any, database: str):
        self._driver = driver
        self._database = database

    def is_loaded(self) -> bool:
        records, _, _ = self._driver.execute_query(
            "MATCH (a:Amenity {ontology_version: 'v2'}) RETURN count(a) AS n", database_=self._database
        )
        return bool(records and records[0]["n"])

    def candidates(self, conditions: StructuredConditions) -> dict[str, dict[str, Any]]:
        sidos = sorted(sido_spellings(conditions.sido)) if conditions.sido else None
        records, _, _ = self._driver.execute_query(
            NEO4J_CANDIDATE_QUERY,
            sidos=sidos,
            amenities=list(conditions.amenities),
            open_days=list(conditions.open_weekdays),
            database_=self._database,
            routing_="r",
        )
        found: dict[str, dict[str, Any]] = {}
        for record in records:
            evidence: dict[str, Any] = {}
            if conditions.amenities:
                evidence["amenities"] = {name: list(tokens or []) for name, tokens in record["amenities"] if name}
            if conditions.open_weekdays:
                evidence["closure_weekdays"] = list(record["closure_weekdays"] or [])
                evidence["open_all_year"] = bool(record["open_all_year"])
            found[record["museum_id"]] = evidence
        return found


# ---------------------------------------------------------------------------
# Filter facade used by HybridSearchService
# ---------------------------------------------------------------------------


@dataclass
class FilterDecision:
    status: str  # not_applicable | applied | empty
    conditions: StructuredConditions
    backend: str | None = None
    candidate_ids: list[str] | None = None
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "backend": self.backend,
            "conditions": {k: v for k, v in asdict(self.conditions).items() if v},
            "candidate_count": None if self.candidate_ids is None else len(self.candidate_ids),
        }


def describe_match(conditions: StructuredConditions, evidence: Mapping[str, Any]) -> str:
    """One Korean line the answer LLM can cite as the structured-condition basis."""
    parts = []
    for name, tokens in (evidence.get("amenities") or {}).items():
        raw = ", ".join(dict.fromkeys(tokens)) if tokens else "원문 없음"
        parts.append(f"편의시설 '{name}': CSV amenities_raw의 '{raw}' 항목")
    if conditions.open_weekdays:
        days = "·".join(conditions.open_weekdays)
        if evidence.get("open_all_year"):
            parts.append(f"{days}요일 개관: CSV closure_rule_raw가 연중무휴")
        else:
            closed = "·".join(evidence.get("closure_weekdays") or []) or "없음"
            parts.append(f"{days}요일 개관: CSV closure_rule_raw의 정기 휴관 요일은 {closed}")
    return ("; ".join(parts)
            + " (온톨로지 필터가 metadata_provenance.fields의 같은 CSV 값으로 판정한 정적 기록이며 실시간 상태가 아님)")


class OntologyCandidateFilter:
    """Resolve a question to candidate museum IDs, or say it does not apply."""

    def __init__(self, index: CandidateIndex):
        self.index = index

    def resolve(self, question: str) -> FilterDecision:
        conditions = extract_conditions(question)
        if not conditions.has_hard_conditions:
            return FilterDecision("not_applicable", conditions)
        evidence = self.index.candidates(conditions)
        ids = sorted(evidence)
        return FilterDecision("applied" if ids else "empty", conditions, self.index.backend, ids, evidence)


_DEFAULT_FILTER: OntologyCandidateFilter | None = None
_DEFAULT_LOCK = Lock()


def default_candidate_filter() -> OntologyCandidateFilter | None:
    """Local CSV-backed filter unless HYBRID_ONTOLOGY_FILTER=off."""
    if os.getenv("HYBRID_ONTOLOGY_FILTER", "on").strip().lower() in {"0", "off", "false", "no"}:
        return None
    global _DEFAULT_FILTER
    with _DEFAULT_LOCK:
        if _DEFAULT_FILTER is None:
            _DEFAULT_FILTER = OntologyCandidateFilter(LocalOntologyIndex.from_csv())
    return _DEFAULT_FILTER


# ---------------------------------------------------------------------------
# Parity check: local CSV index vs. the loaded ontology v2 graph (read-only)
# ---------------------------------------------------------------------------


def parity_conditions() -> list[StructuredConditions]:
    """Every amenity, every weekday, and region-scoped combinations."""
    from src.data_pipeline.neo4j.ontology_v2.rules import AMENITY_CATEGORIES

    sidos = (None, "서울특별시", "경기도", "제주특별자치도", "전북특별자치도", "전라남도", "세종특별자치시", "강원특별자치도")
    cases = [StructuredConditions(amenities=(name,)) for name in AMENITY_CATEGORIES]
    cases += [StructuredConditions(open_weekdays=(day,)) for day in WEEKDAYS]
    for sido in sidos:
        cases.append(StructuredConditions(amenities=("주차장", "카페"), sido=sido))
        cases.append(StructuredConditions(amenities=("수유실",), open_weekdays=("월",), sido=sido))
        cases.append(StructuredConditions(open_weekdays=("토", "일"), sido=sido))
    return cases


def compare_backends(left: CandidateIndex, right: CandidateIndex,
                     cases: Iterable[StructuredConditions]) -> list[dict[str, Any]]:
    """Return one row per case whose candidate sets differ (empty list = identical)."""
    mismatches = []
    for conditions in cases:
        a, b = set(left.candidates(conditions)), set(right.candidates(conditions))
        if a != b:
            mismatches.append({"conditions": conditions.describe() or str(conditions),
                               f"only_{left.backend}": sorted(a - b), f"only_{right.backend}": sorted(b - a)})
    return mismatches


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Ontology candidate filter utilities")
    parser.add_argument("--check-neo4j", action="store_true",
                        help="local CSV 조회표와 Neo4j v2 후보가 같은지 읽기 전용으로 비교")
    parser.add_argument("question", nargs="?", help="조건 추출과 후보를 확인할 질문")
    args = parser.parse_args(argv)
    local = LocalOntologyIndex.from_csv()
    if args.question:
        decision = OntologyCandidateFilter(local).resolve(args.question)
        print(json.dumps(decision.summary(), ensure_ascii=False, indent=2))
        print(decision.candidate_ids)
    if args.check_neo4j:
        from dotenv import load_dotenv

        from src.agent.neo4j_tls import load_graph_database

        load_dotenv(PROJECT_ROOT / ".env")
        driver = load_graph_database().driver(
            os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            notifications_min_severity="OFF",
        )
        with driver:
            graph = Neo4jOntologyIndex(driver, os.environ["NEO4J_DATABASE"])
            if not graph.is_loaded():
                print("Neo4j에 ontology v2가 적재되어 있지 않습니다.")
                return 1
            cases = parity_conditions()
            mismatches = compare_backends(local, graph, cases)
        print(json.dumps({"cases": len(cases), "mismatches": mismatches}, ensure_ascii=False, indent=2))
        return 1 if mismatches else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
