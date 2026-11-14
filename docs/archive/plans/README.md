# 보관한 구현 계획

2026-11-14 문서 정리에서 완료 체크와 현재 구현을 대조한 계획입니다. 현재 설치·실행 명령은 루트 README를 사용합니다. 보관은 새 실환경 평가가 통과했다는 뜻이 아닙니다.

| 계획 | 확인한 구현·검증 근거 | 검증 범위 |
|---|---|---|
| [병렬 평가](2026-11-12-langgraph-ragas-parallel-collection.md) | src/evaluation/langgraph/ragas_eval.py의 collect_graph_results, tests/unit/evaluation/langgraph/test_ragas_eval.py | 스레드별 앱, 결과 순서, 진행 표시 구현과 관련 테스트 확인 |
| [지역 별칭](2026-11-13-chroma-sido-alias-normalization.md) | src/region_aliases.py, src/service/vector_search_chroma.py, src/hybrid/bm25_retriever.py, src/service/ui/data.py | 공용 별칭 사용 확인. 원 계획의 검증 범위는 정적 검사와 읽기 전용 메타데이터 확인 |

원문 체크리스트와 당시 검증 수준은 보존했습니다.
