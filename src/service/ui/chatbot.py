"""챗봇 탭: ChromaDB 의미 검색 + OpenAI LLM (RAG).

- 벡터DB: data/vector_db/museum_chroma / 컬렉션 museum_documents (vectoDB_builder.ipynb 로 생성)
- 벡터DB 가 없거나 OPENAI_API_KEY 가 없으면 CSV 키워드 검색으로 대체해 UI 는 계속 동작한다.
"""
import os
from html import escape

import pandas as pd
import streamlit as st

from ui import style as S
from ui.data import PROJECT_ROOT, fee_text

CHROMA_PATH = PROJECT_ROOT / "data" / "vector_db" / "museum_chroma"
COLLECTION = "museum_documents"
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-6-luna")

SYSTEM_PROMPT = """너는 한국 박물관 안내 도우미다.
아래 [검색 결과]에 있는 정보만 근거로 한국어로 답한다. 근거에 없는 내용은 모른다고 말한다.
관람료·운영시간·휴관일은 정확히 옮긴다. 참고한 박물관 목록은 화면에 따로 표시되므로 답변 끝에 다시 나열하지 않는다."""

SUGGESTIONS = [
    "서울에서 무료로 갈 수 있는 박물관 추천해줘",
    "아이와 함께 가기 좋은 체험형 박물관은?",
    "가야 유물을 볼 수 있는 곳 알려줘",
]


@st.cache_resource(show_spinner=False)
def _open_collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_collection(COLLECTION)  # 없으면 예외 → 실패는 캐시되지 않음


def _collection():
    # chroma.sqlite3 가 없으면 PersistentClient 가 빈 DB 를 새로 만들어 버리므로 먼저 확인
    if not (CHROMA_PATH / "chroma.sqlite3").is_file():
        return None
    try:
        return _open_collection()
    except Exception:
        return None


def _vector_status() -> tuple[bool, str]:
    """(벡터 검색 가능 여부, 화면에 띄울 사유)"""
    if not _has_key():
        return False, "OPENAI_API_KEY 없음"
    if not (CHROMA_PATH / "chroma.sqlite3").is_file():
        return False, "벡터DB 파일(chroma.sqlite3) 없음"
    if _collection() is None:
        return False, f"벡터DB에 '{COLLECTION}' 컬렉션 없음"
    return True, ""


@st.cache_resource(show_spinner=False)
def _embeddings():
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=EMBED_MODEL)


@st.cache_resource(show_spinner=False)
def _llm():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=CHAT_MODEL, streaming=True)  # gpt-6-luna 는 temperature 기본값(1)만 지원


def _has_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def retrieve(query: str, df: pd.DataFrame, k: int = 4) -> tuple[list[dict], str]:
    """(검색 결과 리스트, 사용한 검색 방식)"""
    col = _collection()
    if col is not None and _has_key():
        vec = _embeddings().embed_query(query)
        res = col.query(query_embeddings=[vec], n_results=k, include=["documents", "metadatas", "distances"])
        hits = [
            {"museum_id": i, "text": d, "score": 1 - dist, **(m or {})}
            for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]
        return hits, "vector"

    # 대체: 토큰이 이름/지역/설명에 몇 번 나오는지로 점수
    tokens = [t for t in query.replace("?", " ").split() if len(t) >= 2]
    hay = (df["name"].fillna("") + " " + df["sido"].fillna("") + " " + df["sigungu"].fillna("") + " " + df["description"].fillna(""))
    score = sum(hay.str.count(t) for t in tokens) if tokens else pd.Series(0, index=df.index)
    top = df.assign(score=score).query("score > 0").nlargest(k, "score")
    hits = [{**r.to_dict(), "text": r["description"]} for _, r in top.iterrows()]
    return hits, "keyword"


def _context(hits: list[dict]) -> str:
    blocks = []
    for h in hits:
        blocks.append(
            f"- {h.get('name')} ({h.get('sido', '')} {h.get('sigungu', '')})\n"
            f"  성인 {fee_text(h.get('adult_fee'))} / 운영 {h.get('weekday_open', '?')}~{h.get('weekday_close', '?')}"
            f" / 휴관 {h.get('closure_rule_raw', '정보 없음')}\n  {str(h.get('text', ''))[:600]}"
        )
    return "\n".join(blocks)


def _sources_html(hits: list[dict]) -> str:
    chips = "".join(
        f'<span class="chip">{escape(str(h.get("name")))} · {escape(str(h.get("sido", "")))}</span>' for h in hits
    )
    return (
        f'<div style="margin:18px 0 10px;font-size:13px;color:#5E6B73">'
        f'<div style="margin-bottom:4px">참고한 박물관</div>{chips}</div>'
    )


def _answer(query: str, hits: list[dict]):
    if not hits:
        yield "관련 박물관을 찾지 못했어요. 지역이나 주제를 바꿔서 다시 물어봐 주세요."
        return
    if not _has_key():
        yield "OPENAI_API_KEY 가 없어 검색 결과만 보여드려요.\n\n"
        for h in hits:
            yield f"**{h.get('name')}** — {h.get('sido', '')} {h.get('sigungu', '')}, 성인 {fee_text(h.get('adult_fee'))}\n\n"
        return
    history = [(m["role"], m["content"]) for m in st.session_state.chat[-6:]]
    messages = [("system", SYSTEM_PROMPT), *history, ("user", f"[검색 결과]\n{_context(hits)}\n\n[질문]\n{query}")]
    try:
        for chunk in _llm().stream(messages):
            yield chunk.content
    except Exception as e:  # 모델명 오류·네트워크 등 → 앱이 멈추지 않고 안내만
        yield f"\n\n⚠️ 답변 생성에 실패했어요 ({type(e).__name__}). `.env` 의 OPENAI_CHAT_MODEL 값과 API 키를 확인해 주세요.\n\n> {e}"


def render(df: pd.DataFrame) -> None:
    S.page_header(["Home", "Chatbot"], "MUSEUM CHAT", "박물관에 대해 무엇이든 물어보세요")

    mode_ok, reason = _vector_status()
    status = (
        '<span class="status ok">● 벡터 검색 연결됨</span>' if mode_ok
        else f'<span class="status off">● 키워드 검색 모드 ({escape(reason)})</span>'
    )
    head_l, head_r = st.columns([3, 1])
    head_l.markdown(status, unsafe_allow_html=True)
    if head_r.button("대화 초기화", width="stretch"):
        st.session_state.chat = []

    st.session_state.setdefault("chat", [])

    # 화면 배치: [대화 내역] 위 → [추천 질문 + 입력창] 아래.
    # 대화 자리를 먼저 잡아 두고(빈 컨테이너), 입력 위젯을 그 아래에 그린 뒤 대화를 채운다.
    conversation = st.container()

    st.write("")
    cols = st.columns(len(SUGGESTIONS))
    for c, s in zip(cols, SUGGESTIONS):
        if c.button(s, width="stretch", key=f"sugg_{s}"):
            st.session_state["chat_prefill"] = s
    typed = st.chat_input("예) 경주에서 신라 유물 볼 수 있는 박물관은?")
    query = typed or st.session_state.pop("chat_prefill", None)

    with conversation:
        for m in st.session_state.chat:
            with st.chat_message(m["role"], avatar="🏛️" if m["role"] == "assistant" else None):
                st.markdown(m["content"])
                if m.get("sources"):
                    st.markdown(m["sources"], unsafe_allow_html=True)
        if not query:
            return

        with st.chat_message("user"):
            st.markdown(query)
        with st.chat_message("assistant", avatar="🏛️"):
            with st.spinner("관련 박물관을 찾는 중…"):
                hits, _ = retrieve(query, df)
            answer = st.write_stream(_answer(query, hits))
            src = _sources_html(hits) if hits else ""
            if src:
                st.markdown(src, unsafe_allow_html=True)
    st.session_state.chat += [
        {"role": "user", "content": query},
        {"role": "assistant", "content": answer, "sources": src},
    ]
