"""벡터 검색 서비스 진입점: LLM 분석 -> ChromaDB 후보 검색 -> LLM 관련성 평가.

다른 코드에서는 이 파일의 VectorSearchService만 가져오면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI

# 모듈 import와 Python 파일 직접 실행을 모두 지원한다.
# - import: from src.service.vertor_search_service import VectorSearchService
# - 실행: python src/service/vertor_search_service.py
if __name__ == "__main__" and not __package__:
    import sys

    # 직접 실행하면 상대 import가 동작하지 않으므로 프로젝트 루트를 등록한다.
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.service.vertor_search_analyzer import (
        QueryAnalyzer,
        QueryExpansion,
        SearchPlan,
    )
    from src.service.vertor_search_chroma import ChromaSearchTool
else:
    from .vertor_search_analyzer import (
        QueryAnalyzer,
        QueryExpansion,
        SearchPlan,
    )
    from .vertor_search_chroma import ChromaSearchTool


@dataclass(frozen=True)
class VectorSearchResponse:
    """검색 결과뿐 아니라 실제 적용한 검색 계획과 주의사항도 반환한다."""

    plan: SearchPlan
    where: dict[str, Any] | None
    results: list[dict[str, Any]]
    warnings: tuple[str, ...]
    # ChromaDB 후보 검색과 LLM 평가 절차를 외부에서도 관찰할 수 있게 한다.
    candidate_count: int = 0
    excluded_count: int = 0
    reranked: bool = False
    requested_candidate_k: int = 0


CANDIDATE_MULTIPLIER = 4
MAX_CANDIDATES = 40


class VectorSearchService:
    """외부 호출용 서비스: 검색 계획 생성과 실행을 분리해서 제공한다."""

    def __init__(
        self,
        *,
        model: str | None = None,
        llm_client: OpenAI | None = None,
        embeddings: Any | None = None,
        db_path: str | Path | None = None,
        search_tool: ChromaSearchTool | None = None,
    ):
        # DB는 실제 검색할 때만 연결한다. 계획 분석만 하는 테스트도 가능하다.
        self.analyzer = QueryAnalyzer(model=model, llm_client=llm_client)
        self._search_tool = search_tool
        self._embeddings = embeddings
        self._db_path = db_path

    def analyze_query(
        self, query: str, *, fallback_on_error: bool = False
    ) -> SearchPlan:
        """LLM으로 질문을 분석한다. ChromaDB에는 접근하지 않는다."""
        return self.analyzer.analyze(query, fallback_on_error=fallback_on_error)

    def expand_query(
        self, query: str, *, fallback_on_error: bool = False
    ) -> QueryExpansion:
        """기존 검색어 확장 호출과 호환되는 간단한 인터페이스."""
        plan = self.analyze_query(query, fallback_on_error=fallback_on_error)
        status: Literal["expanded", "unchanged", "fallback"] = (
            "fallback" if plan.status == "fallback"
            else "unchanged" if plan.expanded_query == plan.original_query
            else "expanded"
        )
        return QueryExpansion(
            original_query=plan.original_query,
            expanded_query=plan.expanded_query,
            status=status,
            model=plan.model,
        )

    def execute_plan(
        self,
        plan: SearchPlan,
        *,
        top_k: int = 5,
        rerank: bool = True,
        fallback_on_rerank_error: bool = True,
        candidate_ids: list[str] | None = None,
    ) -> VectorSearchResponse:
        """계획 실행: ChromaDB 후보 검색 -> LLM 관련성 평가 -> 최종 결과 반환.

        - 의미 검색은 최종 결과의 4배(최대 40건)를 후보로 조회한다.
        - 메타데이터 검색만 있으면 LLM 평가 없이 top_k만 조회한다.
        - 0점 후보는 제외하며, 부족하다고 무관한 박물관으로 채우지 않는다.
        """
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= MAX_CANDIDATES:
            raise ValueError(f"top_k는 1~{MAX_CANDIDATES} 사이의 정수여야 합니다.")

        if self._search_tool is None:
            self._search_tool = ChromaSearchTool(
                embeddings=self._embeddings,
                db_path=self._db_path,
            )

        # 기존 메타데이터 조건은 ChromaDB에 먼저 적용한다.
        # LLM 재평가 시에만 최종 요청량보다 넉넉하게 검색한다.
        use_rerank = bool(rerank and plan.expanded_query.strip() and plan.status != "fallback")
        # top_k의 4배를 검색하되 40건을 넘지 않는다.
        # 메타데이터 전용 / 재평가 비활성 상태에서는 top_k건만 조회한다.
        search_k = min(top_k * CANDIDATE_MULTIPLIER, MAX_CANDIDATES) if use_rerank else top_k
        where, candidates = self._search_tool.search(
            semantic_query=plan.expanded_query,
            filters=plan.filters,
            top_k=search_k,
            candidate_ids=candidate_ids,
        )
        warnings = list(plan.unsupported_constraints)
        if any(
            value == 0 for value in (
                plan.filters.adult_fee_max,
                plan.filters.youth_fee_max,
                plan.filters.child_fee_max,
            )
        ):
            warnings.append(
                "관람료 0원은 기본 요금 자료일 수 있으니 실제 무료입장 여부를 재확인하세요."
            )
        if plan.status == "fallback":
            warnings.append("LLM 질문 분석 실패: 필터 없이 원문 의미 검색만 수행했습니다.")

        results = candidates[:top_k]
        excluded_count = 0
        reranked = False

        if use_rerank and candidates:
            try:
                assessments = self.analyzer.assess_candidates(
                    original_query=plan.original_query,
                    expanded_query=plan.expanded_query,
                    hits=candidates,
                )
                relevant_hits = []
                for hit in candidates:
                    grade, reason = assessments[hit["museum_id"]]
                    if grade == 0:
                        excluded_count += 1
                        continue
                    # 원본 dict를 수정하지 않고 관련성 정보가 붙은 결과를 생성한다.
                    relevant_hits.append({
                        **hit,
                        "relevance": grade,
                        "relevance_reason": reason,
                    })

                # 2점 -> 1점 순. 동일한 등급이면 기존 벡터 유사도 순위를 보존한다.
                relevant_hits.sort(key=lambda hit: -hit["relevance"])
                results = relevant_hits[:top_k]
                reranked = True
                if not results:
                    warnings.append("후보 중 질문과 관련된 박물관을 확인하지 못했습니다.")
                elif len(results) < top_k:
                    warnings.append(
                        f"관련 시설이 {len(results)}건만 확인되어 요청한 {top_k}건보다 적게 반환합니다."
                    )
            except Exception as exc:
                if not fallback_on_rerank_error:
                    raise RuntimeError("LLM 관련성 평가에 실패했습니다.") from exc
                # LLM 장애로 검색 자체가 실패하지 않도록 벡터 검색 결과를 반환한다.
                # 단, 재평가가 적용되지 않았다는 경고를 함께 기록한다.
                results = candidates[:top_k]
                excluded_count = 0
                warnings.append(
                    "관련성 평가 실패: LLM 필터를 적용하지 않고 벡터 유사도 순서로 반환합니다. "
                    f"({type(exc).__name__}: {exc})"
                )

        return VectorSearchResponse(
            plan=plan,
            where=where,
            results=results,
            warnings=tuple(dict.fromkeys(warnings)),
            candidate_count=len(candidates),
            excluded_count=excluded_count,
            reranked=reranked,
            requested_candidate_k=search_k,
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        rerank: bool = True,
        candidate_ids: list[str] | None = None,
        fallback_on_error: bool = False,
        fallback_on_rerank_error: bool = True,
    ) -> VectorSearchResponse:
        """일반 호출: 질문 분석 -> 후보 검색 -> 관련성 평가 -> 최종 결과."""
        plan = self.analyze_query(query, fallback_on_error=fallback_on_error)
        return self.execute_plan(
            plan,
            top_k=top_k,
            rerank=rerank,
            fallback_on_rerank_error=fallback_on_rerank_error,
            candidate_ids=candidate_ids,
        )


# ---------------------------------------------------------
# 직접 실행용 통합 테스트: 모의 객체 없이 실제 API와 DB를 사용
# ---------------------------------------------------------
def _main() -> None:
    """질문 입력 -> 실제 LLM 분석 -> 실제 ChromaDB 검색을 순서대로 확인한다."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="실제 OpenAI API 및 ChromaDB를 사용하는 벡터 검색 점검"
    )
    parser.add_argument(
        "query", nargs="?", help="검색 질문 (생략하면 콘솔에서 직접 입력)"
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="최종 검색 결과 상한 (1~40, 기본값: 5)"
    )
    parser.add_argument(
        "--no-rerank", action="store_true",
        help="LLM 관련성 평가를 건너뛰고 기존 벡터 검색 순위만 출력",
    )
    parser.add_argument(
        "--analyze-only", action="store_true",
        help="LLM 검색 계획 생성까지만 실행하고 ChromaDB 검색은 생략",
    )
    args = parser.parse_args()

    # 코드에 질문 예시를 고정하지 않는다. 사용자 입력만으로 테스트한다.
    try:
        query = args.query if args.query is not None else input("검색 질문: ")
    except EOFError:
        parser.error("검색 질문을 입력하거나 명령줄 인자로 전달하세요.")
    query = query.strip()
    if not query:
        parser.error("검색 질문을 입력해야 합니다.")
    if not 1 <= args.top_k <= MAX_CANDIDATES:
        parser.error("--top-k는 1~40 사이의 정수여야 합니다.")

    # 전체 검색에서는 DB 연결을 먼저 확인해 잘못된 경로 때문에
    # LLM 호출 비용이 낭비되는 것을 방지한다.
    search_tool = None if args.analyze_only else ChromaSearchTool()
    service = VectorSearchService(search_tool=search_tool)

    # 1. 실제 LLM API로 검색어 확장 및 메타데이터 조건 분리
    plan = service.analyze_query(query)
    print("\n" + "=" * 60)
    print("[LLM 검색 계획]")
    print("원본 질문:", plan.original_query)
    print("확장 검색어:", plan.expanded_query or "(없음: 메타데이터 검색 전용)")
    print("검색 방식:", plan.mode)
    print("사용 모델:", plan.model)
    print("메타데이터 조건:")
    print(json.dumps(
        plan.filters.model_dump(exclude_none=True),
        ensure_ascii=False, indent=2,
    ))
    if plan.unsupported_constraints:
        print("미지원 조건:", ", ".join(plan.unsupported_constraints))

    if args.analyze_only:
        print("\n--analyze-only: 실제 LLM 분석 확인 완료 (DB 검색 생략)")
        return

    # 2. 만들어진 계획을 그대로 검색 도구에 전달한다.
    #    의미 검색은 임베딩 API와 로컬 ChromaDB를 사용한다.
    #    관련성 평가를 켰다면 후보 검색 이후 LLM을 한 번 더 호출한다.
    response = service.execute_plan(
        plan,
        top_k=args.top_k,
        rerank=not args.no_rerank,
    )
    print("\n" + "=" * 60)
    print("[ChromaDB 검색 결과]")
    print("적용 필터:")
    print(json.dumps(response.where, ensure_ascii=False, indent=2))
    print(f"요청 후보 수: {response.requested_candidate_k}건")
    print(f"실제 검색 후보: {response.candidate_count}건")
    print(f"LLM 관련성 재평가: {'적용' if response.reranked else '미적용'}")
    print(f"무관한 후보 제외: {response.excluded_count}건")
    print(f"최종 검색 결과: {len(response.results)}건")

    for index, hit in enumerate(response.results, start=1):
        metadata = hit.get("metadata") or {}
        distance = hit.get("distance")
        distance_text = f"{distance:.4f}" if distance is not None else "(조건 검색)"
        relevance = hit.get("relevance")
        label = {2: "직접 관련", 1: "부분 관련"}.get(relevance, "미평가")
        print(
            f"{index:2d}. {metadata.get('name', '(이름 없음)')} "
            f"[ID: {hit['museum_id']}] "
            f"| 지역: {metadata.get('sido', '-')} "
            f"{metadata.get('sigungu', '')} "
            f"| 거리: {distance_text} | 관련성: {label}"
        )
        if hit.get("relevance_reason"):
            print(f"    평가 근거: {hit['relevance_reason']}")

    for warning in response.warnings:
        print("주의:", warning)


if __name__ == "__main__":
    _main()
