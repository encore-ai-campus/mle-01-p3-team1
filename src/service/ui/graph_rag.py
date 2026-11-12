"""GraphRAG 탭: Neo4j(Aura) 연결 · 스키마 · 그래프 탐색 · 자연어 질의(Text2Cypher).

.env 에 다음 값을 넣는다 (Aura 콘솔에서 받은 credentials 파일 이름 그대로):
    NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
    NEO4J_USERNAME=neo4j
    NEO4J_PASSWORD=...
    NEO4J_DATABASE=neo4j   (선택)
"""
import json
import os
import re
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ui import style as S

CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-6-luna")
WRITE_PATTERN = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL\s+db\.(?!schema|labels|relationshipTypes))\b", re.I)
NODE_COLORS = S.SERIES

CYPHER_PROMPT = """너는 Neo4j Cypher 전문가다. 아래 그래프 스키마만 사용해 사용자의 질문에 답하는 **읽기 전용** Cypher 한 개를 작성한다.
- 결과는 최대 25행 (LIMIT 25)
- 문자열 매칭은 CONTAINS 사용
- 코드블록이나 설명 없이 Cypher 문만 출력

[스키마]
{schema}

[질문]
{question}"""

ANSWER_PROMPT = """너는 한국 박물관 안내 도우미다. 아래 [그래프 조회 결과]만 근거로 한국어로 간결하게 답한다.
결과가 비어 있으면 그래프에서 찾지 못했다고 말한다.

[질문]
{question}

[Cypher]
{cypher}

[그래프 조회 결과]
{rows}"""


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
    c = _cfg()
    if not c["uri"] or not c["password"]:
        return None, "NEO4J_URI / NEO4J_PASSWORD 가 .env 에 없습니다."
    try:
        return _driver(c["uri"], c["user"], c["password"]), ""
    except Exception as e:  # 인증 실패·네트워크 등
        _driver.clear()
        return None, f"연결 실패: {e}"


def run_read(driver, cypher: str, **params) -> list[dict]:
    if WRITE_PATTERN.search(cypher):
        raise ValueError("쓰기 쿼리는 실행할 수 없습니다 (읽기 전용).")
    records, _, _ = driver.execute_query(cypher, params, database_=_cfg()["database"], routing_="r")
    return [r.data() for r in records]


@st.cache_data(ttl=300, show_spinner=False)
def _schema(_driver) -> dict:
    labels = run_read(_driver, "CALL db.labels() YIELD label RETURN label")
    rels = run_read(_driver, "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType AS type")
    label_counts = {}
    for l in labels:
        name = l["label"]
        label_counts[name] = run_read(_driver, f"MATCH (n:`{name}`) RETURN count(n) AS c")[0]["c"]
    patterns = run_read(
        _driver,
        "MATCH (a)-[r]->(b) WITH labels(a)[0] AS a, type(r) AS r, labels(b)[0] AS b "
        "RETURN a, r, b, count(*) AS c ORDER BY c DESC LIMIT 30",
    )
    props = {}
    for name in label_counts:
        rows = run_read(_driver, f"MATCH (n:`{name}`) WITH n LIMIT 50 UNWIND keys(n) AS k RETURN DISTINCT k")
        props[name] = [r["k"] for r in rows]
    return {"labels": label_counts, "rels": [r["type"] for r in rels], "patterns": patterns, "props": props}


def _schema_text(schema: dict) -> str:
    nodes = "\n".join(f"(:{l} {{{', '.join(p)}}})" for l, p in schema["props"].items())
    pats = "\n".join(f"(:{p['a']})-[:{p['r']}]->(:{p['b']})" for p in schema["patterns"])
    return f"노드:\n{nodes}\n관계:\n{pats}"


def _node_caption(props: dict, labels: list[str]) -> str:
    for k in ("name", "title", "museum_name", "sido", "id"):
        if props.get(k):
            return str(props[k])
    return labels[0] if labels else "?"


def _subgraph(driver, keyword: str, limit: int) -> tuple[list[dict], list[dict]]:
    cypher = (
        "MATCH (n) WHERE any(k IN keys(n) WHERE toString(n[k]) CONTAINS $kw) "
        "WITH n LIMIT 5 MATCH p=(n)-[r]-(m) RETURN n, r, m LIMIT $limit"
    )
    records, _, _ = driver.execute_query(cypher, {"kw": keyword, "limit": limit}, database_=_cfg()["database"], routing_="r")
    nodes, edges, label_color = {}, [], {}
    for rec in records:
        for node in (rec["n"], rec["m"]):
            lbls = list(node.labels)
            lab = lbls[0] if lbls else "Node"
            label_color.setdefault(lab, NODE_COLORS[len(label_color) % len(NODE_COLORS)])
            nodes[node.element_id] = {
                "id": node.element_id, "label": _node_caption(dict(node), lbls), "group": lab,
                "color": label_color[lab], "title": f"{lab}\n" + "\n".join(f"{k}: {v}" for k, v in list(dict(node).items())[:8]),
            }
        r = rec["r"]
        edges.append({"from": r.start_node.element_id, "to": r.end_node.element_id, "label": r.type})
    return list(nodes.values()), edges


def _render_graph(nodes: list[dict], edges: list[dict], height: int = 560) -> None:
    for n in nodes:
        n["font"] = {"color": S.NAVY, "face": "IBM Plex Sans KR, sans-serif", "size": 13}
        n["shape"] = "dot"
        n["size"] = 16
        n["color"] = {"background": n["color"], "border": S.COCONUT, "highlight": {"background": n["color"], "border": S.NAVY}}
        n["borderWidth"] = 2
    html = f"""
<!doctype html><html><head><meta charset="utf-8">
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>@font-face{{font-family:"IBM Plex Sans KR";font-weight:400;src:url("{S.FONT_URL}/IBMPlexSansKR-Regular.woff2") format("woff2");}} html,body{{margin:0;background:{S.SURFACE};}} #g{{height:{height}px;border:1px solid {S.LINE};border-radius:4px;}}</style>
</head><body><div id="g"></div><script>
const nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
const edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
new vis.Network(document.getElementById('g'), {{nodes, edges}}, {{
  physics: {{ stabilization: true, barnesHut: {{ gravitationalConstant: -6000, springLength: 140 }} }},
  edges: {{ color: {{ color: '{S.RESEDA}', highlight: '{S.ACCENT}' }}, arrows: {{ to: {{ enabled: true, scaleFactor: .5 }} }},
           font: {{ size: 10, color: '{S.MUTED}', strokeWidth: 0, align: 'middle' }}, smooth: {{ type: 'continuous' }} }},
  interaction: {{ hover: true, tooltipDelay: 120 }}
}});
</script></body></html>"""
    components.html(html, height=height + 8)


def _text2cypher(question: str, schema_text: str) -> str:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=CHAT_MODEL)
    out = llm.invoke(CYPHER_PROMPT.format(schema=schema_text, question=question)).content
    return re.sub(r"^```(?:cypher)?|```$", "", out.strip(), flags=re.M).strip()


def _graph_answer(question: str, cypher: str, rows: list[dict]):
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=CHAT_MODEL, streaming=True)  # gpt-6-luna 는 temperature 기본값(1)만 지원
    prompt = ANSWER_PROMPT.format(question=question, cypher=cypher, rows=json.dumps(rows[:25], ensure_ascii=False, default=str))
    try:
        for chunk in llm.stream(prompt):
            yield chunk.content
    except Exception as e:
        yield f"⚠️ 답변 생성에 실패했어요 ({type(e).__name__}). `.env` 의 OPENAI_CHAT_MODEL 값과 API 키를 확인해 주세요.\n\n> {e}"


def _setup_guide(msg: str) -> None:
    st.markdown(f'<span class="status off">● Neo4j 미연결</span>', unsafe_allow_html=True)
    st.caption(msg)
    st.markdown(
        '<div class="card"><h4>연결 방법</h4><div class="meta">프로젝트 루트 <code>.env</code> 에 Aura 접속 정보를 추가한 뒤 새로고침하세요.</div></div>',
        unsafe_allow_html=True,
    )
    st.code("NEO4J_URI=neo4j+s://<instance-id>.databases.neo4j.io\nNEO4J_USERNAME=neo4j\nNEO4J_PASSWORD=<password>\nNEO4J_DATABASE=neo4j", language="bash")


def render() -> None:
    S.page_header(["Home", "GraphRAG"], "KNOWLEDGE GRAPH", "Neo4j 지식 그래프로 박물관 관계를 탐색하고 질문하세요")
    driver, err = get_driver()
    if driver is None:
        _setup_guide(err)
        return

    try:
        schema = _schema(driver)
    except Exception as e:
        st.error(f"스키마 조회 실패: {e}")
        return

    st.markdown(f'<span class="status ok">● Neo4j 연결됨 · {escape(_cfg()["uri"])}</span>', unsafe_allow_html=True)
    st.write("")
    labels = schema["labels"]
    total = sum(labels.values())
    cols = st.columns(4)
    cols[0].markdown(S.kpi("노드", f"{total:,}", f"{len(labels)}개 레이블", accent=True), unsafe_allow_html=True)
    cols[1].markdown(S.kpi("관계 유형", f"{len(schema['rels'])}", ", ".join(schema["rels"][:3])), unsafe_allow_html=True)
    top = sorted(labels.items(), key=lambda x: -x[1])[:2]
    for c, (l, n) in zip(cols[2:], top):
        c.markdown(S.kpi(l, f"{n:,}", "노드 수"), unsafe_allow_html=True)

    if total == 0:
        st.info("그래프가 비어 있습니다. src/for_build/build_neo4j 에서 그래프를 먼저 적재하세요.")
        return

    ask, explore, schema_tab = st.tabs(["질문하기", "그래프 탐색", "스키마"])

    with ask:
        S.section("그래프에 질문하기")
        with st.form("graph_q"):
            q = st.text_input("질문", placeholder="예) 경상남도에 있는 국립 박물관은 어디야?", label_visibility="collapsed")
            submitted = st.form_submit_button("질문하기", type="primary")
        if submitted and q:
            if not os.getenv("OPENAI_API_KEY"):
                st.warning("OPENAI_API_KEY 가 필요합니다.")
            else:
                with st.spinner("Cypher 생성 중…"):
                    cypher = _text2cypher(q, _schema_text(schema))
                l, r = st.columns([1, 1], gap="large")
                with l:
                    S.label("생성된 Cypher")
                    st.code(cypher, language="cypher")
                    try:
                        rows = run_read(driver, cypher)
                    except Exception as e:
                        st.error(f"쿼리 실행 실패: {e}")
                        rows = None
                    if rows is not None:
                        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                with r:
                    S.label("답변")
                    if rows is not None:
                        st.write_stream(_graph_answer(q, cypher, rows))

    with explore:
        S.section("키워드 주변 그래프")
        c1, c2 = st.columns([3, 1])
        kw = c1.text_input("키워드", placeholder="박물관 이름, 지역, 주제…", key="graph_kw")
        limit = c2.slider("최대 관계 수", 10, 200, 60, step=10)
        if kw:
            nodes, edges = _subgraph(driver, kw, limit)
            if nodes:
                legend = "".join(
                    f'<span class="chip solid" style="background:{c};color:{S.text_on(c)}">{escape(g)}</span>'
                    for g, c in {n["group"]: n["color"] for n in nodes}.items()
                )
                st.markdown(legend, unsafe_allow_html=True)
                _render_graph(nodes, edges)
            else:
                st.info("일치하는 노드가 없습니다.")

    with schema_tab:
        S.section("스키마")
        st.dataframe(pd.DataFrame(schema["patterns"]).rename(columns={"a": "시작", "r": "관계", "b": "끝", "c": "개수"}), width="stretch", hide_index=True)
        st.code(_schema_text(schema), language="cypher")
