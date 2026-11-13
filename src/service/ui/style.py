"""팔레트·전역 CSS·공용 HTML 조각."""
from html import escape

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ── 첨부 팔레트 (Pantone) ─────────────────────────────
RED_INFERNO = "#4E0000"
PASTEL_YELLOW = "#F2E6B1"
RESEDA = "#A1AD92"
CHIVE = "#4B5335"
POWDER_BLUE = "#94B2C4"
NAVY = "#00263E"
COCOA = "#594536"
COCONUT = "#F0EDE5"

FONT_URL = "app/static/fonts"
MAP_STYLE = "carto-voyager"  # 지도 바탕 (물·공원·도로에 옅은 색이 들어간 부드러운 컬러 지도)
HEAD_FONT = '"IBM Plex Sans KR", "Apple SD Gothic Neo", sans-serif'   # 제목 (굵기로 위계 구분)
BODY_FONT = '"IBM Plex Sans KR", "Apple SD Gothic Neo", sans-serif'   # 본문

SURFACE = "#FAF8F3"      # 카드 배경
PLACEHOLDER = "#E4DED0"  # 이미지 자리(와이어프레임 회색 블록)
LINE = "#D8D1C1"
MUTED = "#5E6B73"

# 차트 색: 팔레트 톤을 유지한 채 채도를 낮춘 버전 (색각 이상 구분 검증 통과, 라벨 항상 표기)
OWNERSHIP_ORDER = ["공립", "사립", "국립", "대학"]
OWNERSHIP_COLORS = {
    "공립": "#B5675F",  # Red Inferno 계열
    "사립": "#7FA6C0",  # Powder Blue 계열
    "국립": "#C8AA55",  # Pastel Yellow 계열
    "대학": "#4A6680",  # Navy 계열
}
ACCENT = "#A8625B"     # KPI 강조 박스 = 관람료 차트 막대
BAR_GREEN = "#8F9C78"  # 시·도별 막대 (Chive/Reseda 사이)
BAR_COCOA = "#9C8371"  # 편의시설 막대 (Cocoa 연하게)
SERIES = [ACCENT, "#7FA6C0", "#C8AA55", "#4A6680", BAR_GREEN, BAR_COCOA, RESEDA]


def text_on(bg: str) -> str:
    """배경색 위에 올릴 글자색(흰색 또는 네이비)."""
    r, g, b = (int(bg.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#FFFFFF" if lum < 0.42 else NAVY


def chart_title(text: str) -> dict:
    """차트 소제목: 왼쪽 정렬, 크게."""
    return dict(text=text, x=0, xref="container", xanchor="left", pad=dict(l=6), font=dict(family=HEAD_FONT, size=21, weight=700, color=NAVY))



def _register_plotly_template() -> None:
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family=BODY_FONT, color=NAVY, size=13),
        title=dict(font=dict(family=HEAD_FONT, size=21, color=NAVY), x=0, xref="paper", pad=dict(b=10)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        margin=dict(l=8, r=8, t=60, b=8),
        xaxis=dict(gridcolor=LINE, zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED, size=13)),
        yaxis=dict(gridcolor=LINE, zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED, size=13)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE, font=dict(color=NAVY)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=NAVY)),
        bargap=0.25,
    )
    pio.templates["museum"] = tpl
    pio.templates.default = "museum"


_register_plotly_template()


CSS = f"""
<style>
/* 나눔 글꼴 @font-face 는 .streamlit/config.toml 의 [[theme.fontFaces]] 에서 등록 */
:root {{
  --red: {RED_INFERNO}; --yellow: {PASTEL_YELLOW}; --reseda: {RESEDA}; --chive: {CHIVE};
  --accent: {ACCENT}; --powder: {POWDER_BLUE}; --navy: {NAVY}; --cocoa: {COCOA}; --coconut: {COCONUT};
  --surface: {SURFACE}; --ph: {PLACEHOLDER}; --line: {LINE}; --muted: {MUTED};
  --font-head: {HEAD_FONT};
  --font-body: {BODY_FONT};
}}
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea {{
  font-family: var(--font-body) !important;
}}
.stApp {{ background: var(--coconut); }}
header[data-testid="stHeader"] {{ display: none; }}
.block-container {{ padding-top: 0 !important; max-width: 1180px; }}
#MainMenu, footer {{ visibility: hidden; }}

/* ── 상단 네비게이션 바 ── */
.topbar {{
  display:flex; align-items:center; justify-content:space-between;
  padding: 18px 4px 14px; border-bottom: 1px solid var(--line); margin-bottom: 0;
}}
.brand {{ font-family:var(--font-head); font-weight:700; font-size:26px; letter-spacing:0; color:var(--navy); }}
.brand span {{ color: var(--red); }}

/* ── 탭 = 가운데 정렬 네비 링크 (Streamlit 1.67: react-aria 구조) ── */
.stTabs [role="tablist"] {{
  justify-content:center; gap: 40px; border-bottom: 1px solid var(--line); margin-bottom: 8px;
}}
.stTabs [data-testid="stTab"] {{ background: transparent; padding: 12px 2px; }}
.stTabs [data-testid="stTab"] p {{
  font-family:var(--font-head); font-size: 13px; letter-spacing: 1.6px;
  text-transform: uppercase; color: var(--muted); font-weight:500;
}}
.stTabs [data-testid="stTab"]:hover p {{ color: var(--navy); }}
.stTabs [data-testid="stTab"][aria-selected="true"] p {{ color: var(--red); font-weight:600; }}
.stTabs .react-aria-SelectionIndicator {{ background: var(--red) !important; height: 2px !important; }}
/* 탭 안의 탭은 왼쪽 정렬 */
.stTabs .stTabs [role="tablist"] {{ justify-content:flex-start; gap: 26px; }}
/* ── 브레드크럼 & 페이지 타이틀 ── */
.crumb {{ font-size:12px; color:var(--muted); margin: 28px 0 14px; font-weight:400; }}
.crumb b {{ color: var(--navy); font-weight:600; }}
.crumb .sep {{ margin: 0 8px; opacity:.6; }}
.page-title {{
  text-align:center; font-family:var(--font-head); font-weight:700;
  font-size: 44px; font-weight:700; letter-spacing: 0; color: var(--navy); margin: 0 0 12px; line-height:1.2;
}}
.page-sub {{ text-align:center; color: var(--muted); font-size:15px; font-weight:400; margin-bottom: 44px; }}

/* ── 섹션 제목 ── */
.section-h {{ font-family:var(--font-head); font-size:22px; font-weight:700; letter-spacing:0; color:var(--navy); margin: 40px 0 14px; }}
.label {{ font-family:var(--font-head); font-size:15px; font-weight:600; color:var(--navy); margin: 4px 0 10px; }}

/* ── 상품 상세형 정보 블록 ── */
.prod-name {{ font-family:var(--font-head); font-size:26px; font-weight:700; letter-spacing:0; color:var(--navy); margin-bottom:4px; }}
.prod-price {{ font-size:22px; font-weight:500; color:var(--navy); margin: 8px 0 18px; }}
.prod-desc {{ font-size:15px; font-weight:400; line-height:1.8; color:#33444F; }}
.spec {{ width:100%; border-collapse:collapse; margin-top:14px; }}
.spec, .spec tr {{ border:none !important; background:transparent !important; }}
.spec td {{ border-left:none !important; border-right:none !important; border-top:none !important; padding: 12px 0; font-size:14px; border-bottom: 1px solid var(--line); vertical-align:top; }}
.spec td:first-child {{ font-weight:600; color:var(--navy); width:34%; }}
.spec td:last-child {{ text-align:right; color: var(--muted); }}

/* ── 이미지 / 플레이스홀더 ── */
.ph {{ background: var(--ph); border-radius: 2px; width:100%; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:13px; overflow:hidden; }}
.ph img {{ width:100%; height:100%; object-fit:cover; }}
.tile {{ border-radius:2px; padding: 16px 14px; height: 120px; display:flex; flex-direction:column; justify-content:space-between; }}
.tile .k {{ font-size:12px; letter-spacing:1px; opacity:.85; }}
.tile .v {{ font-size:22px; font-weight:700; }}

/* ── KPI 카드 ── */
.kpi {{ background: var(--surface); border:1px solid var(--line); border-radius: 6px; padding: 24px 26px; }}
.kpi .k {{ font-size:13px; font-weight:500; color:var(--muted); margin-bottom: 12px; }}
.kpi .v {{ font-family:var(--font-head); font-size:34px; font-weight:500; letter-spacing:0; color:var(--navy); line-height:1.1; margin-bottom: 10px; }}
.kpi .s {{ font-size:13px; font-weight:400; color:var(--muted); }}
.kpi.accent {{ background: var(--accent); border-color: var(--accent); }}
.kpi.accent .k, .kpi.accent .s {{ color: #FFFFFF; opacity:.92; }}
.kpi.accent .v {{ color: #FFFFFF; }}

/* ── 카드 / 칩 ── */
.card {{ background: var(--surface); border:1px solid var(--line); border-radius:4px; padding:16px 18px; margin-bottom:10px; }}
.card h4 {{ font-family:var(--font-head); font-weight:700; margin:0 0 6px; font-size:17px; color:var(--navy); }}
.card .meta {{ font-size:12px; color:var(--muted); }}
.chip {{ display:inline-block; font-size:11px; padding:3px 10px; border-radius:999px; margin: 6px 6px 0 0; border:1px solid var(--line); color:var(--navy); background:var(--coconut); }}
.chip.solid {{ border-color: transparent; }}
.status {{ display:inline-flex; align-items:center; gap:8px; font-size:13px; padding:6px 12px; border-radius:999px; }}
.status.ok {{ background:#E3EAD8; color:#2F4A16; }}
.status.off {{ background:#F1DCDC; color:var(--red); }}

/* ── 버튼: 알약형 ── */
.stButton > button, .stLinkButton > a, .stFormSubmitButton > button {{
  border-radius: 999px !important; padding: 6px 22px !important; font-weight:600;
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: var(--red) !important; border-color: var(--red) !important; color: var(--coconut) !important;
}}
.stButton > button[kind="secondary"] {{ background: transparent; border:1px solid var(--line); color: var(--navy); }}

/* ── 입력 위젯 ── */
[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea {{
  background: var(--surface) !important;
}}
/* 채팅 입력: 바깥 박스 색은 유지하고, 글자 뒤 흰 배경만 투명 처리 */
[data-testid="stChatInput"] textarea {{
  background: transparent !important;
}}
[data-baseweb="tag"] {{ background: var(--navy) !important; }}

/* ── 채팅 ── */
[data-testid="stChatMessage"] {{ background: var(--surface); border:1px solid var(--line); border-radius: 6px; padding: 20px 22px; margin-bottom: 12px; }}
[data-testid="stChatInput"] {{ border-color: var(--line) !important; }}

/* ── 사이드바 ── */
section[data-testid="stSidebar"] {{ background: var(--navy); }}
section[data-testid="stSidebar"] * {{ color: var(--coconut) !important; }}

hr {{ border-color: var(--line) !important; }}
h1, h2, h3, h4, h5, h6 {{ font-family: var(--font-head) !important; }}
@media (max-width: 760px) {{
  .page-title {{ font-size: 32px; }}
  .stTabs [role="tablist"] {{ gap: 16px; }}
}}
</style>
"""


def inject_css() -> None:
    # style 만 담긴 st.html 은 화면 공간을 차지하지 않고 전역 CSS 로 적용된다
    st.html(CSS)


def topbar(brand_left: str, brand_right: str) -> None:
    st.markdown(
        f"""<div class="topbar">
              <div class="brand">{escape(brand_left)}<span>{escape(brand_right)}</span></div>
            </div>""",
        unsafe_allow_html=True,
    )


def page_header(crumbs: list[str], title: str, subtitle: str = "") -> None:
    parts = [escape(c) for c in crumbs[:-1]] + [f"<b>{escape(crumbs[-1])}</b>"]
    crumb_html = '<span class="sep">›</span>'.join(parts)
    sub = f'<div class="page-sub">{escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f'<div class="crumb">{crumb_html}</div><div class="page-title">{escape(title)}</div>{sub}',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown(f'<div class="section-h">{escape(title)}</div>', unsafe_allow_html=True)


def label(text: str) -> None:
    """작은 굵은 소제목 (표·답변 위 라벨)."""
    st.markdown(f'<div class="label">{escape(text)}</div>', unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", accent: bool = False) -> str:
    cls = "kpi accent" if accent else "kpi"
    return (
        f'<div class="{cls}"><div class="k">{escape(label)}</div>'
        f'<div class="v">{escape(value)}</div><div class="s">{escape(sub)}</div></div>'
    )


def spec_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in rows)
    return f'<table class="spec">{body}</table>'


def image_block(url, height: int, label: str = "이미지 없음") -> str:
    # 이미지가 없는 행은 NaN(float) 이라 `if url` 이 참이 됨 → 문자열인지 직접 확인
    has_img = isinstance(url, str) and url.startswith("http")
    inner = f'<img src="{escape(url)}" alt="">' if has_img else escape(label)
    return f'<div class="ph" style="height:{height}px">{inner}</div>'


def ownership_chip(kind: str) -> str:
    color = OWNERSHIP_COLORS.get(kind, MUTED)
    return f'<span class="chip solid" style="background:{color};color:{text_on(color)}">{escape(kind)}</span>'
