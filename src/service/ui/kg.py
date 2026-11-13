"""Neo4j 지식그래프 공용 모듈 — 챗봇에서 필요할 때만 그래프 검색을 하고, 근거 그래프를 그린다.

.env 에 다음 값을 넣는다 (Aura 콘솔에서 받은 credentials 파일 이름 그대로):
    NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
    NEO4J_USERNAME=neo4j        (NEO4J_USER 도 인식)
    NEO4J_PASSWORD=...
    NEO4J_DATABASE=neo4j        (선택)

흐름 (chatbot.py 에서 호출):
    1. plan()        : LLM 이 질문을 보고 그래프가 필요한지 판단 → 필요하면 읽기 전용 Cypher 생성
    2. run_read()    : Cypher 실행 (쓰기 키워드 차단 + 읽기 라우팅)
    3. evidence()    : 결과에 나온 박물관들의 실제 관계(박물관→시군구→시도, 필요 시 출처)를 다시 조회해 노드·엣지로 변환
    4. render_graph(): vis-network 로 끌어다 놓을 수 있는 반응형 그래프 렌더링
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import streamlit as st
import streamlit.components.v1 as components

from ui import style as S

CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-6-luna")
WRITE_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|CALL)\b", re.I
)
MUSEUM_ID = re.compile(r"^M\d{3,}$")
MAX_IDS = 30  # 근거 그래프에 그릴 최대 박물관 수

# 레이블별 색·크기·표시 이름 (범례 순서 = 이 순서)
NODE_STYLE = {
    "Museum": {"name": "박물관", "color": S.ACCENT, "size": 14},
    "Sigungu": {"name": "시·군·구", "color": "#7FA6C0", "size": 18},
    "Sido": {"name": "시·도", "color": "#4A6680", "size": 24},
    "SourceDocument": {"name": "출처 문서", "color": S.BAR_COCOA, "size": 10},
}
REL_NAME = {"LOCATED_IN": "위치", "PART_OF": "소속", "HAS_SOURCE": "출처"}

# 실제 DB 를 조회해 정리한 스키마 (자동 추출보다 값 예시가 있어 Cypher 정확도가 높다)
SCHEMA = """노드
(:Museum {museum_id, name, sido, sigungu, address, ownership_type, adult_fee, youth_fee, child_fee,
          adult_fee_status, weekday_open, weekday_close, closure_rule_raw, amenities_raw, homepage_url, text})
(:Sigungu {name, sido, region_key})
(:Sido {name})
(:SourceDocument {doc_id, source_type, source_file, match_trust})

관계
(:Museum)-[:LOCATED_IN]->(:Sigungu)-[:PART_OF]->(:Sido)
(:Museum)-[:HAS_SOURCE]->(:SourceDocument)

값 예시
- museum_id: 'M0001' 형식
- ownership_type: '국립' | '공립' | '사립' | '대학'
- adult_fee: 숫자(원). 0 은 '무료로 기록됨'이지만 검증된 무료는 아님 (adult_fee_status='BASE_FEE_ZERO_CHECK_EXCEPTIONS')
- weekday_open / weekday_close: '09:00' 형식 문자열
- amenities_raw: '주차장+수유실+유모차/휠체어 이용가능' 처럼 + 로 이어진 문자열
- source_type: 'TOUR_API' | 'BASE' | 'WEB_RESEARCH'
- Sido.name: 강원특별자치도, 경기도, 경상남도, 경상북도, 광주광역시, 대구광역시, 대전광역시, 부산광역시,
  서울특별시, 세종특별시, 세종특별자치시, 울산광역시, 인천광역시, 전남광주통합특별시, 전라남도, 전라북도,
  전북특별자치도, 제주특별자치도, 충청남도, 충청북도
  (같은 지역이 옛/새 이름으로 나뉜 경우가 있다: 전북 = 전라북도·전북특별자치도, 세종 = 세종특별시·세종특별자치시,
   전남 = 전라남도·전남광주통합특별시. 전남광주통합특별시에는 전남 시·군만 있고 광주광역시는 별개 지역이다)"""

PLAN_PROMPT = """너는 박물관 안내 챗봇의 검색 라우터다. 질문을 아래 Neo4j 지식그래프로 답하는 게 좋은지 판단하고,
좋다면 읽기 전용 Cypher 한 개를 만든다.

[그래프를 쓰는 질문] use_graph = true
- 지역 구조: 특정 시·도 / 시·군·구에 있는 박물관 목록, 지역별 개수·순위 비교
- 조건 필터·집계: 운영 주체(국립·공립·사립·대학), 관람료, 운영 시간, 편의시설 조건, 개수 세기
- 다중 홉 관계: 특정 박물관과 같은 시·군·구(또는 시·도)에 있는 다른 박물관
- 박물관 설명의 출처 문서
[그래프를 쓰지 않는 질문] use_graph = false
- 전시 주제·분위기·체험 내용처럼 설명 글의 의미로 찾아야 하는 추천 (예: "가야 유물", "아이와 체험")
- 인사, 잡담, 박물관과 무관한 질문, 한 박물관의 소개만 묻는 질문

[스키마]
{schema}

[Cypher 규칙]
- MATCH / OPTIONAL MATCH / WHERE / WITH / RETURN / ORDER BY / LIMIT 만 사용 (CALL·쓰기 금지). 최대 LIMIT 25.
- 지역 조건은 반드시 (m:Museum)-[:LOCATED_IN]->(g:Sigungu)-[:PART_OF]->(s:Sido) 경로로 건다.
- 사용자가 "서울", "경남"처럼 줄여 말하면 위 Sido.name 목록의 정식 이름으로 바꾼다. 옛/새 이름이 둘 다 있으면 IN 으로 둘 다 넣는다.
- 결과에 박물관이 나오면 반드시 m.museum_id AS museum_id, m.name AS name 을 함께 반환한다.
- 개수·순위 같은 집계라면 collect(m.museum_id)[..5] AS museum_ids 를 함께 반환한다.
- 다른 박물관을 기준으로 찾는 질문(같은 구·같은 시도 등)이면 기준 박물관의 museum_id 도 base_id 로 함께 반환한다.
  한 MATCH 안에서 같은 관계를 두 번 지나면 결과가 비므로, MATCH 를 나누고 노드만 공유한다. 예)
  MATCH (base:Museum) WHERE base.name CONTAINS '전쟁기념관'
  WITH base ORDER BY size(base.name) LIMIT 1          // 이름이 가장 가까운 박물관 하나만 기준으로
  MATCH (base)-[:LOCATED_IN]->(g:Sigungu)
  MATCH (m:Museum)-[:LOCATED_IN]->(g) WHERE m <> base
  RETURN base.museum_id AS base_id, m.museum_id AS museum_id, m.name AS name LIMIT 25
- 박물관 이름은 정확히 같지 않을 수 있으니 CONTAINS 로 찾는다.
- 문자열 부분 일치는 CONTAINS.

[이전 대화]
{history}

[질문]
{question}

JSON 한 개만 출력한다. 설명·코드블록 금지.
{{"use_graph": true, "cypher": "..."}} 또는 {{"use_graph": false}}"""

# 답변 프롬프트에 넣지 않을 큰 속성 (토큰 낭비)
_DROP_KEYS = {"text", "text_spans_json", "source_documents_json", "text_sha256", "qa_flags", "merge_review_flags"}


@dataclass
class GraphResult:
    cypher: str
    rows: list[dict]
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    museums: list[dict] = field(default_factory=list)  # [{"name", "sido"}] 근거 그래프의 박물관
    error: str = ""


# ── 연결 ──────────────────────────────────────────────
def _cfg() -> dict:
    return {
        "uri": os.getenv("NEO4J_URI", ""),
        "user": os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", ""),
        "database": os.getenv("NEO4J_DATABASE") or None,
    }


@st.cache_resource(show_spinner=False)
def _driver(uri: str, user: str, password: str):
    from neo4j import GraphDatabase

    drv = GraphDatabase.driver(uri, auth=(user, password))
    drv.verify_connectivity()
    return drv


def get_driver():
    """(driver | None, 실패 사유). 실패는 캐시하지 않아 .env 를 고치면 다시 시도된다."""
    c = _cfg()
    if not c["uri"] or not c["password"]:
        return None, "NEO4J_URI / NEO4J_PASSWORD 없음"
    try:
        return _driver(c["uri"], c["user"], c["password"]), ""
    except Exception as e:  # 인증 실패·네트워크 등
        return None, f"Neo4j 연결 실패 ({type(e).__name__})"


def _execute(driver, cypher: str, **params):
    if WRITE_PATTERN.search(cypher):
        raise ValueError("읽기 전용 쿼리만 실행할 수 있습니다.")
    records, _, _ = driver.execute_query(cypher, params, database_=_cfg()["database"], routing_="r")
    return records


def run_read(driver, cypher: str, **params) -> list[dict]:
    return [r.data() for r in _execute(driver, cypher, **params)]


# ── 1. 그래프가 필요한지 판단 + Cypher 생성 ─────────────
def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def plan(question: str, history: str = "") -> str | None:
    """그래프가 필요하면 Cypher, 아니면 None."""
    from langchain_openai import ChatOpenAI

    out = ChatOpenAI(model=CHAT_MODEL).invoke(
        PLAN_PROMPT.format(schema=SCHEMA, history=history or "(없음)", question=question)
    ).content
    data = _parse_json(out)
    if not data.get("use_graph") or not data.get("cypher"):
        return None
    return re.sub(r"^```(?:cypher)?|```$", "", data["cypher"].strip(), flags=re.M).strip()


# ── 3. 근거 그래프 (결과에 나온 박물관의 실제 관계) ──────
def _collect_ids(value, out: list[str]) -> None:
    """결과 행 어디에 있든 museum_id 형식 값을 모은다 (컬럼명·중첩 리스트·노드 dict 모두)."""
    if isinstance(value, str):
        if MUSEUM_ID.match(value) and value not in out:
            out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_ids(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect_ids(v, out)


def _caption(label: str, props: dict) -> str:
    if label == "SourceDocument":
        return str(props.get("source_type", "출처"))
    return str(props.get("name") or props.get("museum_id") or label)


def _tooltip(label: str, props: dict) -> str:
    keys = {
        "Museum": ["name", "sido", "sigungu", "ownership_type", "adult_fee", "weekday_open", "weekday_close"],
        "Sigungu": ["name", "sido"],
        "Sido": ["name"],
        "SourceDocument": ["source_type", "source_file", "match_trust"],
    }.get(label, list(props)[:6])
    lines = [NODE_STYLE.get(label, {}).get("name", label)]
    lines += [f"{k}: {props[k]}" for k in keys if props.get(k) not in (None, "")]
    return "\n".join(lines)


def evidence(driver, rows: list[dict], cypher: str) -> tuple[list[dict], list[dict], list[dict]]:
    ids: list[str] = []
    _collect_ids(rows, ids)
    ids = ids[:MAX_IDS]
    if not ids:
        return [], [], []

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(n):
        label = next(iter(n.labels), "Node")
        props = dict(n)
        nodes.setdefault(n.element_id, {"id": n.element_id, "group": label,
                                        "label": _caption(label, props), "title": _tooltip(label, props),
                                        "_props": props})

    def add_edge(r):
        edges.setdefault(r.element_id, {"from": r.start_node.element_id, "to": r.end_node.element_id,
                                        "label": REL_NAME.get(r.type, r.type), "title": r.type})

    for rec in _execute(
        driver,
        "MATCH (m:Museum)-[r1:LOCATED_IN]->(g:Sigungu)-[r2:PART_OF]->(s:Sido) "
        "WHERE m.museum_id IN $ids RETURN m, r1, g, r2, s",
        ids=ids,
    ):
        for k in ("m", "g", "s"):
            add_node(rec[k])
        add_edge(rec["r1"])
        add_edge(rec["r2"])

    if re.search(r"SourceDocument|HAS_SOURCE", cypher):  # 출처를 물은 질문이면 출처 문서까지
        for rec in _execute(
            driver,
            "MATCH (m:Museum)-[r:HAS_SOURCE]->(d:SourceDocument) WHERE m.museum_id IN $ids RETURN m, r, d LIMIT 60",
            ids=ids,
        ):
            add_node(rec["m"])
            add_node(rec["d"])
            add_edge(rec["r"])

    museums = [
        {"name": n["_props"].get("name"), "sido": n["_props"].get("sido", "")}
        for n in nodes.values() if n["group"] == "Museum"
    ]
    for n in nodes.values():
        n.pop("_props")
    return list(nodes.values()), list(edges.values()), museums


def search(driver, question: str, history: str = "") -> GraphResult | None:
    """그래프 검색 전체. 그래프가 필요 없는 질문이면 None.

    Streamlit 위젯을 쓰지 않으므로 스레드에서 벡터 검색과 동시에 돌릴 수 있다.
    """
    try:
        cypher = plan(question, history)
    except Exception as e:
        return GraphResult(cypher="", rows=[], error=f"Cypher 생성 실패 ({type(e).__name__})")
    if not cypher:
        return None
    try:
        rows = run_read(driver, cypher)
    except Exception as e:
        return GraphResult(cypher=cypher, rows=[], error=f"쿼리 실행 실패 ({type(e).__name__})")
    result = GraphResult(cypher=cypher, rows=rows)
    if rows:
        try:
            result.nodes, result.edges, result.museums = evidence(driver, rows, cypher)
        except Exception:
            pass  # 근거 그래프만 실패 → 답변·Cypher 는 그대로 보여준다
    return result


def rows_for_prompt(rows: list[dict], limit_chars: int = 6000) -> str:
    def slim(v):
        if isinstance(v, dict):
            return {k: slim(x) for k, x in v.items() if k not in _DROP_KEYS}
        if isinstance(v, list):
            return [slim(x) for x in v]
        return v

    text = json.dumps([slim(r) for r in rows[:25]], ensure_ascii=False, default=str)
    return text[:limit_chars]


# ── 4. 렌더링 ──────────────────────────────────────────
def legend_html(nodes: list[dict]) -> str:
    present = {n["group"] for n in nodes}
    chips = "".join(
        f'<span class="chip solid" style="background:{v["color"]};color:{S.text_on(v["color"])}">{v["name"]}</span>'
        for k, v in NODE_STYLE.items() if k in present
    )
    return f'<div style="margin:2px 0 8px">{chips}</div>'


def render_graph(nodes: list[dict], edges: list[dict], height: int = 440) -> None:
    """노드를 끌어다 놓을 수 있는 반응형 그래프 (vis-network, 물리 엔진 켜짐)."""
    vis_nodes = []
    for n in nodes:
        style = NODE_STYLE.get(n["group"], {"color": S.RESEDA, "size": 12})
        c = style["color"]
        vis_nodes.append({
            **n, "shape": "dot", "size": style["size"], "borderWidth": 2,
            "color": {"background": c, "border": S.SURFACE,
                      "highlight": {"background": c, "border": S.NAVY},
                      "hover": {"background": c, "border": S.NAVY}},
            "font": {"color": S.NAVY, "face": "IBM Plex Sans KR, sans-serif",
                     "size": 14 if n["group"] != "SourceDocument" else 11},
        })
    html = f"""
<!doctype html><html><head><meta charset="utf-8">
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
@font-face{{font-family:"IBM Plex Sans KR";font-weight:400;src:url("{S.FONT_URL}/IBMPlexSansKR-Regular.woff2") format("woff2");}}
html,body{{margin:0;background:{S.SURFACE};}}
#g{{height:{height}px;border:1px solid {S.LINE};border-radius:6px;background:{S.SURFACE};}}
.hint{{position:absolute;right:12px;bottom:10px;font:12px "IBM Plex Sans KR",sans-serif;color:{S.MUTED};pointer-events:none;}}
div.vis-tooltip{{font:12px/1.5 "IBM Plex Sans KR",sans-serif;white-space:pre;background:#fff;border:1px solid {S.LINE};color:{S.NAVY};padding:8px 10px;border-radius:4px;}}
</style>
</head><body><div id="g"></div><div class="hint">노드를 끌어 옮기거나 확대·축소할 수 있어요</div><script>
const nodes = new vis.DataSet({json.dumps(vis_nodes, ensure_ascii=False)});
const edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
new vis.Network(document.getElementById('g'), {{nodes, edges}}, {{
  physics: {{ stabilization: {{ iterations: 200 }}, barnesHut: {{ gravitationalConstant: -4200, springLength: 110, springConstant: 0.03 }} }},
  edges: {{ color: {{ color: '{S.RESEDA}', highlight: '{S.ACCENT}', hover: '{S.ACCENT}' }}, width: 1.4,
           arrows: {{ to: {{ enabled: true, scaleFactor: .45 }} }},
           font: {{ size: 10, color: '{S.MUTED}', strokeWidth: 3, strokeColor: '{S.SURFACE}', align: 'middle' }},
           smooth: {{ type: 'continuous' }} }},
  interaction: {{ hover: true, tooltipDelay: 120, dragNodes: true, zoomView: true, navigationButtons: false }}
}});
</script></body></html>"""
    components.html(html, height=height + 10)
