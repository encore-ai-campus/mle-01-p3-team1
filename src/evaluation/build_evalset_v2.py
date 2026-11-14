#!/usr/bin/env python3
"""Build the v2 Supervisor Ragas evaluation set.

v2 = the archived v1 150 questions (unchanged, for regression) + new questions
for the flows added on 2026-11-14:
  - structured_filter        amenity (+ region) conditions -> ontology candidate filter -> Hybrid
  - structured_weekday       open-weekday + amenity conditions
  - structured_no_record     conditions no recorded facility satisfies -> abstain with reason
  - org_same_operator        "○○과 같은 기관이 운영하는 다른 시설" -> Graph same_operator
  - org_same_manager         same, via MANAGED_BY (UNVERIFIED)
  - closure_fact             recorded weekly closure of a named facility
  - unanswerable_count_live  counts / today's status that static records cannot answer

New gold answers are computed deterministically from the read-only CSV with the
same rules as ontology v2 (no LLM). They still need human review before scores
are treated as final. Each generated question is checked to trigger the intended
code path (condition extractor / organization template).

    uv run --no-sync python -m src.evaluation.build_evalset_v2
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.agent.neo4j_text2cypher import _organization_relation, _question_named_museums
from src.data_pipeline.neo4j.ontology_v2.rules import (
    is_self_named,
    map_amenity_token,
    parse_closure,
    resolve_org,
    split_amenity_tokens,
)
from src.hybrid.ontology_filter import (
    LocalOntologyIndex,
    StructuredConditions,
    extract_conditions,
)
from src.region_aliases import canonicalize_sido

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "museum_final_738.csv"
V1_PATH = ROOT / "evaluations" / "datasets" / "archive" / "v1_2026-11-13" / "langgraph" / "LangGraph_Ragas_150_draft.csv"
OUT_PATH = ROOT / "evaluations" / "datasets" / "supervisor_v2" / "Supervisor_Ragas_v2_draft.csv"

COLUMNS = (
    "question_id", "category", "user_input", "answerable", "reference", "reference_contexts",
    "gold_museum_ids", "gold_museum_names", "evidence_doc_ids", "evidence_quote", "label_status",
    "notes", "expected_route", "expected_behavior", "source_set",
)
NEW_LABEL = "auto_generated_needs_human_review"
CONTEXT_PREFIX = "[정제 CSV 구조화 필드; 원문 소개글 인용 아님]"

# Region word used in the question -> canonical label the extractor returns.
REGION_WORDS = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시", "경기도": "경기도",
    "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도", "전북": "전북특별자치도",
    "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도",
}
# Amenity -> natural request phrase that the condition extractor recognizes.
AMENITY_PHRASES = {
    "수유실": "수유실 있는",
    "주차장": "주차 가능한",
    "카페": "카페 있는",
    "장애인 화장실": "장애인 화장실 있는",
    "휠체어 대여·이용": "휠체어 대여 되는",
    "엘리베이터·리프트": "엘리베이터 있는",
    "유모차 대여": "유모차 대여 가능한",
    "기념품점": "기념품점 있는",
    "식당": "식당 있는",
    "물품보관": "물품 보관 가능한",
}
WEEKDAY_PHRASES = {("월",): "월요일에도 여는", ("토", "일"): "주말에 문 여는"}
QUOTAS = {"structured_filter": 12, "structured_weekday": 6, "structured_no_record": 5,
          "org_same_operator": 10, "org_same_manager": 4, "closure_fact": 6}


def has_batchim(word: str) -> bool:
    last = word.strip()[-1]
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0


def josa(word: str, with_batchim: str, without: str) -> str:
    return word + (with_batchim if has_batchim(word) else without)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def first_doc_id(row: dict[str, str]) -> str:
    try:
        docs = json.loads(row.get("source_documents_json") or "[]")
        return str(docs[0]["doc_id"]) if docs else ""
    except (ValueError, KeyError, TypeError):
        return ""


def context(row: dict[str, str], *fields: str) -> str:
    parts = [f"museum_id={row['museum_id']}", f"name={row['name']}",
             f"sido={row['sido']}", f"sigungu={row['sigungu']}"]
    parts += [f"{field}={(row.get(field) or '').strip()}" for field in fields]
    return f"{CONTEXT_PREFIX} " + "; ".join(parts)


def names_list(rows: Iterable[dict[str, str]]) -> str:
    return ", ".join(f"{row['name']}({row['museum_id']})" for row in rows)


def record(category: str, question: str, *, answerable: bool, reference: str, rows: list[dict[str, str]],
           context_fields: tuple[str, ...], expected_route: str, expected_behavior: str, notes: str) -> dict[str, Any]:
    return {
        "category": category,
        "user_input": question,
        "answerable": "yes" if answerable else "no",
        "reference": reference,
        "reference_contexts": json.dumps([context(row, *context_fields) for row in rows], ensure_ascii=False),
        "gold_museum_ids": ";".join(row["museum_id"] for row in rows),
        "gold_museum_names": ";".join(row["name"] for row in rows),
        "evidence_doc_ids": ";".join(filter(None, (first_doc_id(row) for row in rows))),
        "evidence_quote": " | ".join(f"{row['name']}: " + "; ".join((row.get(f) or "").strip() for f in context_fields)
                                     for row in rows),
        "label_status": NEW_LABEL,
        "notes": notes,
        "expected_route": expected_route,
        "expected_behavior": expected_behavior,
        "source_set": "v2_2026-11-14",
    }


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def structured_questions(rows: list[dict[str, str]], index: LocalOntologyIndex) -> list[dict[str, Any]]:
    by_id = {row["museum_id"]: row for row in rows}
    museums_per_sido = defaultdict(int)
    for row in rows:
        museums_per_sido[canonicalize_sido(row["sido"])] += 1
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_amenity: dict[str, int] = defaultdict(int)
    # Spread questions across regions: at most one per region and category.
    used_region: dict[tuple[str, str], int] = defaultdict(int)

    def region_free(category: str, sido: str) -> bool:
        return used_region[(category, sido)] < 1

    def gold_for(conditions: StructuredConditions) -> list[dict[str, str]]:
        return [by_id[mid] for mid in sorted(index.candidates(conditions))]

    for word, sido in REGION_WORDS.items():
        for amenity, phrase in AMENITY_PHRASES.items():
            # amenity + region
            question = f"{word}에서 {phrase} 박물관이나 미술관을 알려줘"
            conditions = StructuredConditions(amenities=(amenity,), sido=sido)
            if extract_conditions(question) != conditions:
                continue
            gold = gold_for(conditions)
            sido_label = sido
            if (1 <= len(gold) <= 4 and used_amenity[amenity] < 2 and region_free("structured_filter", sido)
                    and len(out["structured_filter"]) < QUOTAS["structured_filter"]):
                used_amenity[amenity] += 1
                used_region[("structured_filter", sido)] += 1
                out["structured_filter"].append(record(
                    "structured_filter", question, answerable=True,
                    reference=(f"{sido_label}에서 편의시설 기록에 '{amenity}'이(가) 있는 시설은 {names_list(gold)}입니다. "
                               "편의시설은 데이터에 기록된 내용이며 실시간 운영 상태가 아닙니다."),
                    rows=gold, context_fields=("amenities_raw",),
                    expected_route="hybrid_ontology_filter", expected_behavior="answer",
                    notes=f"gold = {sido_label} + amenities_raw에서 '{amenity}'로 매핑되는 기록이 있는 시설 전체(rules.py)"))
            elif (not gold and museums_per_sido[canonicalize_sido(sido)] >= 20
                  and len(out["structured_no_record"]) < QUOTAS["structured_no_record"]
                  and region_free("structured_no_record", sido)
                  and amenity in {"휠체어 대여·이용", "유모차 대여", "엘리베이터·리프트", "식당", "장애인 화장실"}):
                used_region[("structured_no_record", sido)] += 1
                out["structured_no_record"].append(record(
                    "structured_no_record", question, answerable=False,
                    reference=(f"기록된 데이터에서 조건({sido_label}, 편의시설 {amenity})을 모두 만족하는 시설을 찾지 못했습니다. "
                               "편의시설 정보는 일부 시설에만 기록되어 있어, 기록이 없다고 실제로 없다는 뜻은 아닙니다."),
                    rows=[], context_fields=(), expected_route="hybrid_ontology_filter",
                    expected_behavior="abstain_no_record",
                    notes="조건을 만족하는 기록이 0곳 → 재시도 없이 이유를 안내하며 보류해야 함"))
            # amenity + open weekday + region
            for days, day_phrase in WEEKDAY_PHRASES.items():
                question = f"{day_phrase} {word} 박물관 중 {phrase} 곳"
                conditions = StructuredConditions(amenities=(amenity,), open_weekdays=days, sido=sido)
                if extract_conditions(question) != conditions:
                    continue
                gold = gold_for(conditions)
                if (1 <= len(gold) <= 4 and region_free("structured_weekday", sido)
                        and len(out["structured_weekday"]) < QUOTAS["structured_weekday"]):
                    used_region[("structured_weekday", sido)] += 1
                    day_text = "·".join(days)
                    out["structured_weekday"].append(record(
                        "structured_weekday", question, answerable=True,
                        reference=(f"{sido_label}에서 '{amenity}' 기록이 있고 정기 휴관 요일에 {day_text}요일이 없는 시설은 "
                                   f"{names_list(gold)}입니다. 휴관 정보는 기록된 정적 규칙이며 오늘의 운영 상태가 아닙니다."),
                        rows=gold, context_fields=("amenities_raw", "closure_rule_raw"),
                        expected_route="hybrid_ontology_filter", expected_behavior="answer",
                        notes="gold = 편의시설 기록 + closure_rule_raw 파싱 결과(연중무휴 포함, 파싱 실패 제외)"))
    return [item for category in ("structured_filter", "structured_weekday", "structured_no_record")
            for item in out[category]]


def organization_questions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    name_count = defaultdict(int)
    for row in rows:
        name_count[row["name"]] += 1
    items: list[dict[str, Any]] = []
    for column, relation, category, verb in (
        ("operator_name", "OPERATED_BY", "org_same_operator", "운영"),
        ("manager_name", "MANAGED_BY", "org_same_manager", "관리"),
    ):
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        org_names: dict[str, str] = {}
        for row in rows:
            resolution = resolve_org(row.get(column) or "", row["sido"])
            if resolution is None or (column == "operator_name" and is_self_named(row[column], row["name"])):
                continue
            groups[resolution.org.org_key].append(row)
            org_names[resolution.org.org_key] = resolution.org.name
        made = 0
        for key in sorted(groups, key=lambda k: (len(groups[k]), k)):
            members = sorted(groups[key], key=lambda r: r["museum_id"])
            if not 2 <= len(members) <= 5 or made >= QUOTAS[category]:
                continue
            anchor = next((r for r in members if name_count[r["name"]] == 1), None)
            if anchor is None:
                continue
            question = f"{josa(anchor['name'], '과', '와')} 같은 기관이 {verb}하는 다른 시설은?"
            if _organization_relation(question) != relation or _question_named_museums(question) != [anchor["name"]]:
                continue
            others = [r for r in members if r["museum_id"] != anchor["museum_id"]]
            caution = " 관리기관 연결은 이름 규칙으로 만든 미검증(UNVERIFIED) 정보입니다." if relation == "MANAGED_BY" else ""
            items.append(record(
                category, question, answerable=True,
                reference=(f"{anchor['name']}의 {verb}기관은 '{org_names[key]}'(원문: {anchor[column]})으로 기록되어 있으며, "
                           f"같은 기관이 {verb}하는 다른 시설은 {names_list(others)}입니다.{caution}"),
                rows=[anchor, *others], context_fields=(column,),
                expected_route="graph", expected_behavior="answer",
                notes=(f"gold = {column}을 rules.resolve_org로 정규화한 org_key '{key}'가 같은 시설(anchor 포함). "
                       "Supervisor 전체 흐름(--with-neo4j) 기준")))
            items[-1]["gold_museum_ids"] = ";".join(r["museum_id"] for r in others)
            items[-1]["gold_museum_names"] = ";".join(r["name"] for r in others)
            made += 1
    return items


def closure_questions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    name_count = defaultdict(int)
    for row in rows:
        name_count[row["name"]] += 1
    items: list[dict[str, Any]] = []
    want = [("월", True)] * 3 + [("월", False)] * 2 + [("일", True)]
    for day, closed_wanted in want:
        for row in rows:
            if name_count[row["name"]] != 1 or any(item["gold_museum_ids"] == row["museum_id"] for item in items):
                continue
            parsed = parse_closure(row.get("closure_rule_raw"))
            if parsed["closure_parse_status"] != "parsed" or parsed["open_all_year"]:
                continue
            if (day in parsed["closure_weekdays"]) != closed_wanted or not parsed["closure_weekdays"]:
                continue
            raw = (row.get("closure_rule_raw") or "").strip()
            answer = (f"{row['name']}은(는) 기록상 매주 {day}요일 휴관입니다(휴관 규칙 원문: {raw})."
                      if closed_wanted else
                      f"{row['name']}의 기록된 정기 휴관 요일은 {'·'.join(parsed['closure_weekdays'])}요일이라 "
                      f"{day}요일은 정기 휴관일이 아닙니다(휴관 규칙 원문: {raw}). 공휴일·임시 휴관은 별도로 확인해야 합니다.")
            items.append(record(
                "closure_fact", f"{josa(row['name'], '은', '는')} {day}요일에 문을 여나요?", answerable=True,
                reference=answer + " 기록된 정적 규칙이며 오늘의 운영 상태가 아닙니다.",
                rows=[row], context_fields=("closure_rule_raw",),
                expected_route="any", expected_behavior="answer",
                notes="gold = closure_rule_raw 파싱 결과(rules.parse_closure)"))
            break
    return items[:QUOTAS["closure_fact"]]


def unanswerable_questions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        tokens = split_amenity_tokens(row.get("amenities_raw"))
        mapped = {name for token in tokens for name in map_amenity_token(token)}
        has_count = any(any(ch.isdigit() for ch in token) for token in tokens)
        if "수유실" in mapped and not has_count and not any(i["gold_museum_ids"] == row["museum_id"] for i in items):
            items.append(record(
                "unanswerable_count_live", f"{row['name']} 수유실은 몇 개 있나요?", answerable=False,
                reference=(f"현재 자료에는 {row['name']}에 수유실이 있다는 기록만 있고 개수는 없어 답할 수 없습니다. "
                           "시설에 직접 확인이 필요합니다."),
                rows=[], context_fields=(), expected_route="any", expected_behavior="abstain",
                notes="편의시설은 존재 여부만 기록됨(수량 없음)"))
        if len(items) >= 2:
            break
    for row in rows:
        if parse_closure(row.get("closure_rule_raw"))["closure_parse_status"] == "parsed":
            items.append(record(
                "unanswerable_count_live", f"오늘 {row['name']} 문 열었는지 실시간으로 알려줘", answerable=False,
                reference=(f"현재 자료의 휴관 정보는 기록된 정적 규칙이라 {row['name']}의 오늘 운영 여부나 임시 휴관은 "
                           "확인할 수 없습니다. 시설에 직접 확인이 필요합니다."),
                rows=[], context_fields=(), expected_route="any", expected_behavior="abstain",
                notes="실시간 상태는 정적 데이터로 답할 수 없음"))
            break
    return items


# ---------------------------------------------------------------------------


def build(csv_path: Path = CSV_PATH, v1_path: Path = V1_PATH) -> list[dict[str, Any]]:
    rows = read_rows(csv_path)
    index = LocalOntologyIndex.from_csv(csv_path)
    carried = []
    for row in read_rows(v1_path):
        item = {column: row.get(column, "") for column in COLUMNS}
        item["expected_route"] = "any"
        item["expected_behavior"] = "answer" if row["answerable"] == "yes" else "abstain"
        item["source_set"] = "v1_2026-11-13"
        carried.append(item)
    new = [*structured_questions(rows, index), *organization_questions(rows),
           *closure_questions(rows), *unanswerable_questions(rows)]
    prefixes = {"structured_filter": "SF", "structured_weekday": "SW", "structured_no_record": "SN",
                "org_same_operator": "OO", "org_same_manager": "OM", "closure_fact": "CF",
                "unanswerable_count_live": "UL"}
    counters: dict[str, int] = defaultdict(int)
    for item in new:
        prefix = prefixes[item["category"]]
        counters[prefix] += 1
        item["question_id"] = f"V2-{prefix}{counters[prefix]:02d}"
    return carried + new


def write(items: list[dict[str, Any]], path: Path = OUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    items = build()
    write(items, args.out)
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[f"{item['source_set']} / {item['category']}"] += 1
    print(json.dumps({"total": len(items), "by_category": dict(sorted(counts.items()))}, ensure_ascii=False, indent=2))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
