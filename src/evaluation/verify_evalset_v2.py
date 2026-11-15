"""Check the v2 evaluation labels against the raw CSV without an LLM.

Most v2 labels were generated from the same rules as the ontology filter, so a check that
reuses those rules would only agree with itself. These checks therefore read the raw CSV
columns with their own simple patterns and report every disagreement for a person to look at.
A flagged row is a question to review, not proof that the label is wrong.

    python -m src.evaluation.verify_evalset_v2
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVALSET = ROOT / "evaluations" / "datasets" / "supervisor_v2" / "Supervisor_Ragas_v2_draft.csv"
MUSEUMS = ROOT / "data" / "processed" / "museum_final_738.csv"
REPORT = ROOT / "evaluations" / "datasets" / "supervisor_v2" / "review" / "auto_verification_2026-11-15.csv"

# Raw-text patterns per amenity label (independent of rules.py's token mapping).
AMENITY_PATTERNS = {
    "주차장": r"주차", "장애인 주차구역": r"장애인.{0,3}주차", "장애인 화장실": r"장애인.{0,3}화장실",
    "수유실": r"수유|기저귀", "카페": r"카페|커피", "식당": r"식당|레스토랑|푸드코트",
    "엘리베이터·리프트": r"엘리베이터|승강기|리프트", "휠체어 대여·이용": r"휠체어", "유모차 대여": r"유모차",
    "기념품점": r"기념품|뮤지엄.?[샵숍]|아트.?[샵숍]", "물품보관": r"물품.?보관|사물함", "무선인터넷": r"와이파이|무선",
    "자전거 보관대": r"자전거", "전기차 충전": r"전기차",
}
SIDOS = ("서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
         "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도")
SIDO_PREFIXES = SIDOS + ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
                         "전북", "전남", "경북", "경남", "제주", "전남광주통합특별시", "전남광주특별자치도", "강원도", "전라북도")
DAYS = "월화수목금토일"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def squash(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def sido_key(value: str) -> str:
    value = str(value or "")
    for canonical, variants in (("전북특별자치도", ("전북특별자치도", "전라북도")), ("전라남도", ("전라남도", "전남광주통합특별시", "전남광주특별자치도")),
                                ("강원특별자치도", ("강원특별자치도", "강원도")), ("세종특별자치시", ("세종특별자치시", "세종특별시"))):
        if value in variants:
            return canonical
    return value


def amenity_hit(raw: str, label: str) -> bool | None:
    pattern = AMENITY_PATTERNS.get(label)
    return None if pattern is None else bool(re.search(pattern, raw or ""))


def closed_days(raw: str) -> set[str]:
    """Weekdays that closure_rule_raw lists as closed. A clause with a clock time is opening hours."""
    days: set[str] = set()
    for clause in re.split(r"[;+,]", raw or ""):
        clause = clause.strip()
        if not clause or re.search(r"\d{1,2}:\d{2}", clause):
            continue
        days.update(re.findall(rf"([{DAYS}])요일", clause))
        if re.fullmatch(rf"[{DAYS}]", clause):  # "월+토+일" style
            days.add(clause)
    return days


def crude_org_key(raw: str) -> str:
    value = re.sub(r"^(?:\(주\)|㈜|주식회사|\(재\)|재단법인|\(사\)|사단법인)\s*", "", str(raw or "").strip())
    value = re.sub(r"청$", "", squash(value))  # 창녕군청 -> 창녕군, 울산광역시청 -> 울산광역시
    changed = True
    while changed:
        changed = False
        for prefix in sorted(SIDO_PREFIXES, key=len, reverse=True):
            if value.startswith(prefix) and len(value) > len(prefix):
                value, changed = value[len(prefix):], True
                break
    return value


class Verifier:
    def __init__(self, museums: list[dict[str, str]]):
        self.by_id = {row["museum_id"]: row for row in museums}
        self.by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in museums:
            self.by_name[row["name"]].append(row)
        self.rows = museums

    # -- helpers -----------------------------------------------------------------
    def region_rows(self, sido: str) -> list[dict[str, str]]:
        return [row for row in self.rows if sido_key(row["sido"]) == sido_key(sido)]

    @staticmethod
    def diff(expected: set[str], gold: set[str]) -> str:
        missing, extra = sorted(expected - gold), sorted(gold - expected)
        parts = []
        if missing:
            parts.append("CSV에는 조건에 맞는데 정답에 없음: " + ",".join(missing))
        if extra:
            parts.append("정답에는 있는데 CSV 확인에서 조건에 안 맞음: " + ",".join(extra))
        return " / ".join(parts)

    # -- checks ------------------------------------------------------------------
    def check_common(self, row: dict[str, str]) -> list[str]:
        problems = []
        ids = [item for item in row["gold_museum_ids"].split(";") if item]
        names = [item for item in row["gold_museum_names"].split(";") if item]
        for museum_id in ids:
            if museum_id not in self.by_id:
                problems.append(f"정답 시설 번호 {museum_id}가 CSV에 없음")
        if len(ids) == len(names):
            for museum_id, name in zip(ids, names):
                if museum_id in self.by_id and self.by_id[museum_id]["name"] != name:
                    problems.append(f"{museum_id}의 이름이 {self.by_id[museum_id]['name']}인데 정답에는 {name}")
        elif ids or names:
            problems.append("정답 시설 번호와 이름의 개수가 다름")
        try:
            contexts = json.loads(row["reference_contexts"] or "[]")
            if row["answerable"] == "yes" and not contexts:
                problems.append("답변 가능 문항인데 정답 근거(reference_contexts)가 비어 있음")
        except json.JSONDecodeError:
            problems.append("reference_contexts가 올바른 JSON이 아님")
        if row["answerable"] == "yes" and not row["reference"].strip():
            problems.append("정답 문장이 비어 있음")
        return problems

    def check_v1_quote(self, row: dict[str, str]) -> list[str]:
        if row["answerable"] != "yes" or not row["evidence_quote"].strip():
            return []
        ids = [item for item in row["gold_museum_ids"].split(";") if item]
        texts = [squash(self.by_id[i].get("text", "")) for i in ids if i in self.by_id]
        for quote in (part for part in row["evidence_quote"].split(" | ") if part.strip()):
            if not any(squash(quote) in text for text in texts):
                return ["근거 인용문이 정답 시설의 CSV 소개글에 그대로 들어 있지 않음"]
        return []

    def check_amenity(self, row: dict[str, str]) -> list[str]:
        reference = row["reference"]
        label_match = re.search(r"'(.+?)'이\(가\) 있는", reference) or re.search(r"편의시설 ([^)]+?)\)", reference)
        region_match = re.match(r"(.+?)에서 편의시설", reference) or re.search(r"조건\(([^,]+),", reference)
        if not label_match or not region_match:
            return ["정답 문장에서 조건을 읽지 못해 자동 확인을 건너뜀"]
        label, region = label_match.group(1).strip(), region_match.group(1).strip()
        if amenity_hit("", label) is None:
            return [f"'{label}' 조건은 자동 확인 패턴이 없어 건너뜀"]
        expected = {r["museum_id"] for r in self.region_rows(region) if amenity_hit(r.get("amenities_raw", ""), label)}
        gold = {item for item in row["gold_museum_ids"].split(";") if item}
        return [self.diff(expected, gold)] if expected != gold else []

    def check_weekday(self, row: dict[str, str]) -> list[str]:
        reference = row["reference"]
        label_match = re.search(r"'(.+?)' 기록이 있고", reference)
        days_match = re.search(r"휴관 요일에 ([월화수목금토일·]+)요일이 없는", reference)
        region_match = re.match(r"(.+?)에서 '", reference)
        if not (label_match and days_match and region_match):
            return ["정답 문장에서 조건을 읽지 못해 자동 확인을 건너뜀"]
        label, region = label_match.group(1), region_match.group(1)
        days = set(days_match.group(1).replace("·", ""))
        if amenity_hit("", label) is None:
            return [f"'{label}' 조건은 자동 확인 패턴이 없어 건너뜀"]
        expected = {r["museum_id"] for r in self.region_rows(region)
                    if amenity_hit(r.get("amenities_raw", ""), label) and not (days & closed_days(r.get("closure_rule_raw", "")))}
        gold = {item for item in row["gold_museum_ids"].split(";") if item}
        return [self.diff(expected, gold)] if expected != gold else []

    def check_org(self, row: dict[str, str], column: str) -> list[str]:
        anchor_name = re.match(r"(.+?)(?:과|와) 같은 기관이", row["user_input"])
        if not anchor_name or len(self.by_name.get(anchor_name.group(1), [])) != 1:
            return ["기준 시설을 이름으로 하나로 정하지 못해 자동 확인을 건너뜀"]
        anchor = self.by_name[anchor_name.group(1)][0]
        key = crude_org_key(anchor.get(column, ""))
        if not key:
            return ["기준 시설의 기관 기록이 비어 있음"]
        expected = {r["museum_id"] for r in self.rows
                    if r["museum_id"] != anchor["museum_id"] and crude_org_key(r.get(column, "")) == key}
        gold = {item for item in row["gold_museum_ids"].split(";") if item}
        return [self.diff(expected, gold)] if expected != gold else []

    def check_closure(self, row: dict[str, str]) -> list[str]:
        day = re.search(rf"([{DAYS}])요일", row["user_input"])
        ids = [item for item in row["gold_museum_ids"].split(";") if item]
        if not day or len(ids) != 1 or ids[0] not in self.by_id:
            return ["질문에서 요일이나 시설을 읽지 못해 자동 확인을 건너뜀"]
        museum = self.by_id[ids[0]]
        raw = museum.get("closure_rule_raw", "")
        says_closed = "휴관입니다" in row["reference"] or "휴관이" in row["reference"] and "없" not in row["reference"]
        crude_closed = day.group(1) in closed_days(raw)
        problems = []
        if squash(raw) and squash(raw) not in squash(row["reference"]) and squash(raw) not in squash(row["evidence_quote"]):
            problems.append("정답 문장과 근거 인용에 CSV의 휴관 규칙 원문이 그대로 나오지 않음")
        if says_closed != crude_closed:
            problems.append(f"정답은 {'휴관' if says_closed else '개관'}인데 CSV 원문({raw})에서는 {day.group(1)}요일이 "
                            f"{'휴관' if crude_closed else '휴관이 아님'}으로 읽힘")
        return problems

    def check_count(self, row: dict[str, str]) -> list[str]:
        name = re.match(r"(.+?) (?:수유실|화장실|주차장|엘리베이터|카페|식당)", row["user_input"])
        label = next((k for k in AMENITY_PATTERNS if k in row["user_input"] or k[:2] in row["user_input"]), "수유실")
        if not name or len(self.by_name.get(name.group(1), [])) != 1:
            return ["시설을 이름으로 정하지 못해 자동 확인을 건너뜀"]
        raw = self.by_name[name.group(1)][0].get("amenities_raw", "")
        problems = []
        if not amenity_hit(raw, label):
            problems.append(f"정답 문장은 '{label} 기록이 있다'고 하는데 CSV 편의시설에 없음({raw})")
        if re.search(rf"({AMENITY_PATTERNS.get(label, '수유')})\s*\d+\s*(?:개|곳|실)", raw):
            problems.append("CSV에 개수가 적혀 있어 '개수는 알 수 없다'는 정답이 틀릴 수 있음")
        return problems

    def check_combined(self, row: dict[str, str]) -> list[str]:
        anchor_name = re.match(r"(.+?)(?:과|와) 같은 기관이", row["user_input"])
        ids = [item for item in row["gold_museum_ids"].split(";") if item]
        word = re.search(r"본문·이름에 '(.+?)'가 있는 곳", row["notes"])
        if not anchor_name or len(self.by_name.get(anchor_name.group(1), [])) != 1 or len(ids) != 1 or ids[0] not in self.by_id:
            return ["기준 시설이나 정답 시설을 하나로 정하지 못해 자동 확인을 건너뜀"]
        anchor, target = self.by_name[anchor_name.group(1)][0], self.by_id[ids[0]]
        problems = []
        key = crude_org_key(anchor.get("operator_name", ""))
        if not key or crude_org_key(target.get("operator_name", "")) != key:
            problems.append("정답 시설의 운영기관이 기준 시설과 같지 않음")
        quote = row["evidence_quote"].split(" | ")[-1].strip()
        if quote and squash(quote) not in squash(target.get("name", "") + ". " + target.get("text", "")):
            problems.append("근거로 든 소개글 문장이 정답 시설의 CSV 소개글에 그대로 없음")
        if word:
            others = [r for r in self.rows if r["museum_id"] not in (anchor["museum_id"], target["museum_id"])
                      and crude_org_key(r.get("operator_name", "")) == key
                      and (word.group(1) in r["name"] or word.group(1) in r.get("text", ""))]
            if others:
                problems.append("같은 기관의 다른 시설도 '%s'가 나와 정답이 유일하지 않음: %s" % (word.group(1), ", ".join(r["name"] for r in others)))
        return problems

    def city_rows(self, city: str) -> list[dict[str, str]]:
        return [r for r in self.rows if r["sigungu"] in (f"{city}시", f"{city}군")]

    def check_everyday_region(self, row: dict[str, str], only_art: bool) -> list[str]:
        city = re.match(r"(.+?)에 있는", row["user_input"])
        if not city:
            return ["질문에서 지역을 읽지 못해 자동 확인을 건너뜀"]
        members = self.city_rows(city.group(1))
        if only_art:
            members = [r for r in members if "미술관" in r["name"]]
        expected = {r["museum_id"] for r in members}
        gold = {item for item in row["gold_museum_ids"].split(";") if item}
        return [self.diff(expected, gold)] if expected != gold else []

    def check_everyday_theme(self, row: dict[str, str]) -> list[str]:
        word = re.search(r"'(.+?)'를 주제로", row["reference"])
        if not word:
            return ["정답 문장에서 주제를 읽지 못해 자동 확인을 건너뜀"]
        expected = {r["museum_id"] for r in self.rows if word.group(1) in r["name"]}
        gold = {item for item in row["gold_museum_ids"].split(";") if item}
        return [self.diff(expected, gold)] if expected != gold else []

    def check_everyday_unanswerable(self, row: dict[str, str]) -> list[str]:
        question = row["user_input"]
        if "국립중앙박물관" in question:
            found = [r["name"] for r in self.rows if "국립중앙박물관" in r["name"]]
            return [f"CSV에 국립중앙박물관이 있음: {found}"] if found else []
        if "휠체어" in question:
            found = [r["name"] for r in self.region_rows("서울특별시") if amenity_hit(r.get("amenities_raw", ""), "휠체어 대여·이용")]
            return [f"서울에 휠체어 기록이 있는 시설이 있음: {found}"] if found else []
        return ["사람이 확인해야 하는 질문이라 자동 확인을 건너뜀"]

    def verify(self, row: dict[str, str]) -> tuple[str, list[str]]:
        category = row["category"]
        problems = self.check_common(row)
        if row["source_set"].startswith("v1"):
            problems += self.check_v1_quote(row)
            return ("v1/" + ("답 없음(자동확인 불가)" if row["answerable"] == "no" else "질문-근거"), problems)
        if category in ("structured_filter", "structured_no_record"):
            problems += self.check_amenity(row)
        elif category == "structured_weekday":
            problems += self.check_weekday(row)
        elif category == "org_same_operator":
            problems += self.check_org(row, "operator_name")
        elif category == "org_same_manager":
            problems += self.check_org(row, "manager_name")
        elif category == "closure_fact":
            problems += self.check_closure(row)
        elif category == "unanswerable_count_live":
            problems += self.check_count(row)
        elif category == "combined_relation_description":
            problems += self.check_combined(row)
        elif category == "everyday_region_list":
            problems += self.check_everyday_region(row, only_art=False)
        elif category == "everyday_region_type":
            problems += self.check_everyday_region(row, only_art=True)
        elif category == "everyday_theme":
            problems += self.check_everyday_theme(row)
        elif category == "everyday_amenity":
            problems += self.check_amenity(row)
        elif category == "everyday_unanswerable":
            problems += self.check_everyday_unanswerable(row)
        return ("v2/" + category, problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evalset", type=Path, default=EVALSET)
    parser.add_argument("--museums", type=Path, default=MUSEUMS)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    verifier = Verifier(read(args.museums))
    rows = read(args.evalset)
    total: Counter[str] = Counter()
    clean: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    flagged: list[dict[str, Any]] = []
    for row in rows:
        group, problems = verifier.verify(row)
        total[group] += 1
        real = [p for p in problems if "건너뜀" not in p]
        if any("건너뜀" in p for p in problems):
            skipped[group] += 1
        if real:
            flagged.append({"question_id": row["question_id"], "종류": group, "질문": row["user_input"],
                            "자동 확인에서 다르게 나온 점": " / ".join(real)})
        elif not any("건너뜀" in p for p in problems):
            clean[group] += 1
    print(f"{'종류':<46}{'문항':>5}{'일치':>6}{'확인필요':>8}{'건너뜀':>6}")
    for group in sorted(total):
        needs = sum(1 for item in flagged if item["종류"] == group)
        print(f"{group:<46}{total[group]:>5}{clean[group]:>6}{needs:>8}{skipped[group]:>6}")
    print(f"합계 {sum(total.values())}문항: 일치 {sum(clean.values())}, 확인 필요 {len(flagged)}, 자동 확인 건너뜀 {sum(skipped.values())}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["question_id", "종류", "질문", "자동 확인에서 다르게 나온 점"])
        writer.writeheader()
        writer.writerows(flagged)
    print("저장:", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
