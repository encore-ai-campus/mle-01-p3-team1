"""데이터 로딩·정제 (대시보드/지도/챗봇 공용)."""
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = PROJECT_ROOT / "data" / "museum_final.csv"

# 화면 표시용 시·도 이름 (원본 데이터와 검색 DB 의 값은 바꾸지 않는다)
SIDO_ALIAS = {
    "강원특별자치도": "강원도",
    "전북특별자치도": "전라북도",
    "제주특별자치도": "제주도",
    "세종특별시": "세종특별자치시",
    "전남광주통합특별시": "전라남도",  # 광주 구는 없고 전남 시·군만 이 이름으로 들어와 있다
}
# 시·도 선택 목록 순서: 특별시·광역시 → 도
SIDO_ORDER = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    "세종특별자치시",
    "경기도", "강원도", "충청북도", "충청남도", "전라북도", "전라남도", "경상북도", "경상남도", "제주도",
)


def sido_options(values) -> list[str]:
    """시·도 값을 SIDO_ORDER 순서로 정렬한다. 목록에 없는 이름은 맨 뒤에 가나다순."""
    rank = {name: i for i, name in enumerate(SIDO_ORDER)}
    return sorted(pd.Series(values).dropna().unique(), key=lambda s: (rank.get(s, len(rank)), s))


NO_AMENITY = {"없음", "-", "NAME?", "#NAME?"}  # 편의시설이 아닌 값: 글자 '없음', 엑셀 수식 오류(#NAME?)
FEE_OUTLIER = 100_000  # 이 이상은 입력 오류로 보고 결측 처리


@st.cache_data(show_spinner=False)
def load_museums() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    # 같은 박물관이 출처별로 여러 행 → museum_id 기준 1행
    df = df.drop_duplicates(subset="museum_id", keep="first").reset_index(drop=True)
    df["sido"] = df["sido"].replace(SIDO_ALIAS)
    for col in ("adult_fee", "youth_fee", "child_fee"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] >= FEE_OUTLIER, col] = pd.NA
    df["is_free"] = df["adult_fee"].fillna(-1).eq(0)
    df["amenity_list"] = (
        df["amenities_raw"].fillna("").map(
            lambda s: [a.strip() for a in s.split("+") if a.strip() and a.strip() not in NO_AMENITY]
        )
    )
    df["description"] = df["description"].fillna(df["text"])
    df["image_url"] = df["image_url"].where(df["image_url"].astype(str).str.startswith("http"))
    return df


def fee_text(v) -> str:
    if pd.isna(v):
        return "정보 없음"
    return "무료" if v == 0 else f"{int(v):,}원"


def hours_text(row) -> str:
    o, c = row.get("weekday_open"), row.get("weekday_close")
    if pd.isna(o) or pd.isna(c):
        return "정보 없음"
    return f"{o} – {c}"


def clean(v, default: str = "정보 없음") -> str:
    return default if pd.isna(v) or str(v).strip() == "" else str(v)
