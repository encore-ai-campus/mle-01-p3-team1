"""Generate a new, source-grounded draft retrieval evaluation set."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_CSV = ROOT / "data" / "processed" / "museum_final_738.csv"
OUTPUT_CSV = ROOT / "evaluations" / "datasets" / "vector_db" / "VectorDB_평가셋_30문항.csv"

# These are replacement draft labels, not a recovery of the deleted original gold set.
CASES = [
    ("Q001", "direct", "박진전쟁기념관에서는 어떤 전투와 관련한 행사·프로그램을 운영하나요?", "yes", "M0001",
     "박진전쟁기념관에서는 6·25전쟁 및 낙동강 돌출부 전투 관련 행사 및 프로그램을 운영하고 있으며,", ""),
    ("Q002", "direct", "창녕박물관에서 어린이박물관을 포함한 교육관은 몇 년에 신축되었나요?", "yes", "M0003",
     "2018년 박물관 리모델링 사업을 통해 어린이박물관을 포함한 교육관을 신축한 후", ""),
    ("Q003", "direct", "인천광역시립박물관은 몇 년에 개관한 최초의 공립박물관인가요?", "yes", "M0004",
     "1946년 개관한 우리나라 최초의 공립박물관이다.", ""),
    ("Q004", "direct", "인천도시역사관의 근대도시관은 개항 이후 어느 시기까지 인천의 형성과 변천을 소개하나요?", "yes", "M0005",
     "근대도시관은 개항(1883년) 이후부터 광복(1945년)까지 도시 인천의 형성과 변천 과정을 소개하고 있으며", ""),
    ("Q005", "direct", "한국이민사박물관은 2003년 어떤 기념으로 개관했나요?", "yes", "M0006",
     "2003년 미주 이민 100주년을 기념해 개관했다.", ""),
    ("Q006", "direct", "거창박물관은 언제 군 단위 최초의 공립박물관으로 개관했나요?", "yes", "M0013",
     "1988년 5월 20일 당시 군 단위 최초로 개관한 공립박물관이다.", ""),
    ("Q007", "direct", "웅천도요지전시관이 소개하는 조선시대 가마에서는 어떤 도자기를 만들었나요?", "yes", "M0015",
     "조선시대 분청사기와 백자 등을 제작하였던 가마터", ""),
    ("Q008", "direct", "창원시립진해박물관 전시실은 진해탑 몇 층에 있나요?", "yes", "M0016",
     "진해탑 1층과 2층에 전시실, 사무실, 시청각실, 유물창고, 전망탑 등의 시설을 갖추고 있다.", ""),
    ("Q009", "semantic", "고려청자와 조선 분청사기·백자를 통해 한국 도자문화의 흐름을 볼 수 있는 미술관은?", "yes", "M0007",
     "고려청자, 조선의 분청사기와 백자 등 시대별 도자기를 통해 한국 도자문화의 흐름을 살펴볼 수 있으며", ""),
    ("Q010", "semantic", "인천 서북부 개발 과정에서 발굴한 선사시대 유물과 청동기 집터를 볼 수 있는 곳은?", "yes", "M0008",
     "청동기시대 집터 및 돌널무덤(석관묘)을 발굴 당시 모습 그대로 이전 설치하였습니다", ""),
    ("Q011", "semantic", "화가의 생가와 초가·연밭·산책로를 함께 둘러볼 수 있는 충남 홍성의 기념관은?", "yes", "M0011",
     "초가로 지은 생가ㆍ연밭ㆍ산책로 등을 갖춘 기념관이자 미술관이다.", ""),
    ("Q012", "semantic", "홍주읍성 안에서 내포 지역의 역사와 유적을 다루는 전시관은?", "yes", "M0012",
     "홍성과 충남 내포지역의 특색 있는 역사와 문화, 관련 유적 및 유물을 소재로 전시를 하고 있다.", ""),
    ("Q013", "semantic", "선사시대부터 근현대까지 지역 출토 유물과 사진으로 마산 지역사를 보여주는 박물관은?", "yes", "M0017",
     "선사시대부터 근현대에 이르기까지 지역의 역사와 문화를 체계적으로 이해할 수 있다.", ""),
    ("Q014", "semantic", "석고 원형 작품과 야외 조각을 볼 수 있는 조각가의 미술관은?", "yes", "M0018",
     "116여 점의 석고원형작품을 소장·전시하고 있다.", ""),
    ("Q015", "semantic", "추사 김정희의 현판·편지 글씨와 지인의 편지를 전시하는 제주 전시관은?", "yes", "M0027",
     "추사 현판 글씨, 추사 편지 글씨, 추사 지인의 편지 글씨 등을 전시하고 있다.", ""),
    ("Q016", "semantic", "물방울 그림으로 알려진 화가의 작품을 볼 수 있는 제주 미술관은?", "yes", "M0029",
     "‘물방울 화가’로 널리 알려진 김창열 화백의 주옥같은 작품을 만나 볼 수 있으며", ""),
    ("Q017", "semantic", "제주 돌하르방 48기의 원형 재현과 여러 조형물을 야외에서 볼 수 있는 곳은?", "yes", "M0031",
     "도 내외에 흩어져 있는 48기의 돌하르방을 원형 그대로 재현해 전시하고 있을 뿐만 아니라", ""),
    ("Q018", "semantic", "김흥수 화백 대표작을 기증받아 전시하는 제주 저지문화예술인마을의 미술관은?", "yes", "M0032",
     "한국 근현대 미술의 거목 김흥수 화백이 자신의 대표 작품을 무상으로 기증한 유일한 미술관이다.", ""),
    ("Q019", "semantic", "폐교된 초등학교를 사진 전시공간으로 활용해 제주의 자연과 민속을 담은 사진을 보여주는 곳은?", "yes", "M0033",
     "폐교된 가시초등학교를 활용해 90평 규모의 넓은 전시 공간을 가진 것이 특징이다.", ""),
    ("Q020", "semantic", "각국의 원두와 커피 도구를 전시하고 사전 신청 바리스타 체험을 운영하는 박물관은?", "yes", "M0037",
     "또한 사전 신청을 통해 바리스타 체험을 할 수 있다.", ""),
    ("Q021", "geo_semantic", "충남 홍성에서 한약방, 조선시대 문화실, 토기·고려청자실과 전통 부엌을 주제별로 보는 박물관은?", "yes", "M0009",
     "한약방ㆍ조선시대 문화실ㆍ한국의 토기-고려청자실ㆍ전통부엌 등의 테마별로 전시되어 있다.", ""),
    ("Q022", "geo_semantic", "제주 서귀포에서 실물 항공기 26대와 우주 전시, 체험관을 함께 볼 수 있는 시설은?", "yes", "M0039",
     "26대의 실물 항공기가 전시된 항공 역사관, 우주를 향한 인류의 끝없는 도전을 알아보는 천문우주관, 오감을 만족시키는 체험공간인 테마관이 있어", ""),
    ("Q023", "geo_semantic", "제주 서귀포에서 유리 블로잉과 캔들 만들기 체험을 할 수 있는 전문 박물관은?", "yes", "M0047",
     "유리블로잉 및 캔들 만들기 등 직접 유리 공예품을 만들 수 있는 체험 프로그램", ""),
    ("Q024", "geo_semantic", "제주에서 조천만세·법정사·해녀 항일운동을 함께 다루는 기념관은?", "yes", "M0056",
     "조천만세운동을 비롯해 법정사 항일운동, 해녀항일운동 등 제주 3대 항일운동과 제주에서 일어난 항일독립운동의 역사를 시대순으로 한눈에 볼 수 있다.", ""),
    ("Q025", "unanswerable", "박진전쟁기념관이 오늘 임시 휴관하는지 실시간으로 확인해줘.", "no", "",
     "", "당일 임시 휴관 여부는 정적 소개 데이터에 없음."),
    ("Q026", "unanswerable", "홍주성역사관의 2025년 연간 관람객 수는 몇 명이야?", "no", "",
     "", "연도별 관람객 통계가 코퍼스에 없음."),
    ("Q027", "unanswerable", "송암미술관에서 다음 달 개막하는 특별전의 제목과 정확한 날짜는?", "no", "",
     "", "미래 특별전 일정과 날짜가 코퍼스에 없음."),
    ("Q028", "unanswerable", "창원시립진해박물관의 장애인 전용 주차면은 몇 면인가요?", "no", "",
     "", "장애인 전용 주차면 수가 코퍼스에 없음."),
    ("Q029", "unanswerable", "제주커피박물관 바움에서 오늘 바리스타 체험을 예약할 수 있는 시간은?", "no", "",
     "", "당일 예약 가능 시간과 잔여 좌석은 코퍼스에 없음."),
    ("Q030", "unanswerable", "제주유리박물관의 다음 유리 공예 체험 일정과 신청 잔여 인원은?", "no", "",
     "", "미래 체험 일정과 신청 잔여 인원은 코퍼스에 없음."),
]


def load_source() -> dict[str, dict[str, str]]:
    if not SOURCE_CSV.is_file():
        raise SystemExit(f"Source CSV not found: {SOURCE_CSV}")
    with SOURCE_CSV.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    return {row["museum_id"]: row for row in rows}


def source_doc_ids(row: dict[str, str], quote: str) -> str:
    start = row["text"].find(quote)
    if start < 0:
        raise ValueError(f"Evidence quote is not present for {row['museum_id']}: {quote}")
    end = start + len(quote)
    spans = json.loads(row["text_spans_json"])
    ids = {
        doc_id
        for span in spans
        if span["start"] < end and span["end"] > start
        for doc_id in span.get("doc_ids", [])
    }
    if not ids:
        raise ValueError(f"No source document IDs cover quote for {row['museum_id']}")
    return ";".join(sorted(ids))


def generate(force: bool = False) -> Path:
    if OUTPUT_CSV.exists() and not force:
        raise SystemExit(
            f"{OUTPUT_CSV.name} already exists. Use --force only when you intend to replace it."
        )

    source = load_source()
    question_ids = [case[0] for case in CASES]
    if len(CASES) != 30 or len(question_ids) != len(set(question_ids)):
        raise ValueError("Expected 30 unique evaluation questions.")
    if sum(case[3] == "yes" for case in CASES) != 24:
        raise ValueError("Expected 24 answerable questions.")

    fields = [
        "question_id",
        "category",
        "question",
        "answerable",
        "gold_museum_ids",
        "gold_museum_names",
        "evidence_quote",
        "evidence_doc_ids",
        "label_status",
        "notes",
    ]
    rows = []
    for question_id, category, question, answerable, museum_id, quote, reason in CASES:
        if answerable == "yes":
            if museum_id not in source:
                raise ValueError(f"Unknown museum_id {museum_id} in {question_id}")
            item = source[museum_id]
            doc_ids = source_doc_ids(item, quote)
            names = item["name"]
            gold_ids = museum_id
            notes = (
                "새로 생성한 초안. evidence_quote와 원문 출처 ID를 연결했으며, "
                "다른 관련 시설도 정답인지 사람이 검수해야 함."
            )
        else:
            doc_ids = ""
            names = ""
            gold_ids = ""
            notes = f"새로 생성한 근거 부족 초안. {reason} 답변 보류 사례로 사람이 검수해야 함."

        rows.append(
            {
                "question_id": question_id,
                "category": category,
                "question": question,
                "answerable": answerable,
                "gold_museum_ids": gold_ids,
                "gold_museum_names": names,
                "evidence_quote": quote,
                "evidence_doc_ids": doc_ids,
                "label_status": "draft_needs_human_review",
                "notes": notes,
            }
        )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} draft questions to {OUTPUT_CSV}")
    print(f"Answerable: {sum(r['answerable'] == 'yes' for r in rows)}")
    print(f"Evidence-insufficient: {sum(r['answerable'] == 'no' for r in rows)}")
    return OUTPUT_CSV


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the existing generated draft CSV.",
    )
    args = parser.parse_args()
    generate(force=args.force)


if __name__ == "__main__":
    main()
