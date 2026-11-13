"""LangGraph가 전달하는 공통 상태와 검색 근거 타입."""

from typing import Literal, TypedDict


Route = Literal["vector", "graph", "hybrid"]


class Evidence(TypedDict, total=False):
    museum_id: str
    name: str
    text: str
    source_doc_ids: list[str]
    source_url: str
    source_urls: list[str]
    chunk_id: str
    span_id: str
    sido: str
    sigungu: str
    matched_terms: list[str]
    score: float
    retriever: str
    # 하이브리드 검색에서 같은 근거가 두 검색기에 잡힌 경우 출처를 모두 보존한다.
    retrievers: list[str]


class AgentState(TypedDict, total=False):
    question: str
    route: Route
    evidence: list[Evidence]
    answer: str
    verified: bool
    retry_count: int
    route_trace: list[Route]
    failure_reason: str
    # 가드레일이 막은 위치. 막히지 않았으면 키가 없다.
    blocked_by: Literal["input", "output"]
