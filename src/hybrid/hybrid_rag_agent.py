"""Graph-ready museum Hybrid Retrieval Agent (retrieval only).

Public interface mirrors src/service/vector_search_rag_agent.py:
    HybridRAGAgent().retrieve(query, top_k=10) -> dict
    HybridRAGAgent().run(query, top_k=10)      -> dict
    HybridRAGAgent().as_langchain_tool()      -> StructuredTool
    HybridRAGAgent().as_langgraph_node()      -> StateGraph node callable
    HybridRAGAgent().as_langgraph_tool_node() -> LangGraph ToolNode

Pipeline: query analysis -> independent Chroma/BM25 Top-20 -> weighted RRF
Top-20 -> Cross-Encoder Top-10. No Neo4j, answer generation, or retries.

Run (at project root):
    uv run python -m src.hybrid.hybrid_rag_agent
    uv run python -m src.hybrid.hybrid_rag_agent "독립운동 관련 박물관"
    uv run python -m src.hybrid.hybrid_rag_agent "독립운동 관련 박물관" --show-stages --show-fusion
    uv run python -m src.hybrid.hybrid_rag_agent --info
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .config import HybridConfig
    from .service import HybridSearchService

# Enable both python -m and direct script execution, matching VectorSearchRAGAgent.
if __name__ == "__main__" and not __package__:
    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

RETRIEVAL_TOOL_NAME = "museum_hybrid_retrieve"
AGENT_NAME = RETRIEVAL_TOOL_NAME
RETRIEVAL_DESCRIPTION = (
    "한국 박물관·미술관 데이터를 대상으로 독립적인 BM25 키워드 검색과 ChromaDB 의미 검색을 "
    "병렬 수행한 뒤, 가중 RRF로 결합하고 Cross-Encoder로 최종 후보를 재정렬합니다. "
    "기본값은 BM25 20개 + Vector 20개 -> RRF 20개 -> 최종 10개입니다. "
    "지역·관람료 등 지원되는 메타데이터 조건을 공통 적용하고, museum_id, 설명문, "
    "각 검색 순위·점수, 실행 단계 진단, 경고를 반환합니다. 자연어 답변은 생성하지 않습니다. "
    "Neo4j 관계 탐색, 실시간 영업 상태, 최신 요금/예약은 보장하지 않으며, "
    "재검색과 답변 생성은 상위 Supervisor가 담당합니다."
)
AGENT_DESCRIPTION = RETRIEVAL_DESCRIPTION

AGENT_CARD: dict[str, Any] = {
    "name": RETRIEVAL_TOOL_NAME,
    "description": RETRIEVAL_DESCRIPTION,
    "use_when": [
        "박물관의 이름·용어 일치와 문맥적 의미 검색을 함께 적용해야 할 때",
        "사용자 질문으로 박물관 후보와 참고 설명문을 확보해야 할 때",
        "상위 LangGraph에서 검색 Tool 결과, 검색 순위, 단계 진단이 필요할 때",
    ],
    "avoid_when": [
        "기관 관계·운영기관을 Neo4j에서 직접 탐색해야 하는 경우",
        "실시간 개관·예약·최신 가격 확인이 필요한 경우",
        "검색 후보가 아니라 자연어 최종 답변을 생성해야 하는 경우",
    ],
    "inputs": {
        "query": "원본 사용자 질문 (필수)",
        "top_k": "최종 반환 후보 수 (기본 10; fusion_top_k 이내)",
    },
    "outputs": ["results", "source_ids", "warnings", "unsupported_constraints", "search_summary"],
    "retry_owner": "supervisor",
    "generates_answer": False,
    "graph_integration": ["as_langchain_tool", "as_langgraph_tool_node", "as_langgraph_node"],
}


def _validate_top_k(top_k: int) -> None:
    if type(top_k) is not int or not 1 <= top_k <= 40:
        raise ValueError("top_k는 1~40 사이의 정수여야 합니다. fusion_top_k도 초과할 수 없습니다.")


def _validate_input(query: str, top_k: int) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query에는 비어 있지 않은 질문 문자열이 필요합니다.")
    _validate_top_k(top_k)
    cleaned = " ".join(query.split())
    if len(cleaned) > 500:
        raise ValueError("query는 최대 500자까지 허용됩니다 (기존 Vector 분석기 계약).")
    return cleaned


def _build_tool_definition() -> dict[str, Any]:
    """Strict function tool in the same shape as the vector agent.

    Actual top_k limit also depends on the configured fusion_top_k. The
    graph should normally use the default 10 candidates.
    """
    return {
        "type": "function",
        "name": RETRIEVAL_TOOL_NAME,
        "description": RETRIEVAL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "원본 사용자 질문. 지역 및 요금 조건을 포함하여 그대로 전달.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "최종 반환 후보 수. 기본 권장값 10 (fusion_top_k 이하).",
                },
            },
            "required": ["query", "top_k"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def get_tool_definition(mode: Literal["run", "retrieve"] = "retrieve") -> dict[str, Any]:
    if mode not in ("run", "retrieve"):
        raise ValueError("mode는 'run' 또는 'retrieve'여야 합니다.")
    return _build_tool_definition()


def get_retrieval_tool_definition() -> dict[str, Any]:
    return get_tool_definition("retrieve")


class HybridRAGAgent:
    """Graph-facing wrapper that builds the BM25 index only once per instance.

    Inject ``search_service`` when a higher-level application already owns the
    service. When omitted, construction is lazy, so importing this module,
    registering tools, and --info never touch the LLM or disk DB.
    """

    name = RETRIEVAL_TOOL_NAME
    description = RETRIEVAL_DESCRIPTION

    def __init__(
        self,
        search_service: HybridSearchService | None = None,
        *,
        config: HybridConfig | None = None,
        corpus_source: Literal["chroma", "file"] = "chroma",
        corpus_path: str | Path | None = None,
        chroma_db_path: str | Path | None = None,
        chroma_collection_name: str = "museum_documents",
    ) -> None:
        if corpus_source not in ("chroma", "file"):
            raise ValueError("corpus_source는 'chroma' 또는 'file'이어야 합니다.")
        self._search_service = search_service
        self._init_lock = Lock()
        self._config = config
        self._corpus_source = corpus_source
        self._corpus_path = corpus_path
        self._chroma_db_path = chroma_db_path
        self._chroma_collection_name = chroma_collection_name

    @property
    def service(self) -> HybridSearchService:
        if self._search_service is None:
            with self._init_lock:
                if self._search_service is None:
                    from src.hybrid.factory import build_hybrid_service

                    self._search_service = build_hybrid_service(
                        corpus_source=self._corpus_source,
                        corpus_path=self._corpus_path,
                        chroma_db_path=self._chroma_db_path,
                        chroma_collection_name=self._chroma_collection_name,
                        config=self._config,
                    )
        return self._search_service

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        *,
        rerank: bool = True,
        include_fusion_candidates: bool = False,
        include_retrieval_candidates: bool = False,
    ) -> dict[str, Any]:
        """Run exactly one retrieval pipeline and return candidates, never an answer.

        The LangChain tool exposes only query and top_k; diagnostics remain
        available in search_summary. Detailed per-stage candidates are opt-in.
        """
        original = _validate_input(query, top_k)
        if type(rerank) is not bool:
            raise TypeError("rerank는 bool이어야 합니다.")
        return self.service.search(
            original,
            top_k=top_k,
            rerank=rerank,
            include_fusion_candidates=include_fusion_candidates,
            include_retrieval_candidates=include_retrieval_candidates,
        )

    def run(self, query: str, top_k: int = 10) -> dict[str, Any]:
        """Compatibility alias to retrieve(), analogous to the vector agent."""
        return self.retrieve(query=query, top_k=top_k)

    def as_langchain_tool(self, mode: Literal["run", "retrieve"] = "retrieve") -> Any:
        """Return a StructuredTool for LangChain/LangGraph's ToolNode.

        The wrapper has a small schema so the LLM cannot turn off reranking,
        change retrieval weights, or request full diagnostic payloads.
        """
        if mode not in ("run", "retrieve"):
            raise ValueError("mode는 'run' 또는 'retrieve'여야 합니다.")
        try:
            from langchain_core.tools import StructuredTool
        except ImportError as exc:
            raise RuntimeError("LangChain Tool을 사용하려면 langchain-core를 설치해야 합니다.") from exc

        def invoke_hybrid(query: str, top_k: int = 10) -> dict[str, Any]:
            """Retrieve museum evidence using BM25 + vector hybrid search."""
            return self.retrieve(query, top_k=top_k)

        return StructuredTool.from_function(
            func=invoke_hybrid,
            name=RETRIEVAL_TOOL_NAME,
            description=RETRIEVAL_DESCRIPTION,
        )

    def as_langchain_retrieval_tool(self) -> Any:
        return self.as_langchain_tool("retrieve")

    def as_langgraph_tool_node(self) -> Any:
        """Build a ToolNode (requires a LangGraph messages/tool-call state)."""
        try:
            from langgraph.prebuilt import ToolNode
        except ImportError as exc:
            raise RuntimeError("LangGraph ToolNode를 사용하려면 langgraph를 설치해야 합니다.") from exc
        return ToolNode([self.as_langchain_tool()])

    def as_langgraph_node(
        self,
        *,
        input_key: str = "question",
        output_key: str = "hybrid_result",
        top_k: int = 10,
    ) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
        """Return a plain StateGraph node, independent of message/tool routing.

        Callers MUST define output_key in their State TypedDict/schema; this
        does not silently mutate other Graph state or create graph edges.
        """
        _validate_top_k(top_k)
        if not input_key or not output_key:
            raise ValueError("input_key와 output_key는 비어 있을 수 없습니다.")

        def node(state: Mapping[str, Any]) -> dict[str, Any]:
            if not isinstance(state, Mapping):
                raise TypeError("LangGraph state must be a mapping")
            question = state.get(input_key)
            if not isinstance(question, str) or not question.strip():
                raise ValueError(f"LangGraph state['{input_key}']에 질문이 없습니다.")
            return {output_key: self.retrieve(question, top_k=top_k)}

        return node


# Names people may expect after using the old vector-search wrapper.
HybridSearchRAGAgent = HybridRAGAgent
HybridSearchRetriever = HybridRAGAgent


def _readable_duration(ms: Any) -> str:
    return f"{ms:.1f} ms" if isinstance(ms, (int, float)) else "-"


def _print_preview(result: Mapping[str, Any], *, show_fusion: bool, show_stages: bool) -> None:
    """Human-friendly CLI report: real counts, methods, scores, and candidate IDs."""
    summary = result["search_summary"]
    print("\n" + "=" * 72)
    print("[Hybrid RAG] 검색 과정 / 실제 실행 결과")
    print("=" * 72)
    print("질문:", result["query"])
    print("상태:", result["status"])
    print("확장 의미 검색어:", summary.get("expanded_query") or "(없음)")
    print("분리된 필터:", json.dumps(summary.get("metadata_filters", {}), ensure_ascii=False))
    print("\n[단계별 처리]")
    names = {
        "query_analysis": "① 질문 분석·필터",
        "vector_retrieval": "② Chroma Vector",
        "bm25_retrieval": "③ Sparse BM25",
        "rrf_fusion": "④ 가중 RRF Fusion",
        "cross_encoder_rerank": "⑤ Cross-Encoder",
        "final_selection": "⑥ 최종 후보",
    }
    for stage in summary.get("stages", []):
        label = names.get(stage["stage"], stage["stage"])
        counts = (f" | {stage.get('returned')}/{stage.get('requested')}건"
                  if "returned" in stage else "")
        print(f"  {label}: {stage['status']}{counts} | {_readable_duration(stage.get('duration_ms'))}")
        if stage.get("stage") == "cross_encoder_rerank" and "model_load_ms" in stage:
            print("     - 모델 로딩:", _readable_duration(stage.get("model_load_ms")),
                  "| 실제 추론:", _readable_duration(stage.get("inference_ms")),
                  "| 출처:", stage.get("model_source", "unknown"))
    print("총 소요:", _readable_duration(summary.get("total_duration_ms")))
    conf = summary.get("config", {})
    print("RRF 가중치: Vector", conf.get("vector_weight"), "/ BM25", conf.get("bm25_weight"),
          "| k =", conf.get("rrf_k"))
    if result.get("warnings"):
        print("\n[경고 / 확인 필요]")
        for warning in result["warnings"]:
            print(" -", warning)

    if show_stages:
        print("\n[각 검색기의 원본 후보]")
        for source, hits in result.get("retrieval_candidates", {}).items():
            print(f"  {source.upper()} ({len(hits)}건)")
            for hit in hits:
                score = hit.get("score") if source == "bm25" else hit.get("distance")
                print(f"    {hit['rank']:>2}. {hit.get('name') or '-'} [{hit['museum_id']}] / ",
                      f"{'BM25' if source == 'bm25' else 'distance'}={score}")

    if show_fusion:
        print("\n[RRF Fusion 후보]")
        for hit in result.get("fusion_candidates", []):
            print(f"  {hit['fusion_rank']:>2}. {hit.get('name') or '-'} [{hit['museum_id']}] ",
                  f"RRF={hit['fusion_score']:.6f} / V={hit.get('vector_rank')} B={hit.get('bm25_rank')}")

    print("\n[최종 검색 결과]")
    for hit in result["results"]:
        metadata = hit.get("metadata") or {}
        loc = " ".join(str(metadata.get(x) or "") for x in ("sido", "sigungu")).strip()
        score = hit.get("score")
        score_str = f"{score:.6f}" if isinstance(score, (float, int)) else "-"
        print(f" {hit['rank']:>2}. {hit.get('name') or '(이름 없음)'} [{hit['museum_id']}]")
        print(f"     지역: {loc or '-'} | {hit['score_type']}={score_str} | ",
              f"Vector {hit.get('vector_rank') or '-'}위 / BM25 {hit.get('bm25_rank') or '-'}위")
        doc = str(hit.get("document") or "").strip().replace("\n", " ")
        if doc:
            print("     설명:", doc[:200] + ("..." if len(doc) > 200 else ""))
        if hit.get("best_span_text") and hit["best_span_text"] != hit.get("document"):
            print("     BM25 근거:", str(hit["best_span_text"])[:130])
    if not result["results"]:
        print("  조건에 맞는 검색 후보가 없습니다.")
    print("\n최종 source_ids:", result.get("source_ids", []))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="박물관 BM25 + Chroma 하이브리드 검색 Agent (검색 전용; LangGraph 연결 가능)"
    )
    parser.add_argument("query", nargs="?", help="질문. 생략하면 콘솔에서 직접 입력")
    parser.add_argument("--info", action="store_true", help="Tool 명세 출력 (DB/LLM 미호출)")
    parser.add_argument("--retrieve", action="store_true", help="기존 Vector CLI와 호환되는 별칭")
    parser.add_argument("--top-k", type=int, default=None, help="최종 후보 수, 기본 10")
    parser.add_argument("--no-rerank", action="store_true", help="Cross-Encoder 비활성화 (RRF 결과 확인)")
    parser.add_argument("--show-fusion", action="store_true", help="RRF 중간 후보와 순위 출력")
    parser.add_argument("--show-stages", action="store_true", help="BM25/Vector 후보 상세 목록 출력")
    parser.add_argument("--json", action="store_true", help="사람용 표 대신 전체 응답 JSON 출력")
    parser.add_argument("--corpus", help="전체 BM25 TextSpan 코퍼스 JSONL/CSV (없으면 Chroma에서 구축)")
    parser.add_argument("--db-path", help="ChromaDB 저장 폴더 (상대경로면 프로젝트 루트 기준)")
    parser.add_argument("--collection", default="museum_documents", help="Chroma Collection 이름")
    parser.add_argument("--vector-weight", type=float, help="RRF Vector 가중치")
    parser.add_argument("--bm25-weight", type=float, help="RRF BM25 가중치")
    parser.add_argument("--fusion-top-k", type=int, help="RRF 후보 제한 (기본 20)")
    parser.add_argument("--rrf-k", type=int, help="RRF 순위 상수 (기본 60)")
    args = parser.parse_args()

    if args.info:
        print(json.dumps(AGENT_CARD, ensure_ascii=False, indent=2))
        return

    try:
        query = args.query if args.query is not None else input("검색 질문: ")
    except EOFError:
        parser.error("검색 질문을 인자로 전달하거나 콘솔 입력을 제공하세요.")

    try:
        from src.hybrid.config import HybridConfig
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        cfg = HybridConfig.from_env()
        overrides = {
            "vector_weight": args.vector_weight,
            "bm25_weight": args.bm25_weight,
            "fusion_top_k": args.fusion_top_k,
            "rrf_k": args.rrf_k,
        }
        cfg = replace(cfg, **{key: value for key, value in overrides.items() if value is not None})
        requested_k = cfg.final_top_k if args.top_k is None else args.top_k
        agent = HybridRAGAgent(
            config=cfg,
            corpus_source="file" if args.corpus else "chroma",
            corpus_path=args.corpus,
            chroma_db_path=args.db_path,
            chroma_collection_name=args.collection,
        )
        result = agent.retrieve(
            query,
            top_k=requested_k,
            rerank=not args.no_rerank,
            include_fusion_candidates=args.show_fusion,
            include_retrieval_candidates=args.show_stages,
        )
    except Exception as exc:
        parser.exit(1, f"[Hybrid RAG 오류] {type(exc).__name__}: {exc}\n")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_preview(result, show_fusion=args.show_fusion, show_stages=args.show_stages)


if __name__ == "__main__":
    main()
