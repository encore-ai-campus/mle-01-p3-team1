"""대시보드 탭: KPI · 분포 차트 · 박물관 상세(상품 상세 페이지 레이아웃)."""
import re
from collections import Counter
from html import escape
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import nav
from ui import style as S
from ui.data import clean, fee_text, hours_text, sido_options



def _person_svg(height: int) -> str:
    """사람 실루엣 (머리 + 몸통). 키로 성인·청소년·어린이를 구분."""
    w = round(height * 0.62)
    return (
        f'<svg width="{w}" height="{height}" viewBox="0 0 20 32" fill="currentColor" aria-hidden="true">'
        '<circle cx="10" cy="6" r="5.5"/><path d="M1 32v-9a9 9 0 0 1 18 0v9z"/></svg>'
    )


# 교통 안내는 '+' 로 잇거나 '…도보 10분- 일반버스 …' 처럼 '- ' 로 이어 쓴 경우가 섞여 있다
_TRANSIT_SPLIT = re.compile(r"\+|(?:^|(?<=[^\s\d]))\s*-\s+")


_BUS_NO = re.compile(r"^[가-힣]{0,3}\d{1,4}(-\d{1,2})?(번)?$")  # 204, 410-1, 급행2, 북구2, 순환2번


def _transit_lines(raw: str) -> list[str]:
    """교통 안내를 줄 목록으로. 연달아 나오는 버스 번호는 '버스 204 · 304 · 급행2' 한 줄로 묶는다."""
    raw = re.sub(r"\(([^)]*)\)", lambda m: "(" + m.group(1).replace("+", ", ") + ")", raw)  # 괄호 안 '+' 는 구분자가 아님
    lines, buses = [], []
    for part in (t.strip(" -·•") for t in _TRANSIT_SPLIT.split(raw)):
        if not part:
            continue
        if _BUS_NO.match(part):
            buses.append(part)
            continue
        if buses:
            lines.append("버스 " + " · ".join(buses))
            buses = []
        lines.append(part)
    if buses:
        lines.append("버스 " + " · ".join(buses))
    return lines


def _fee_note(v) -> str:
    if pd.isna(v):
        return "현장에서 확인해 주세요"
    return "입장료 없음" if v == 0 else "1인 기준"

def _kpis(df: pd.DataFrame) -> None:
    paid = df.loc[df["adult_fee"] > 0, "adult_fee"]
    cols = st.columns(4, gap="medium")
    cards = [
        S.kpi("등록 박물관", f"{len(df):,}", f"{df['sido'].nunique()}개 시·도", accent=True),
        S.kpi("무료 관람", f"{df['is_free'].mean():.0%}", f"{int(df['is_free'].sum()):,}곳 (성인 기준)"),
        S.kpi("유료 평균 관람료", f"{paid.mean():,.0f}원" if len(paid) else "-", f"중앙값 {paid.median():,.0f}원" if len(paid) else ""),
        _night_kpi(df),
    ]
    for c, html in zip(cols, cards):
        c.markdown(html, unsafe_allow_html=True)


NEARBY_K = 6  # 목록 6줄이 오른쪽 정보 표 + 지도 높이와 맞음 (줄 47px 기준 실측)


def _go_museum(name: str, sido: str) -> None:
    """가까운 박물관 카드 → 대시보드 상세를 그 박물관으로 (버튼 on_click 콜백)."""
    st.session_state["dash_sido"] = sido
    st.session_state["dash_museum"] = name


def _nearest(df: pd.DataFrame, row) -> pd.DataFrame:
    """좌표 기준 직선거리로 가장 가까운 박물관 NEARBY_K곳 (좌표는 738곳 모두 있음). km 열 추가."""
    if pd.isna(row["latitude"]):
        return df.iloc[0:0].assign(km=[])
    others = df[(df["museum_id"] != row["museum_id"]) & df["latitude"].notna()]
    lat1, lon1 = np.radians(row["latitude"]), np.radians(row["longitude"])
    lat2, lon2 = np.radians(others["latitude"]), np.radians(others["longitude"])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return others.assign(km=6371 * 2 * np.arcsin(np.sqrt(a))).nsmallest(NEARBY_K, "km")


def _nearby_list(near: pd.DataFrame) -> None:
    """가까운 박물관 목록: 오른쪽 정보 표처럼 구분선 있는 한 줄씩. 줄 전체가 버튼(누르면 그 박물관으로)."""
    if near.empty:
        return
    S.section("가까운 박물관")
    st.markdown('<div class="muted-note">직선거리 기준 · 클릭 시 이동</div>', unsafe_allow_html=True)
    # 줄 오른쪽의 '거리 · 관람료 →' 는 버튼 글자가 아니라 CSS ::after 로 붙인다 (이름은 왼쪽, 정보는 오른쪽 정렬)
    meta_css = "".join(
        f'.st-key-near_{m["museum_id"]} button::after {{ content: "{m["km"]:.1f}km · {fee_text(m["adult_fee"])}   →"; }}'
        for _, m in near.iterrows()
    )
    st.html(f"<style>{meta_css}</style>")
    with st.container(key="dash_nearby"):
        for _, m in near.iterrows():
            st.button(m["name"], key=f"near_{m['museum_id']}", width="stretch",
                      on_click=_go_museum, args=(m["name"], m["sido"]))


def _fit_zoom(lats: list[float], lons: list[float], width_px: int = 420, height_px: int = 230, pad: float = 1.6) -> float:
    """모든 점이 여백(pad 배)을 두고 지도 안에 들어오는 확대 수준 (웹 메르카토르, MapLibre 타일 512px 기준)."""
    lat_span = max(max(lats) - min(lats), 0.002) * pad
    lon_span = max(max(lons) - min(lons), 0.002) * pad
    mid = np.radians((max(lats) + min(lats)) / 2)
    z_lon = np.log2(width_px * 360 / (512 * lon_span))
    z_lat = np.log2(height_px * 360 * np.cos(mid) / (512 * lat_span))
    return float(np.clip(min(z_lon, z_lat), 6, 15))


def _location_map(row, near: pd.DataFrame) -> None:
    """위치 지도: 보고 있는 곳(진한 점) + 가까운 곳들(연한 점). 모두 보이게 범위를 맞춘다."""
    if pd.isna(row["latitude"]):
        return
    lats = [row["latitude"], *near["latitude"]]
    lons = [row["longitude"], *near["longitude"]]
    zoom = _fit_zoom(lats, lons)
    fig = go.Figure([
        go.Scattermap(
            lat=near["latitude"], lon=near["longitude"], mode="markers", name="가까운 곳",
            marker=dict(size=12, color=S.POWDER_BLUE, opacity=0.95),
            text=[f"{n} · {k:.1f}km" for n, k in zip(near["name"], near["km"])], hoverinfo="text",
        ),
        go.Scattermap(
            lat=[row["latitude"]], lon=[row["longitude"]], mode="markers", name="보고 있는 곳",
            marker=dict(size=16, color=S.ACCENT), text=[row["name"]], hoverinfo="text",
        ),
    ])
    fig.update_layout(
        map=dict(style=S.MAP_STYLE, center=dict(lat=(min(lats) + max(lats)) / 2, lon=(min(lons) + max(lons)) / 2), zoom=zoom),
        height=230, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.markdown(
        f'<div class="map-legend"><span style="background:{S.ACCENT}"></span>보고 있는 곳'
        f'<span style="background:{S.POWDER_BLUE}"></span>가까운 곳</div>',
        unsafe_allow_html=True,
    )


NIGHT_HOUR = 19  # 평일 이 시각 이후까지 여는 곳 = 야간 관람


def _night_kpi(df: pd.DataFrame) -> str:
    close = pd.to_datetime(df["weekday_close"], format="%H:%M", errors="coerce")
    night = close.dt.hour >= NIGHT_HOUR
    if not night.any():
        return S.kpi("야간 관람", "0곳", f"평일 {NIGHT_HOUR}시 이후 운영")
    latest = df.loc[close.idxmax()]
    return S.kpi("야간 관람", f"{int(night.sum()):,}곳", f"최장 {close.max():%H}시 · {latest['name']}")


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
    # 정보가 많은 곳부터: 사진+편의시설 → 사진만 → 편의시설만 → 둘 다 없음 (같은 그룹 안에서는 기존 순서 유지)
    info = pool["image_url"].notna().astype(int) * 2 + pool["amenity_list"].map(bool).astype(int)
    pool = pool.assign(_info=info).sort_values("_info", ascending=False, kind="stable")
    name = f2.selectbox("박물관", pool["name"].tolist(), key="dash_museum")
    row = pool[pool["name"] == name].iloc[0]

    S.page_header(["Home", "대시보드", clean(row["sido"]), row["name"]], row["name"], clean(row["address"], ""))

    near = _nearest(df, row)
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown(S.image_block(row["image_url"], 340), unsafe_allow_html=True)
        st.write("")
        t1, t2, t3 = st.columns(3)
        tiles = [  # (구분, 금액, 배경, 글자, 사람 아이콘 키 px)
            ("성인", row["adult_fee"], S.BAR_GREEN, S.NAVY, 26),
            ("청소년", row["youth_fee"], S.RESEDA, S.NAVY, 21),
            ("어린이", row["child_fee"], S.PASTEL_YELLOW, S.NAVY, 16),
        ]
        for col, (k, v, bg, fg, h) in zip((t1, t2, t3), tiles):
            col.markdown(
                f'<div class="ticket" style="background:{bg};color:{fg}">'
                f'<div class="top"><div class="k">{k} 관람료</div><div class="who">{_person_svg(h)}</div></div>'
                f'<div class="bottom"><div class="v">{fee_text(v)}</div><div class="s">{_fee_note(v)}</div></div></div>',
                unsafe_allow_html=True,
            )
        _nearby_list(near)
    with right:
        desc = escape(clean(row["description"], "소개 정보가 없습니다."))
        # 소개는 4줄만 보이고 '더 보기'로 펼친다 (아래 Description 칸과 겹치던 글을 한 곳으로)
        body = f'<div class="prod-desc clamp">{desc}</div>'
        if len(desc) > 180:
            body = f'<details class="more"><summary>{body}<span class="more-btn"></span></summary></details>'
        st.markdown(
            f'{S.ownership_chip(row["ownership_type"])}'
            f'<div class="prod-name" style="margin-top:10px">{escape(row["name"])}</div>'
            f'<div class="prod-price">{fee_text(row["adult_fee"])}</div>{body}',
            unsafe_allow_html=True,
        )
        st.write("")
        b1, b2 = st.columns(2)
        hp = row.get("homepage_url")
        if isinstance(hp, str) and hp.startswith("http"):
            b1.link_button("홈페이지", hp, width="stretch")
        b2.button(
            "챗봇에게 물어보기", type="primary", width="stretch", key="dash_ask",
            on_click=nav.ask_chatbot, args=(f"{row['name']} 관람 정보와 주변에 함께 가볼 곳 알려줘",),
        )
        st.markdown(
            S.spec_table([
                ("운영 주체", clean(row["ownership_type"])),
                ("운영 시간", hours_text(row)),
                ("휴관일", clean(row["closure_rule_raw"]).replace("+", ", ")),
                ("운영 기관", clean(row["operator_name"])),
            ]),
            unsafe_allow_html=True,
        )
        # 위치 지도: 정보 표 아래. 가까운 박물관들도 연한 점으로 함께 표시
        st.write("")
        _location_map(row, near)

    S.section("편의시설 · 교통")
    # 편의시설은 46%, 교통은 51% 박물관에만 있다 → 없을 때는 안내 문구 + 길찾기(좌표는 모두 있음)
    if row["amenity_list"]:
        st.markdown("".join(f'<span class="chip">{escape(a)}</span>' for a in row["amenity_list"]), unsafe_allow_html=True)
    else:
        st.markdown('<div class="muted-note">등록된 편의시설 정보가 없어요.</div>', unsafe_allow_html=True)
    transit = _transit_lines(clean(row["transport_notes"], ""))
    if transit:
        st.markdown('<ul class="transit">' + "".join(f"<li>{escape(t)}</li>" for t in transit) + "</ul>", unsafe_allow_html=True)
    else:
        st.markdown('<div class="muted-note">교통 안내 정보가 없어요. 길찾기로 확인해 보세요.</div>', unsafe_allow_html=True)
    if pd.notna(row["latitude"]):
        url = f"https://map.kakao.com/link/to/{quote(str(row['name']))},{row['latitude']},{row['longitude']}"
        st.container(key="dash_route").link_button("카카오맵 길찾기", url)  # 모양: style.py .st-key-dash_route


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
