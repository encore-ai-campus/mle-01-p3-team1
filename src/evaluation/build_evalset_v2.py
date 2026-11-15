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
import re
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
    # Names only: a museum_id never appears in an answer, so a reference that cites one cannot be
    # attributed to the evidence by the judge (2026-11-15: Context Recall 0.03 -> 0.77 without IDs).
    # The IDs stay in gold_museum_ids for the ranking metrics.
    return ", ".join(row["name"] for row in rows)


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
# 2026-11-15 additions: combined-route questions and everyday-wording questions
# ---------------------------------------------------------------------------

# Questions removed on 2026-11-15 because their labels depend on a judgement call
# (does a tea house count as a cafe? is a kiosk a restaurant? do irregular closures count as open?).
# IDs of the other questions are kept as they were.
EXCLUDED_IDS = {
    "V2-SF05": "찻집을 카페로 볼지 판단이 필요함",
    "V2-SW05": "찻집을 카페로 볼지 판단이 필요함",
    "V2-SF08": "매점·공동취사장을 식당으로 볼지 판단이 필요함",
    "V2-SW06": "불규칙 휴관('관리운영상 정하는 휴관일')을 개관으로 볼지 판단이 필요함",
}

# (anchor facility, target facility, thing asked about, word that must identify the target's text)
COMBINED_CASES = (
    ("울산대곡박물관", "울산암각화박물관", "암각화", "암각화 유적"),
    ("신안갯벌박물관", "세계화석광물박물관", "화석과 광물", "화석"),
    ("문경도자기박물관", "문경자연생태박물관", "자연 생태", "생태"),
    ("고성공룡박물관", "고성탈박물관", "탈", "탈"),
    ("짜장면박물관", "인천개항장 근대건축전시관", "개항기 건축물", "근대건축"),
    ("남원향토박물관", "혼불문학관", "문학 작품", "혼불"),
    ("천안박물관", "유관순열사기념관", "유관순 열사 자료", "유관순"),
    ("한성백제박물관", "서울생활사박물관", "서울의 생활사 자료", "생활사"),
    ("박인환문학관", "한국시집박물관", "시집", "시집"),
    ("부천활박물관", "고강선사유적체험관", "선사시대 유적", "선사유적"),
    ("대구근대역사관", "대구방짜유기박물관", "방짜 유기", "방짜"),
    ("홍주성역사관", "결성농요농사박물관", "농요", "농요"),
    ("해남공룡박물관", "고산윤선도박물관", "윤선도 관련 자료", "윤선도"),
    ("태백석탄박물관", "태백고생대자연사박물관", "고생대 화석", "고생대"),
    ("안성맞춤박물관", "박두진문학관", "시인 박두진의 문학 자료", "박두진"),
)
EVERYDAY_CITIES = ("경주", "통영", "홍성", "나주", "포항")
EVERYDAY_TYPE_CITIES = ("가평", "화순", "통영")
EVERYDAY_THEMES = (("공룡", "공룡을 볼 수 있는 박물관은 어디야?"), ("곤충", "곤충을 볼 수 있는 박물관 알려줘"),
                   ("옹기", "옹기를 전시하는 박물관이 있어?"))


def _sentence_with(text: str, word: str) -> str:
    for sentence in re.split(r"(?<=[.다])\s+", " ".join(str(text or "").split())):
        if word in sentence:
            return sentence.strip()
    return ""


def combined_questions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Relation + description: the graph names the same-operator facilities, the text names the target."""
    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_name[row["name"]].append(row)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    org_names: dict[str, str] = {}
    key_of: dict[str, str] = {}
    for row in rows:
        resolution = resolve_org(row.get("operator_name") or "", row["sido"])
        if resolution is None or is_self_named(row["operator_name"], row["name"]):
            continue
        groups[resolution.org.org_key].append(row)
        org_names[resolution.org.org_key] = resolution.org.name
        key_of[row["museum_id"]] = resolution.org.org_key
    items = []
    for anchor_name, target_name, phrase, word in COMBINED_CASES:
        if len(by_name.get(anchor_name, [])) != 1 or len(by_name.get(target_name, [])) != 1:
            raise ValueError(f"combined case needs unique facility names: {anchor_name}, {target_name}")
        anchor, target = by_name[anchor_name][0], by_name[target_name][0]
        key = key_of.get(anchor["museum_id"])
        members = groups.get(key, [])
        if key is None or target not in members:
            raise ValueError(f"{target_name} is not in the same operator group as {anchor_name}")
        others = [m for m in members if m["museum_id"] not in (anchor["museum_id"], target["museum_id"])]
        sentence = _sentence_with(f"{target['name']}. {target.get('text', '')}", word)
        if not sentence:
            raise ValueError(f"'{word}' does not appear in {target_name}")
        clashes = [m["name"] for m in others if word in m["name"] or word in (m.get("text") or "")]
        if clashes:
            raise ValueError(f"'{word}' also appears in {clashes}; the answer would not be unique")
        question = f"{josa(anchor_name, '과', '와')} 같은 기관이 운영하는 시설 중 {josa(phrase, '을', '를')} 볼 수 있는 곳은?"
        if _organization_relation(question) != "OPERATED_BY" or _question_named_museums(question) != [anchor_name]:
            raise ValueError(f"the relation template does not read: {question}")
        item = record(
            "combined_relation_description", question, answerable=True,
            reference=(f"{anchor_name}의 운영기관은 '{org_names[key]}'(원문: {anchor['operator_name']})으로 기록되어 있으며, "
                       f"같은 기관이 운영하는 시설 중 {phrase} 관련 내용을 볼 수 있는 곳은 {target_name}입니다."),
            rows=[anchor, target], context_fields=("operator_name",),
            expected_route="combined", expected_behavior="answer",
            notes=(f"관계(같은 운영기관 org_key '{key}')와 설명('{word}')이 함께 필요. gold = 같은 기관 시설 중 "
                   f"본문·이름에 '{word}'가 있는 곳(유일)"))
        item["gold_museum_ids"] = target["museum_id"]
        item["gold_museum_names"] = target["name"]
        item["reference_contexts"] = json.dumps(
            [context(anchor, "operator_name"), context(target, "operator_name"), f"[CSV 소개글 인용] {sentence}"],
            ensure_ascii=False)
        item["evidence_quote"] = f"{anchor_name}: {anchor['operator_name']} | {target_name}: {target['operator_name']} | {sentence}"
        items.append(item)
    return items


def everyday_questions(rows: list[dict[str, str]], index: LocalOntologyIndex) -> list[dict[str, Any]]:
    """Questions worded the way a visitor would ask. Gold is read straight from the CSV columns."""
    items: list[dict[str, Any]] = []
    sigungu_names = defaultdict(set)
    for row in rows:
        sigungu_names[row["sigungu"]].add(row["sido"])

    def city_rows(city: str) -> list[dict[str, str]]:
        found = [r for r in rows if r["sigungu"] in (f"{city}시", f"{city}군")]
        if not found or len({r["sido"] for r in found}) != 1:
            raise ValueError(f"city '{city}' is not a single region in the CSV")
        return sorted(found, key=lambda r: r["museum_id"])

    for city in EVERYDAY_CITIES:
        members = city_rows(city)
        items.append(record(
            "everyday_region_list", f"{city}에 있는 박물관이나 미술관을 알려줘", answerable=True,
            reference=f"{city}({members[0]['sido']} {members[0]['sigungu']})에 있는 시설은 {names_list(members)}입니다.",
            rows=members, context_fields=(), expected_route="any", expected_behavior="answer",
            notes="시·군 이름만으로 지역을 묻는 일상 질문. gold = CSV의 sigungu가 같은 모든 시설"))
    for city in EVERYDAY_TYPE_CITIES:
        members = [r for r in city_rows(city) if "미술관" in r["name"]]
        if not members:
            raise ValueError(f"no art museum in {city}")
        items.append(record(
            "everyday_region_type", f"{city}에 있는 미술관은?", answerable=True,
            reference=f"{city}에 있는 미술관은 {names_list(members)}입니다.",
            rows=members, context_fields=(), expected_route="any", expected_behavior="answer",
            notes="시·군 + 시설 종류. gold = 해당 시·군 시설 중 이름에 '미술관'이 있는 곳"))
    for word, question in EVERYDAY_THEMES:
        members = sorted((r for r in rows if word in r["name"]), key=lambda r: r["museum_id"])
        if not 2 <= len(members) <= 6:
            raise ValueError(f"theme '{word}' matches {len(members)} facilities")
        item = record(
            "everyday_theme", question, answerable=True,
            reference=f"'{word}'를 주제로 한 시설로는 {names_list(members)}이(가) 있습니다.",
            rows=members, context_fields=(), expected_route="any", expected_behavior="answer",
            notes=f"주제 단어를 이름에 가진 시설이 gold(전국). 소개글에만 '{word}'가 나오는 시설은 gold에 없음")
        item["evidence_quote"] = " | ".join(r["name"] for r in members)
        items.append(item)
    members = sorted((r for r in rows if r["sido"] == "서울특별시"
                      and "수유실" in {n for t in split_amenity_tokens(r.get("amenities_raw")) for n in map_amenity_token(t)}),
                     key=lambda r: r["museum_id"])
    question = "서울에서 아이랑 갈 건데 수유실 있는 박물관 알려줘"
    conditions = extract_conditions(question)
    gold = sorted(index.candidates(conditions))
    if not conditions.has_hard_conditions or gold != sorted(r["museum_id"] for r in members):
        raise ValueError("the everyday amenity question does not match the filter")
    items.append(record(
        "everyday_amenity", question, answerable=True,
        reference=(f"서울특별시에서 편의시설 기록에 '수유실'이(가) 있는 시설은 {names_list(members)}입니다. "
                   "편의시설은 데이터에 기록된 내용이며 실시간 운영 상태가 아닙니다."),
        rows=members, context_fields=("amenities_raw",), expected_route="any", expected_behavior="answer",
        notes="수유실 조건 + 일상 말투('아이랑 갈 건데')"))
    unanswerable = (
        ("제주도에서 비 오는 날 갈 만한 실내 전시관 있어?",
         "현재 자료에는 시설이 실내인지 실외인지와 날씨별 추천 정보가 없어 답할 수 없습니다. 시설에 직접 확인이 필요합니다.",
         "실내·실외 구분이 데이터에 없음"),
        ("국립중앙박물관 근처에 다른 박물관도 있어?",
         "현재 자료에는 국립중앙박물관이 없어 그 근처 시설을 찾을 수 없습니다.",
         "738곳 데이터에 국립중앙박물관이 없음"),
        ("휠체어로 관람 가능한 서울 박물관이 있을까?",
         "기록된 데이터에서 조건(서울특별시, 편의시설 휠체어 대여·이용)을 모두 만족하는 시설을 찾지 못했습니다. "
         "편의시설 정보는 일부 시설에만 기록되어 있어, 기록이 없다고 실제로 없다는 뜻은 아닙니다.",
         "서울 시설 중 휠체어 기록이 0건"),
    )
    for question, reference, note in unanswerable:
        items.append(record(
            "everyday_unanswerable", question, answerable=False, reference=reference, rows=[], context_fields=(),
            expected_route="any", expected_behavior="abstain", notes=note))
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
                "unanswerable_count_live": "UL", "combined_relation_description": "CB",
                "everyday_region_list": "ER", "everyday_region_type": "ET", "everyday_theme": "EH",
                "everyday_amenity": "EA", "everyday_unanswerable": "EU"}
    counters: dict[str, int] = defaultdict(int)
    for item in new:
        prefix = prefixes[item["category"]]
        counters[prefix] += 1
        item["question_id"] = f"V2-{prefix}{counters[prefix]:02d}"
    new = [item for item in new if item["question_id"] not in EXCLUDED_IDS]
    # Added after the numbering above so the IDs of the earlier questions never move.
    later = [*combined_questions(rows), *everyday_questions(rows, index)]
    for item in later:
        prefix = prefixes[item["category"]]
        counters[prefix] += 1
        item["question_id"] = f"V2-{prefix}{counters[prefix]:02d}"
        item["source_set"] = "v2_2026-11-15"
    return carried + new + later


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
