"""상위 Supervisor에서 호출하는 박물관 Vector 검색 도구 래퍼.

내부에서는 다음 고정 흐름을 딱 한 번 실행한다.
  기본 검색: 질문 분석/확장 -> ChromaDB 후보 조회 -> 관련성 재평가 -> 최대 top_k개 반환
  Hybrid용: 질문 분석/확장 -> ChromaDB 후보 20개 조회 -> 재평가 없이 후보 보존

- run()/retrieve(): 기존 검색 동작과 호환된다 (기본 top_k=5, LLM 재평가).
- retrieve_hybrid_candidates(): Hybrid RAG에서 쓸 벡터 후보를 최대 20개 반환한다.
- 자연어 답변 생성, 재검색 판단 및 실행, Graph 검색 결합은 수행하지 않는다.

파일명/클래스명에 agent가 남아 있는 이유는 기존 호출 코드와의 호환성 때문이다.
설치 위치: src/service/vector_search_rag_agent.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .vector_search_service import VectorSearchService, VectorSearchResponse

# 파일 직접 실행 및 python -m 실행을 모두 지원한다.
if __name__ == "__main__" and not __package__:
    import sys
    _project_root = Path(__file__).resolve().parents[2]
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 상위 Router/Graph에 노출할 실제 도구 이름.
RETRIEVAL_TOOL_NAME = "museum_vector_retrieve"
HYBRID_CANDIDATE_TOOL_NAME = "museum_vector_candidates"
HYBRID_CANDIDATE_K = 20
AGENT_NAME = RETRIEVAL_TOOL_NAME  # 과거 상수명과의 호환용

RETRIEVAL_DESCRIPTION = (
    "한국 박물관·미술관 DB에 대해 전시·역사·예술·과학·유물·체험 등 "
    "내용 기반 의미 검색을 수행합니다. LLM이 검색어를 확장하고, "
    "지원되는 지역(단일/복수 시도)·시군구·소유 구분·관람료 조건을 분리해 "
    "ChromaDB에 적용합니다. 의미 검색에서는 최종 top_k의 4배(최대 40개)를 후보로 "
    "조회하고, LLM이 관련성을 평가한 뒤 최대 top_k개를 반환합니다. "
    "박물관 museum_id, 원본 설명문, 메타데이터, 검색 거리, 관련성 점수, "
    "미지원 조건 및 경고를 반환하며 자연어 최종 답변은 생성하지 않습니다. "
    "관계/운영기관 탐색은 Graph 검색을 사용하세요. 실시간 개관, 최신 요금, "
    "예약 및 미지원 부정·복합 필터를 보장하지 않습니다. 재검색과 답변은 상위 Supervisor가 관리합니다. "
    "Hybrid용 20개 원시 후보가 필요하면 museum_vector_candidates를 사용하세요."
)
AGENT_DESCRIPTION = RETRIEVAL_DESCRIPTION

HYBRID_CANDIDATE_DESCRIPTION = (
    "Hybrid RAG의 중간 후보 풀을 만들기 위한 박물관 벡터 검색 도구입니다. "
    "질문 분석/확장과 ChromaDB 메타데이터 필터는 그대로 적용하지만, "
    "LLM 관련성 재평가·0점 제외·5건 축소는 실행하지 않습니다. "
    f"ChromaDB의 기존 순위대로 최대 {HYBRID_CANDIDATE_K}건을 반환하며 "
    "최종 후보 통합과 선별은 상위 Hybrid RAG가 수행합니다. "
    "실제 일치 문서가 적으면 해당 수만 반환합니다. "
    "관계 검색이나 자연어 답변은 수행하지 않습니다."
)

AGENT_CARD: dict[str, Any] = {
    "name": RETRIEVAL_TOOL_NAME,
    "description": RETRIEVAL_DESCRIPTION,
    "use_when": [
        "시설의 주제·전시 내용·유물·체험 정보를 기반으로 검색할 때",
        "지원하는 지역·기본 요금 조건과 의미 검색을 결합할 때",
        "벡터 검색 자체의 관련성 재평가를 거친 문서와 museum_id가 필요할 때",
    ],
    "avoid_when": [
        "운영기관·관리기관 등 관계를 직접 탐색해야 하는 경우",
        "실시간 개관·최신 요금·예약·경로 정보가 필요한 경우",
        "지원하지 않는 조건의 엄격한 충족이 필수인 경우",
    ],
    "inputs": {"query": "원본 질문", "top_k": "반환 후보 수 1~40 (기본 5)"},
    "outputs": ["results", "source_ids", "warnings", "unsupported_constraints", "search_summary"],
    "retry_owner": "supervisor",
    "generates_answer": False,
}


HYBRID_CANDIDATE_CARD: dict[str, Any] = {
    "name": HYBRID_CANDIDATE_TOOL_NAME,
    "description": HYBRID_CANDIDATE_DESCRIPTION,
    "use_when": ["Hybrid RAG에서 Vector 검색 결과를 Graph/BM25 후보와 통합하기 전"],
    "inputs": {"query": "사용자 원본 질문"},
    "outputs": ["results", "source_ids", "warnings", "unsupported_constraints", "search_summary"],
    "candidate_k": HYBRID_CANDIDATE_K,
    "reranks": False,
    "retry_owner": "supervisor",
    "generates_answer": False,
}


def _validate_input(query: str, top_k: int) -> str:
    """검색어와 반환 상한을 검증한다."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query에는 비어 있지 않은 검색 질문 문자열이 필요합니다.")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 40:
        raise ValueError("top_k는 1~40 사이의 정수여야 합니다.")
    return query.strip()


def _search_summary(search: VectorSearchResponse) -> dict[str, Any]:
    """상위 그래프의 관찰·기록을 위한 검색 진단 정보."""
    return {
        "expanded_query": search.plan.expanded_query,
        "mode": search.plan.mode,
        "where": search.where,
        "filters": search.plan.filters.model_dump(exclude_none=True),
        "candidate_count": search.candidate_count,
        "requested_candidate_k": search.requested_candidate_k,
        "returned_count": len(search.results),
        "excluded_count": search.excluded_count,
        "reranked": search.reranked,
    }


def _result_status(*, has_results: bool, warnings: list[str], unsupported: list[str]) -> str:
    """재검색 여부는 결정하지 않고 검색 상태만 상위에 전달한다."""
    if not has_results:
        return "no_results"
    if warnings or unsupported:
        return "partial"
    return "ok"


def _build_tool_definition() -> dict[str, Any]:
    """LLM 함수 호출 도구로 등록할 때 사용할 입력 명세."""
    return {
        "type": "function",
        "name": RETRIEVAL_TOOL_NAME,
        "description": RETRIEVAL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "사용자 원본 질문. 지역·가격 등 조건을 포함하여 그대로 전달.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "최종 후보 수. 1~40, 기본 권장값 5.",
                },
            },
            "required": ["query", "top_k"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def get_hybrid_candidate_tool_definition() -> dict[str, Any]:
    """Hybrid 후보 도구 입력 명세. 후보 수 20은 도구에서 고정한다."""
    return {
        "type": "function",
        "name": HYBRID_CANDIDATE_TOOL_NAME,
        "description": HYBRID_CANDIDATE_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "사용자 원본 질문. 지역·가격 등의 필터 조건도 포함.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def get_tool_definition(mode: Literal["run", "retrieve"] = "retrieve") -> dict[str, Any]:
    """run/retrieve 모두 같은 검색 전용 Tool 명세를 반환한다."""
    if mode not in ("run", "retrieve"):
        raise ValueError("mode는 'run' 또는 'retrieve'여야 합니다.")
    return _build_tool_definition()


def get_retrieval_tool_definition() -> dict[str, Any]:
    """검색 전용 도구 명세를 명확한 이름으로 가져오는 함수."""
    return get_tool_definition("retrieve")


class VectorSearchRAGAgent:
    """검색 서비스 래퍼. 자율 반복이나 최종 답변 생성 기능은 없다.

    클래스명은 기존 프로젝트 코드의 import 호환성을 위해 유지한다.
    """

    name = RETRIEVAL_TOOL_NAME
    description = RETRIEVAL_DESCRIPTION

    def __init__(self, search_service: VectorSearchService | None = None) -> None:
        # 정보 조회(--info) 시에는 OpenAI와 ChromaDB를 초기화하지 않는다.
        self._search_service = search_service

    @property
    def service(self) -> VectorSearchService:
        if self._search_service is None:
            if __package__:
                from .vector_search_service import VectorSearchService
            else:
                from src.service.vector_search_service import VectorSearchService
            self._search_service = VectorSearchService()
        return self._search_service

    @staticmethod
    def _format_response(search: VectorSearchResponse, *, tool_name: str) -> dict[str, Any]:
        """기존 결과 계약을 재사용해 상위 Supervisor 호환성을 유지한다."""
        warnings = list(search.warnings)
        unsupported = list(search.plan.unsupported_constraints)
        results: list[dict[str, Any]] = []
        for hit in search.results:
            metadata = dict(hit.get("metadata") or {})
            results.append({
                "museum_id": str(hit["museum_id"]),
                "name": metadata.get("name"),
                "document": hit.get("document", ""),
                "metadata": metadata,
                "distance": hit.get("distance"),
                "relevance": hit.get("relevance"),
                "relevance_reason": hit.get("relevance_reason"),
            })

        return {
            "tool": tool_name,
            "status": _result_status(
                has_results=bool(results), warnings=warnings, unsupported=unsupported,
            ),
            "query": search.plan.original_query,
            "results": results,
            "source_ids": [item["museum_id"] for item in results],
            "warnings": warnings,
            "unsupported_constraints": unsupported,
            "search_summary": _search_summary(search),
        }

    def retrieve(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """기존 Vector 검색: 후보 확대 후 LLM 재평가해 최종 top_k개 반환."""
        original_query = _validate_input(query, top_k)
        search = self.service.search(original_query, top_k=top_k, rerank=True)
        return self._format_response(search, tool_name=RETRIEVAL_TOOL_NAME)

    def retrieve_candidates(self, query: str, top_k: int = HYBRID_CANDIDATE_K) -> dict[str, Any]:
        """하이브리드 검색 전용: ChromaDB 후보를 재평가/탈락 없이 반환한다.

        Python 호출자는 필요하면 top_k를 바꿀 수 있다. 도구 등록 시에는
        retrieve_hybrid_candidates()를 이용해 20개를 고정한다.
        """
        original_query = _validate_input(query, top_k)
        search = self.service.search(original_query, top_k=top_k, rerank=False)
        return self._format_response(search, tool_name=HYBRID_CANDIDATE_TOOL_NAME)

    def retrieve_hybrid_candidates(self, query: str) -> dict[str, Any]:
        """상위 Router에 노출할 최대 20개 후보 검색 진입점(요청당 고정 상한)."""
        return self.retrieve_candidates(query=query, top_k=HYBRID_CANDIDATE_K)

    def run(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """기존 호출을 위한 별칭. retrieve()와 동일하게 후보만 반환한다."""
        return self.retrieve(query=query, top_k=top_k)

    def as_langchain_tool(self, mode: Literal["run", "retrieve"] = "retrieve") -> Any:
        """LangChain/LangGraph용 검색 Tool로 등록한다(선택 설치 의존성)."""
        if mode not in ("run", "retrieve"):
            raise ValueError("mode는 'run' 또는 'retrieve'여야 합니다.")
        from langchain_core.tools import StructuredTool
        return StructuredTool.from_function(
            func=self.retrieve,
            name=RETRIEVAL_TOOL_NAME,
            description=RETRIEVAL_DESCRIPTION,
        )

    def as_langchain_retrieval_tool(self) -> Any:
        """기존 검색 Tool을 반환하는 편의 메서드."""
        return self.as_langchain_tool("retrieve")

    def as_langchain_hybrid_candidate_tool(self) -> Any:
        """Hybrid RAG용 후보 20개 검색 Tool을 별도로 등록한다."""
        from langchain_core.tools import StructuredTool
        return StructuredTool.from_function(
            func=self.retrieve_hybrid_candidates,
            name=HYBRID_CANDIDATE_TOOL_NAME,
            description=HYBRID_CANDIDATE_DESCRIPTION,
        )


# 새 코드에서는 역할을 정확히 드러내는 이름으로도 import할 수 있게 한다.
VectorSearchRetriever = VectorSearchRAGAgent


def _main() -> None:
    """실제 API 검색 테스트. 항상 후보만 출력하며 최종 답변을 작성하지 않는다."""
    parser = argparse.ArgumentParser(description="박물관 Vector 검색 도구 (답변 생성 없음)")
    parser.add_argument("query", nargs="?", help="질문. 생략하면 콘솔 입력")
    parser.add_argument("--top-k", type=int, default=None, help="반환 후보 수 (1~40). 기존 검색 기본 5, Hybrid 기본 20")
    parser.add_argument("--hybrid-candidates", action="store_true", help="Hybrid용: LLM 재평가 없이 최대 20개 후보 반환")
    parser.add_argument("--info", action="store_true", help="도구 선택 기준만 출력 (API 미호출)")
    parser.add_argument(
        "--retrieve", action="store_true",
        help="기존 호출과 호환용. 기본 실행도 검색 전용이므로 결과는 같다.",
    )
    args = parser.parse_args()

    if args.info:
        card = HYBRID_CANDIDATE_CARD if args.hybrid_candidates else AGENT_CARD
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    try:
        query = args.query if args.query is not None else input("검색 질문: ")
    except EOFError:
        parser.error("검색 질문을 인자로 전달하거나 콘솔에 입력하세요.")
    agent = VectorSearchRAGAgent()
    if args.hybrid_candidates:
        candidate_k = HYBRID_CANDIDATE_K if args.top_k is None else args.top_k
        response = agent.retrieve_candidates(query, top_k=candidate_k)
    else:
        final_k = 5 if args.top_k is None else args.top_k
        response = agent.run(query, top_k=final_k)
    print(json.dumps(response, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    _main()
