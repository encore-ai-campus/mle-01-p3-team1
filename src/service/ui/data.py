"""데이터 로딩·정제 (대시보드/지도/챗봇 공용)."""
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = PROJECT_ROOT / "data" / "processed" / "museum_final_1027.csv"

SIDO_ALIAS = {
    "전라북도": "전북특별자치도",
    "세종특별시": "세종특별자치시",
}
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
        df["amenities_raw"].fillna("").map(lambda s: [a.strip() for a in s.split("+") if a.strip()])
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
