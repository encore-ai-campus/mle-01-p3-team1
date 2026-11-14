"""테마별 추천 탭: 박물관 이름·설명 키워드로 테마를 매기고, 테마를 고르면 어울리는 곳을 카드로 추천한다.

- 테마 점수 = 이름에 나온 키워드 수 × 3 + 설명에 나온 키워드 수. 테마별 기준점 이상이면 그 테마에 속한다.
- 한 박물관이 여러 테마에 속할 수 있다 (예: 고성공룡박물관 = 과학·자연 + 아이와 함께).
- API 키·DB 없이 CSV 만으로 동작한다.
"""
import re
from html import escape

import pandas as pd
import streamlit as st

from ui import nav
from ui import style as S
from ui.data import clean, fee_text, sido_options

# 이름: (정규식, 기준점, 한 줄 소개)
THEMES = {
    "역사·고고": (r"고고|선사|가야|신라|백제|고구려|고려|조선|고분|유적|왕릉|토기|유물|향토사|역사", 3,
              "선사부터 조선까지, 땅속에서 나온 유물로 우리 역사를 따라가는 곳"),
    "미술·공예": (r"미술|갤러리|아트|회화|공예|도자|도예|조각|서예|사진|옻칠|목칠|민화", 3,
              "회화·조각·도자·공예 작품을 천천히 감상하는 미술관과 공예관"),
    "근현대·호국": (r"전쟁|호국|독립운동|항일|6·25|6\.25|한국전쟁|의병|민주화|평화기념|충혼|전투|근대", 2,
               "독립운동과 전쟁, 근현대의 기억을 기록한 기념관"),
    "민속·생활문화": (r"민속|생활사|옹기|짚풀|한옥|탈춤|탈박물관|세계탈|복식|자수|장승|농경|농업", 2,
                "옛사람들의 살림살이와 전통 생활을 엿볼 수 있는 곳"),
    "과학·자연": (r"과학|자연사|천문|우주|공룡|화석|광물|곤충|생태|지질|해양|수족|별", 2,
              "공룡·화석부터 천문·생태까지 자연과 과학을 탐구하는 곳"),
    "아이와 함께": (r"어린이|키즈|체험|가족|놀이", 3,
               "직접 만지고 체험하는 어린이·가족 친화 박물관"),
    "산업·기술": (r"철도|자동차|석탄|탄광|산업|화폐|우정|인쇄|활자|등대|항공|모빌리티|기계", 2,
              "철도·항공·석탄·인쇄 등 산업과 기술의 발자취"),
    "음식·술·차": (r"김치|전통주|막걸리|양조|술박물관|술 박물관|녹차|차문화|다도|떡|커피|음식|소금|장류|젓갈|발효|와인", 2,
               "커피·떡·장류·전통음식을 주제로 한 이색 박물관"),
    "종교·사상": (r"불교|사찰|성보|천주교|성당|기독교|교회|유교|서원|향교|순교|성지", 2,
              "불교·유교·기독교 문화유산과 성보를 만나는 곳"),
    "문학·인물": (r"문학|시인|작가|소설|생가|시문학", 2,
              "작가와 인물의 삶을 따라가는 문학관·기념관"),
}
SORTS = ["테마 적합도순", "사진 있는 곳 먼저", "이름순"]
PAGE = 9  # 한 번에 보여 줄 카드 수 (3열 × 3행)

CARD_CSS = """<style>
.tcard { background: var(--surface); border:1px solid var(--line); border-radius:6px; padding:14px 14px 18px; margin-bottom:8px;
         transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease; }
/* 마우스를 올리면 살짝 떠오르며 커지고, 사진은 안쪽에서 천천히 확대 */
.tcard:hover { transform: translateY(-6px) scale(1.015); box-shadow: 0 14px 30px rgba(0, 38, 62, .12); border-color: #CDBFA8; }
.tcard .ph img { transition: transform .5s ease; }
.tcard:hover .ph img { transform: scale(1.06); }
@media (prefers-reduced-motion: reduce) {
  .tcard, .tcard .ph img { transition: none; }
  .tcard:hover, .tcard:hover .ph img { transform: none; }
}
.tcard h4 { font-family:var(--font-head); font-weight:700; font-size:17px; color:var(--navy); margin:10px 0 4px;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.tcard .meta { font-size:12px; color:var(--muted); }
.tcard .fee { font-size:14px; color:var(--navy); font-weight:500; margin:10px 0 6px; }
.tcard .desc { font-size:13px; line-height:1.65; color:#33444F; min-height:calc(1.65em * 3);
               display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.tcard { position:relative; }
.tcard.has-link { cursor:pointer; }
.tcard-hit { position:absolute; inset:0; z-index:3; border-radius:6px; }
.tcard-img { position:relative; }
.hp-badge { position:absolute; right:10px; bottom:10px; padding:4px 10px; border-radius:6px; font-size:12px; font-weight:600;
             background: rgba(250, 248, 243, .92); color: var(--navy); opacity:0; transform: translateY(4px);
             transition: opacity .2s ease, transform .2s ease; }
.tcard.has-link:hover .hp-badge { opacity:1; transform:none; }
/* 테마 탭 KPI 는 대시보드(테라코타)와 구분되게 하늘색(Powder Blue). 모든 탭이 한 페이지라 컨테이너 키로 범위를 좁힌다.
   하늘색은 밝아서 흰 글자 대신 남색 글자를 쓴다. */
.st-key-theme_kpis .kpi.accent { background:#94B2C4; border-color:#94B2C4; }
.st-key-theme_kpis .kpi:hover { background:#B4C9D5; border-color:#B4C9D5; }
.st-key-theme_kpis .kpi.accent:hover { background:#7FA0B4; border-color:#7FA0B4; }
.st-key-theme_kpis .kpi.accent .v, .st-key-theme_kpis .kpi:hover .v { color: var(--navy); }
.st-key-theme_kpis .kpi.accent .k, .st-key-theme_kpis .kpi.accent .s,
.st-key-theme_kpis .kpi:hover .k, .st-key-theme_kpis .kpi:hover .s { color: #2E4A5C; opacity:1; }
.theme-intro { font-size:15px; color:var(--muted); margin:-6px 0 22px; }
</style>"""


@st.cache_data(show_spinner=False)
def _scores(_df: pd.DataFrame) -> pd.DataFrame:
    """museum_id × 테마 점수표 (기준점 미만은 0). 데이터가 고정이라 한 번만 계산."""
    name = _df["name"].fillna("")
    desc = _df["description"].fillna("").astype(str)
    out = pd.DataFrame(index=_df["museum_id"])
    for theme, (pattern, threshold, _) in THEMES.items():
        rx = re.compile(pattern)
        score = (name.map(lambda s: len(rx.findall(s))) * 3 + desc.map(lambda s: len(rx.findall(s)))).to_numpy()
        out[theme] = [s if s >= threshold else 0 for s in score]
    return out


def _card(row, theme: str, other_themes: list[str]) -> str:
    chips = f'<span class="chip solid" style="background:{S.POWDER_BLUE};border-color:{S.POWDER_BLUE};color:{S.NAVY}">{escape(theme)}</span>'
    chips += "".join(f'<span class="chip">{escape(t)}</span>' for t in other_themes[:2])
    region = " ".join(x for x in (clean(row["sido"], ""), clean(row["sigungu"], "")) if x)
    desc = clean(row["description"], "소개 정보가 없습니다.")
    hp = row.get("homepage_url")
    has_hp = isinstance(hp, str) and hp.startswith("http")
    badge = '<span class="hp-badge">홈페이지 ↗</span>' if has_hp else ""
    # 홈페이지가 있으면 카드 전체를 덮는 투명 링크(새 탭)를 얹는다. <a> 로 카드를 감싸면
    # 마크다운 처리기가 링크를 요소마다 쪼개 넣어 레이아웃이 깨지므로 덮개 방식을 쓴다. (없는 곳 59곳은 링크 없음)
    hit = (
        f'<a class="tcard-hit" href="{escape(hp)}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{escape(row["name"])} 홈페이지 열기"></a>'
        if has_hp else ""
    )
    return (
        f'<div class="tcard{" has-link" if has_hp else ""}">{hit}'
        f'<div class="tcard-img">{S.image_block(row["image_url"], 170)}{badge}</div>'
        f'<div style="margin-top:4px">{chips}</div>'
        f'<h4 title="{escape(row["name"])}">{escape(row["name"])}</h4>'
        f'<div class="meta">{escape(region)} · {escape(clean(row["ownership_type"], ""))}</div>'
        f'<div class="fee">성인 {escape(fee_text(row["adult_fee"]))}</div>'
        f'<div class="desc">{escape(desc)}</div></div>'
    )


def render(df: pd.DataFrame) -> None:
    S.page_header(["Home", "Themes"], "THEME PICKS", "관심 있는 주제를 고르면 어울리는 박물관을 추천해 드려요")
    st.html(CARD_CSS)

    scores = _scores(df)
    counts = (scores > 0).sum()
    names = list(THEMES)
    theme = st.pills(
        "테마", names, default=names[0], key="theme_pick", label_visibility="collapsed",
        format_func=lambda t: f"{t}  {counts[t]}",
    ) or names[0]  # 선택을 해제해도 첫 테마로

    S.section(theme)
    st.markdown(f'<div class="theme-intro">{escape(THEMES[theme][2])}</div>', unsafe_allow_html=True)

    in_theme = df.set_index("museum_id").loc[scores.index[scores[theme] > 0]].reset_index()
    in_theme["score"] = in_theme["museum_id"].map(scores[theme])

    # 요약 KPI
    k1, k2, k3 = st.container(key="theme_kpis").columns(3, gap="medium")
    top_sido = in_theme["sido"].value_counts()
    k1.markdown(S.kpi("테마 박물관", f"{len(in_theme):,}곳", f"전체 {len(df):,}곳 중", accent=True), unsafe_allow_html=True)
    free_pct = in_theme["is_free"].mean() * 100 if len(in_theme) else 0
    k2.markdown(S.kpi("무료 관람", f"{free_pct:.0f}%", "성인 관람료 0원 기준"), unsafe_allow_html=True)
    k3.markdown(
        S.kpi("가장 많은 지역", top_sido.index[0] if len(top_sido) else "-",
              f"{top_sido.iloc[0]}곳" if len(top_sido) else ""),
        unsafe_allow_html=True,
    )

    # 필터
    st.write("")
    c1, c2, c3 = st.columns([2, 1.2, 1], vertical_alignment="bottom")
    sidos = c1.multiselect("시·도", sido_options(in_theme["sido"]), placeholder="전체 지역", key="theme_sido")
    sort = c2.selectbox("정렬", SORTS, key="theme_sort")
    free_only = c3.toggle("무료 관람만", key="theme_free")

    picks = in_theme
    if sidos:
        picks = picks[picks["sido"].isin(sidos)]
    if free_only:
        picks = picks[picks["is_free"]]
    if sort == "테마 적합도순":
        picks = picks.assign(_img=picks["image_url"].notna()).sort_values(["score", "_img"], ascending=False)
    elif sort == "사진 있는 곳 먼저":
        picks = picks.assign(_img=picks["image_url"].notna()).sort_values(["_img", "score"], ascending=False)
    else:
        picks = picks.sort_values("name")

    st.caption(f"추천 **{len(picks):,}곳**")
    if picks.empty:
        st.info("조건에 맞는 박물관이 없어요. 지역이나 필터를 바꿔 보세요.")
        return

    # 테마·필터가 바뀌면 다시 첫 페이지부터
    view_key = (theme, tuple(sidos), sort, free_only)
    if st.session_state.get("theme_view") != view_key:
        st.session_state["theme_view"] = view_key
        st.session_state["theme_shown"] = PAGE
    shown = st.session_state["theme_shown"]

    rows = picks.head(shown)
    for start in range(0, len(rows), 3):
        cols = st.columns(3, gap="medium")
        for col, (_, row) in zip(cols, rows.iloc[start:start + 3].iterrows()):
            others = [t for t in names if t != theme and scores.at[row["museum_id"], t] > 0]
            with col:
                st.markdown(_card(row, theme, others), unsafe_allow_html=True)
                st.button(
                    "챗봇에게 물어보기", key=f"theme_ask_{row['museum_id']}", width="stretch",
                    on_click=nav.ask_chatbot, args=(f"{row['name']} 관람 정보와 주변에 함께 가볼 곳 알려줘",),
                )
        st.write("")

    if shown < len(picks):
        _, mid, _ = st.columns([1, 1, 1])
        if mid.button(f"더 보기 ({shown:,} / {len(picks):,})", width="stretch", key="theme_more"):
            st.session_state["theme_shown"] = shown + PAGE
            st.rerun()
