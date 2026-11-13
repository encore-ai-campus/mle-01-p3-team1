"""지도 탭: 필터 → 지도(클릭 선택) → 선택 박물관 카드."""
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from ui import style as S
from ui.data import clean, fee_text, hours_text, sido_options


def _filters(df: pd.DataFrame) -> pd.DataFrame:
    c1, c2, c3, c4 = st.columns([1.4, 1.4, 1, 1], vertical_alignment="bottom")
    sidos = c1.multiselect("시·도", sido_options(df["sido"]), placeholder="전체 지역")
    owners = c2.multiselect("운영 주체", S.OWNERSHIP_ORDER, placeholder="전체")
    free_only = c3.toggle("무료 관람만")
    barrier_free = c4.toggle("휠체어 이용 가능")
    q = st.text_input("박물관 이름 검색", placeholder="예) 국립중앙박물관", label_visibility="collapsed")

    out = df
    if sidos:
        out = out[out["sido"].isin(sidos)]
    if owners:
        out = out[out["ownership_type"].isin(owners)]
    if free_only:
        out = out[out["is_free"]]
    if barrier_free:
        out = out[out["amenities_raw"].fillna("").str.contains("휠체어")]
    if q:
        out = out[out["name"].str.contains(q, case=False, na=False)]
    return out


def _card(row) -> str:
    img = S.image_block(row["image_url"], 180)
    return (
        f'<div class="card">{img}<div style="margin-top:12px">{S.ownership_chip(row["ownership_type"])}</div>'
        f'<h4 style="margin-top:8px">{escape(row["name"])}</h4>'
        f'<div class="meta">{escape(clean(row["address"], ""))}</div>'
        + S.spec_table([
            ("성인 관람료", fee_text(row["adult_fee"])),
            ("운영 시간", hours_text(row)),
            ("휴관일", clean(row["closure_rule_raw"]).replace("+", ", ")),
        ])
        + "</div>"
    )


def render(df: pd.DataFrame) -> None:
    S.page_header(["Home", "Map"], "MUSEUM MAP", "지역·조건으로 박물관을 찾아보세요")
    filtered = _filters(df).dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    st.caption(f"검색 결과 **{len(filtered):,}곳**")

    left, right = st.columns([2.2, 1], gap="large")
    with left:
        if filtered.empty:
            st.info("조건에 맞는 박물관이 없습니다.")
            return
        fig = px.scatter_map(
            filtered, lat="latitude", lon="longitude", color="ownership_type",
            category_orders={"ownership_type": S.OWNERSHIP_ORDER},
            color_discrete_map=S.OWNERSHIP_COLORS,
            hover_name="name",
            hover_data={"sido": True, "sigungu": True, "latitude": False, "longitude": False, "ownership_type": False},
            custom_data=["museum_id"],
            center=dict(lat=filtered["latitude"].mean(), lon=filtered["longitude"].mean()),
            zoom=6 if len(filtered) > 30 else 9, height=640, map_style="carto-positron",
            labels={"ownership_type": "운영 주체", "sido": "시·도", "sigungu": "시·군·구"},
        )
        fig.update_traces(marker=dict(size=10, opacity=0.9))
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), legend_title_text="")
        event = st.plotly_chart(
            fig, width="stretch", on_select="rerun", selection_mode="points",
            config={"displayModeBar": False, "scrollZoom": True}, key="museum_map",
        )

    with right:
        selected_id = None
        points = (event or {}).get("selection", {}).get("points", []) if event else []
        if points:
            selected_id = points[0].get("customdata", [None])[0]
        if selected_id is None:
            st.caption("지도에서 마커를 클릭하면 상세 정보가 표시됩니다. 아래는 목록 첫 번째 박물관입니다.")
            row = filtered.iloc[0]
        else:
            row = filtered[filtered["museum_id"] == selected_id].iloc[0]
        st.markdown(_card(row), unsafe_allow_html=True)
        hp = row.get("homepage_url")
        if isinstance(hp, str) and hp.startswith("http"):
            st.link_button("홈페이지 방문", hp, width="stretch")

    with st.expander("결과 목록 표로 보기"):
        st.dataframe(
            filtered[["name", "ownership_type", "sido", "sigungu", "adult_fee", "address"]],
            width="stretch", hide_index=True,
        )
