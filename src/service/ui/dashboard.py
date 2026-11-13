"""대시보드 탭: KPI · 분포 차트 · 박물관 상세(상품 상세 페이지 레이아웃)."""
from collections import Counter
from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui import style as S
from ui.data import clean, fee_text, hours_text, sido_options


def _kpis(df: pd.DataFrame) -> None:
    paid = df.loc[df["adult_fee"] > 0, "adult_fee"]
    cols = st.columns(4, gap="medium")
    cards = [
        S.kpi("등록 박물관", f"{len(df):,}", f"{df['sido'].nunique()}개 시·도", accent=True),
        S.kpi("무료 관람", f"{df['is_free'].mean():.0%}", f"{int(df['is_free'].sum()):,}곳 (성인 기준)"),
        S.kpi("유료 평균 관람료", f"{paid.mean():,.0f}원" if len(paid) else "-", f"중앙값 {paid.median():,.0f}원" if len(paid) else ""),
        S.kpi("이미지 보유", f"{df['image_url'].notna().mean():.0%}", "TourAPI 대표 이미지"),
    ]
    for c, html in zip(cols, cards):
        c.markdown(html, unsafe_allow_html=True)


def _sido_chart(df: pd.DataFrame) -> go.Figure:
    counts = df["sido"].value_counts().sort_values()
    fig = go.Figure(
        go.Bar(
            x=counts.values, y=counts.index, orientation="h",
            marker=dict(color=S.BAR_GREEN, cornerradius=4),
            text=counts.values, textposition="outside", textfont=dict(color=S.MUTED, size=11), cliponaxis=False,
            hovertemplate="%{y}: %{x}곳<extra></extra>",
        )
    )
    fig.update_layout(title=S.chart_title("시·도별 박물관 수"), height=560, margin=dict(l=8, r=36, t=60, b=8), xaxis=dict(showgrid=True), yaxis=dict(showgrid=False))
    return fig


def _ownership_chart(df: pd.DataFrame) -> go.Figure:
    counts = df["ownership_type"].value_counts().reindex(S.OWNERSHIP_ORDER).dropna()
    fig = go.Figure(
        go.Pie(
            labels=counts.index, values=counts.values, hole=0.62, sort=False,
            marker=dict(colors=[S.OWNERSHIP_COLORS[k] for k in counts.index], line=dict(color=S.COCONUT, width=2)),
            textinfo="label+percent", textposition="auto", insidetextorientation="horizontal",
            insidetextfont=dict(color=[S.text_on(S.OWNERSHIP_COLORS[k]) for k in counts.index], size=13), outsidetextfont=dict(color=S.NAVY, size=13),
            hovertemplate="%{label}: %{value}곳 (%{percent})<extra></extra>", automargin=True,
        )
    )
    fig.update_layout(
        title=S.chart_title("운영 주체"), height=310, margin=dict(l=8, r=8, t=90, b=16), showlegend=False,
        annotations=[dict(text=f"<b>{int(counts.sum())}</b><br>곳", showarrow=False, font=dict(size=16, color=S.NAVY))],
    )
    return fig


def _fee_chart(df: pd.DataFrame) -> go.Figure:
    bins = [-1, 0, 2000, 5000, 10000, 1e9]
    labels = ["무료", "~2천원", "~5천원", "~1만원", "1만원 초과"]
    cat = pd.cut(df["adult_fee"].dropna(), bins=bins, labels=labels)
    counts = cat.value_counts().reindex(labels)
    fig = go.Figure(
        go.Bar(
            x=counts.index, y=counts.values, marker=dict(color=S.ACCENT, cornerradius=4),
            text=counts.values, textposition="outside", textfont=dict(color=S.MUTED, size=11), cliponaxis=False,
            hovertemplate="%{x}: %{y}곳<extra></extra>",
        )
    )
    fig.update_layout(title=S.chart_title("성인 관람료 분포"), height=250, margin=dict(l=8, r=8, t=60, b=8), yaxis=dict(showgrid=True), xaxis=dict(showgrid=False))
    return fig


def _amenity_chart(df: pd.DataFrame) -> go.Figure:
    c = Counter(a for lst in df["amenity_list"] for a in lst)
    top = pd.Series(dict(c.most_common(6))).sort_values()
    fig = go.Figure(
        go.Bar(
            x=top.values, y=top.index, orientation="h", marker=dict(color=S.BAR_COCOA, cornerradius=4),
            text=top.values, textposition="outside", textfont=dict(color=S.MUTED, size=11), cliponaxis=False,
            hovertemplate="%{y}: %{x}곳<extra></extra>",
        )
    )
    fig.update_layout(title=S.chart_title("편의시설 보유 현황"), height=270, margin=dict(l=8, r=36, t=60, b=8), yaxis=dict(showgrid=False))
    return fig


def _detail(df: pd.DataFrame) -> None:
    S.section("박물관 상세")
    f1, f2 = st.columns([1, 2])
    sido = f1.selectbox("시·도", ["전체"] + sido_options(df["sido"]), key="dash_sido")
    pool = df if sido == "전체" else df[df["sido"] == sido]
    pool = pool.sort_values(["image_url"], na_position="last")
    name = f2.selectbox("박물관", pool["name"].tolist(), key="dash_museum")
    row = pool[pool["name"] == name].iloc[0]

    S.page_header(["Home", "대시보드", clean(row["sido"]), row["name"]], row["name"], clean(row["address"], ""))

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(S.image_block(row["image_url"], 340), unsafe_allow_html=True)
        st.write("")
        t1, t2, t3 = st.columns(3)
        tiles = [
            ("성인", row["adult_fee"], S.BAR_GREEN, S.NAVY),
            ("청소년", row["youth_fee"], S.RESEDA, S.NAVY),
            ("어린이", row["child_fee"], S.PASTEL_YELLOW, S.NAVY),
        ]
        for col, (k, v, bg, fg) in zip((t1, t2, t3), tiles):
            col.markdown(
                f'<div class="tile" style="background:{bg};color:{fg}"><div class="k">{k} 관람료</div>'
                f'<div class="v">{fee_text(v)}</div></div>',
                unsafe_allow_html=True,
            )
    with right:
        desc = escape(clean(row["description"], "소개 정보가 없습니다."))
        short = desc if len(desc) < 260 else desc[:260].rsplit(" ", 1)[0] + " …"
        st.markdown(
            f'{S.ownership_chip(row["ownership_type"])}'
            f'<div class="prod-name" style="margin-top:10px">{escape(row["name"])}</div>'
            f'<div class="prod-price">{fee_text(row["adult_fee"])}</div>'
            f'<div class="prod-desc">{short}</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        b1, b2 = st.columns(2)
        hp = row.get("homepage_url")
        if isinstance(hp, str) and hp.startswith("http"):
            b1.link_button("홈페이지", hp, width="stretch")
        if b2.button("챗봇에게 물어보기", type="primary", width="stretch", key="dash_ask"):
            st.session_state["chat_prefill"] = f"{row['name']} 관람 정보와 주변에 함께 가볼 곳 알려줘"
            st.toast("챗봇 탭에 답변을 준비했어요.")
        st.markdown(
            S.spec_table([
                ("운영 주체", clean(row["ownership_type"])),
                ("운영 시간", hours_text(row)),
                ("휴관일", clean(row["closure_rule_raw"]).replace("+", ", ")),
                ("운영 기관", clean(row["operator_name"])),
            ]),
            unsafe_allow_html=True,
        )

    d1, d2 = st.columns([1.15, 1], gap="large")
    with d1:
        S.section("Description")
        st.markdown(f'<div class="prod-desc">{desc}</div>', unsafe_allow_html=True)
        S.section("편의시설 · 교통")
        chips = "".join(f'<span class="chip">{escape(a)}</span>' for a in row["amenity_list"]) or '<span class="chip">정보 없음</span>'
        st.markdown(chips, unsafe_allow_html=True)
        st.markdown(f'<div class="prod-desc" style="margin-top:12px">{escape(clean(row["transport_notes"], "교통 안내 정보가 없습니다."))}</div>', unsafe_allow_html=True)
    with d2:
        st.write("")
        if pd.notna(row["latitude"]):
            fig = px.scatter_map(
                pd.DataFrame([row]), lat="latitude", lon="longitude", hover_name="name",
                center=dict(lat=row["latitude"], lon=row["longitude"]), zoom=13, height=340, map_style=S.MAP_STYLE,
            )
            fig.update_traces(marker=dict(size=16, color=S.ACCENT))
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render(df: pd.DataFrame) -> None:
    S.page_header(["Home", "Dashboard"], "MUSEUM DASHBOARD", "전국 박물관 데이터 한눈에 보기")
    _kpis(df)
    st.write("")
    st.write("")
    c1, c2 = st.columns([1, 1.25], gap="large")
    with c1:
        st.plotly_chart(_sido_chart(df), width="stretch", config={"displayModeBar": False})
    with c2:
        st.plotly_chart(_ownership_chart(df), width="stretch", config={"displayModeBar": False})
        st.plotly_chart(_fee_chart(df), width="stretch", config={"displayModeBar": False})
    st.plotly_chart(_amenity_chart(df), width="stretch", config={"displayModeBar": False})
    with st.expander("데이터 표로 보기"):
        st.dataframe(
            df[["name", "ownership_type", "sido", "sigungu", "adult_fee", "weekday_open", "weekday_close"]],
            width="stretch", hide_index=True,
        )
    st.divider()
    _detail(df)
