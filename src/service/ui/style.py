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
        # fixedrange: 드래그로 확대되지 않게 (실수로 끌면 되돌릴 버튼이 없어서)
        xaxis=dict(gridcolor=LINE, zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED, size=13), fixedrange=True),
        yaxis=dict(gridcolor=LINE, zeroline=False, linecolor=LINE, tickfont=dict(color=MUTED, size=13), fixedrange=True),
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
.brand-logo {{ height: 45px; width: auto; display: block; }}

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
/* 탭을 바꿀 때 내용이 위에서 살짝 내려오며 서서히 나타남.
   fill-mode backwards: 끝나면 transform 이 남지 않아 드롭다운·지도 위치에 영향 없음 */
@keyframes tab-enter {{ from {{ opacity:0; transform: translateY(-14px); }} to {{ opacity:1; transform: translateY(0); }} }}
.stTabs [role="tabpanel"] {{ animation: tab-enter .55s cubic-bezier(.22, .61, .36, 1) backwards; }}
@media (prefers-reduced-motion: reduce) {{ .stTabs [role="tabpanel"] {{ animation: none; }} }}
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
/* 관람료 타일 = 입장권 모양: 양옆 반원 홈 + 점선 절취선 */
.ticket {{
  position:relative; height:140px; border-radius:8px; padding:0 18px;
  display:grid; grid-template-rows: 2fr 3fr;   /* 절취선 위 : 아래 = 2 : 3 */
  -webkit-mask: radial-gradient(circle 9px at 0 40%, transparent 96%, #000 100%) left / 51% 100% no-repeat,
                radial-gradient(circle 9px at 100% 40%, transparent 96%, #000 100%) right / 51% 100% no-repeat;
          mask: radial-gradient(circle 9px at 0 40%, transparent 96%, #000 100%) left / 51% 100% no-repeat,
                radial-gradient(circle 9px at 100% 40%, transparent 96%, #000 100%) right / 51% 100% no-repeat;
  transition: transform .22s ease, filter .22s ease;
}}
.ticket::after {{ content:""; position:absolute; left:16px; right:16px; top:40%; border-top:1.5px dashed currentColor; opacity:.28; }}
.ticket:hover {{ transform: translateY(-4px); filter: brightness(1.03); }}
.ticket .top {{ display:flex; justify-content:space-between; align-items:center; }}
.ticket .bottom {{ display:flex; flex-direction:column; justify-content:center; }}
.ticket .k {{ font-size:13px; font-weight:500; opacity:.85; }}
.ticket .who {{ display:flex; align-items:flex-end; height:26px; opacity:.55; }}
.ticket .v {{ font-family:var(--font-head); font-size:24px; font-weight:700; line-height:1.1; }}
.ticket .s {{ font-size:12px; opacity:.7; margin-top:4px; }}
@media (prefers-reduced-motion: reduce) {{ .ticket {{ transition:none; }} .ticket:hover {{ transform:none; }} }}

/* ── KPI 카드 ── */
.kpi {{ background: var(--surface); border:1px solid var(--line); border-radius: 6px; padding: 24px 26px; }}
.kpi .k {{ font-size:13px; font-weight:500; color:var(--muted); margin-bottom: 12px; }}
.kpi .v {{ font-family:var(--font-head); font-size:34px; font-weight:500; letter-spacing:0; color:var(--navy); line-height:1.1; margin-bottom: 10px; }}
.kpi .s {{ font-size:13px; font-weight:400; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.kpi.accent {{ background: var(--accent); border-color: var(--accent); }}
.kpi.accent .k, .kpi.accent .s {{ color: #FFFFFF; opacity:.92; }}
.kpi.accent .v {{ color: #FFFFFF; }}
/* 마우스를 올리면 살짝 떠오르며 색이 바뀜: 일반 카드 → 연한 강조색, 강조 카드 → 한 톤 진하게 */
.kpi {{ transition: transform .22s ease, background-color .22s ease, border-color .22s ease, box-shadow .22s ease; }}
.kpi .k, .kpi .v, .kpi .s {{ transition: color .22s ease; }}
.kpi:hover {{ transform: translateY(-4px); background: #BA857E; border-color: #BA857E; box-shadow: 0 12px 26px rgba(0, 38, 62, .12); }}  /* 강조색(#A8625B)에 바탕색 25% 섞은 한 톤 연한 색 */
.kpi:hover .k, .kpi:hover .s {{ color: #FFFFFF; opacity:.92; }}
.kpi:hover .v {{ color: #FFFFFF; }}
.kpi.accent:hover {{ background: #8F4F49; border-color: #8F4F49; }}
@media (prefers-reduced-motion: reduce) {{ .kpi, .kpi .k, .kpi .v, .kpi .s {{ transition:none; }} .kpi:hover {{ transform:none; }} }}

/* ── 카드 / 칩 ── */
.card {{ background: var(--surface); border:1px solid var(--line); border-radius:4px; padding:16px 18px; margin-bottom:10px; }}
.card h4 {{ font-family:var(--font-head); font-weight:700; margin:0 0 6px; font-size:17px; color:var(--navy); }}
.card .meta {{ font-size:12px; color:var(--muted); }}
.chip {{ display:inline-block; font-size:11px; padding:3px 10px; border-radius:999px; margin: 6px 6px 0 0; border:1px solid var(--line); color:var(--navy); background:var(--coconut); }}
.chip.solid {{ border-color: transparent; }}
/* 박물관 소개: 4줄만 보이고 '더 보기' 로 펼침 */
details.more > summary {{ list-style:none; cursor:pointer; }}
details.more > summary::-webkit-details-marker {{ display:none; }}
.prod-desc.clamp {{ display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }}
details.more[open] .prod-desc.clamp {{ display:block; -webkit-line-clamp:unset; }}
.more-btn::after {{ content:"더 보기 ▾"; display:inline-block; margin-top:6px; font-size:13px; font-weight:600; color:var(--accent); }}
details.more[open] .more-btn::after {{ content:"접기 ▴"; }}
/* 가까운 박물관 목록: 오른쪽 정보 표(.spec)처럼 구분선 있는 한 줄. 이름은 왼쪽, 거리·관람료는 오른쪽(::after) */
.st-key-dash_nearby {{ gap: 0 !important; border-top: 1px solid var(--line); }}
.st-key-dash_nearby .stButton > button {{
  display:flex !important; justify-content:space-between !important; align-items:center; gap:12px;
  background: transparent !important; border: none !important; border-bottom: 1px solid var(--line) !important;
  border-radius: 0 !important; padding: 12px 6px !important; min-height: 0; transition: background-color .2s ease;
}}
.st-key-dash_nearby .stButton > button > div {{ flex:1; min-width:0; justify-content:flex-start !important; text-align:left; }}
.st-key-dash_nearby .stButton > button p {{ font-family:var(--font-head); font-weight:600; font-size:14px; color:var(--navy); text-align:left;
                                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.st-key-dash_nearby .stButton > button::after {{ font-size:13px; color:var(--muted); white-space:pre; flex-shrink:0; }}
.st-key-dash_nearby .stButton > button:hover {{ background: rgba(168, 98, 91, .08) !important; }}
.st-key-dash_nearby .stButton > button:hover p {{ color: var(--accent); }}
.map-legend {{ display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); margin-top:6px; }}
.map-legend span {{ width:9px; height:9px; border-radius:50%; display:inline-block; margin-left:10px; }}
.map-legend span:first-child {{ margin-left:0; }}
.muted-note {{ font-size:14px; color:var(--muted); margin: 0 0 10px; line-height:1.6; }}
.transit {{ margin: 12px 0 14px; padding-left: 18px; color:#33444F; font-size:15px; line-height:1.8; }}
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
/* 챗봇 '대화 초기화': 글자 너비에 맞춘 둥근 네모, 오른쪽 정렬 */
.st-key-chat_reset {{ align-self: flex-end; margin-left: auto; }}
.st-key-chat_reset button {{
  background: #C9CFB7 !important; border: none !important; color: {NAVY} !important;  /* 초록(BAR_GREEN)을 바탕색과 섞은 연한 톤 */
  border-radius: 8px !important; padding: 6px 18px !important;
}}
/* 대시보드 '카카오맵 길찾기': 글자와 간격을 두고, 왼쪽 선이 글자와 맞는 둥근 네모 */
.st-key-dash_route {{ margin-top: 10px; }}
.st-key-dash_route a {{
  border-radius: 8px !important; padding: 6px 16px !important; background: var(--surface);
  border: 1px solid var(--line) !important; transition: background-color .2s ease, border-color .2s ease, color .2s ease;
}}
.st-key-dash_route a:hover {{ background: var(--accent) !important; border-color: var(--accent) !important; color: #FFFFFF !important; }}
.st-key-dash_route a:hover p {{ color: #FFFFFF !important; }}
/* 챗봇 추천 질문: 마우스를 올리면 강조색으로 채워지며 살짝 떠오름 */
.st-key-chat_suggestions button {{ transition: background-color .2s ease, color .2s ease, border-color .2s ease, transform .2s ease; }}
.st-key-chat_suggestions button:hover {{
  background: var(--accent) !important; border-color: var(--accent) !important; color: #FFFFFF !important; transform: translateY(-2px);
}}
.st-key-chat_suggestions button:hover p {{ color: #FFFFFF !important; }}
.st-key-chat_reset button:hover {{ background: #BCC3A8 !important; }}

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
[data-testid="stChatMessage"] {{ gap: 16px !important; }}  /* 아이콘과 글자 사이 간격 */
[data-testid="stChatInput"] {{ border-color: var(--line) !important; }}
/* 답변 대기 중 로딩 표시: 점 세 개가 차례로 튀어 오름 */
.typing {{ display:flex; align-items:center; gap:6px; height:28px; margin-top:-16px; line-height:1; color:var(--muted); font-size:14px; }}  /* 감싸는 칸의 기본 여백만큼 올려 아이콘 중심과 맞춤 (실측) */
.typing span {{ width:7px; height:7px; border-radius:50%; background:var(--accent); opacity:.35;
               animation: typing-bounce 1.1s infinite ease-in-out; }}
.typing span:nth-child(2) {{ animation-delay:.15s; }}
.typing span:nth-child(3) {{ animation-delay:.3s; }}
.typing em {{ font-style:normal; margin-left:8px; line-height:1; }}
@keyframes typing-bounce {{ 0%, 80%, 100% {{ transform:translateY(0); opacity:.35; }} 40% {{ transform:translateY(-5px); opacity:1; }} }}
@media (prefers-reduced-motion: reduce) {{ .typing span {{ animation:none; opacity:.7; }} }}

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


def topbar(alt: str = "mupick") -> None:
    """상단 로고 (src/service/static/logo.png → /app/static/logo.png)."""
    st.markdown(
        f'<div class="topbar"><img class="brand-logo" src="app/static/logo.png" alt="{escape(alt)}"></div>',
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
