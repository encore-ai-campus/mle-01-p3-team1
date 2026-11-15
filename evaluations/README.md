# 평가셋과 실행 안내

평가셋은 `datasets/`, 평가 코드는 `src/evaluation/`, 실행 결과는 `outputs/evaluation/`에 둡니다. 현재 초안의 `draft_needs_human_review` 라벨은 검수 전이므로 점수는 잠정치입니다.

| 평가 | 평가셋 | 실행 코드 | 결과 폴더 |
|---|---|---|---|
| Hybrid·Supervisor 비교 | [Supervisor v2 196문항](datasets/supervisor_v2/README.md) | `src.evaluation.hybrid.ragas_eval` | `outputs/evaluation/hybrid_ragas/` |
| Neo4j GraphRAG | [Neo4j 10문항](datasets/neo4j/README.md) | `src.evaluation.langgraph.ragas_eval` | `outputs/evaluation/neo4j_multihop_ragas/` |
| Vector 검색 순위 | [Vector 30문항](datasets/vector_db/README.md) | `src.evaluation.vector_db.evaluate` | `outputs/evaluation/vector_db/` |
| 가드레일 UI 평가 | [가드레일 평가표](datasets/guardrails/가드레일_평가_v1.md) | `src.guardrails.eval_guardrails` | `outputs/evaluation/guardrails/` |

실행 명령은 [루트 README](../README.md), 세부 설정과 이어하기는 [평가 문서](../docs/evaluation/README.md)를 참고하세요. 가드레일 평가는 기존 Streamlit UI용 스크립트이며 실행마다 새 폴더에 결과를 저장합니다. 예전 결과는 [보관된 평가 이력](reports/guardrails/README.md)에서 볼 수 있습니다.

보관하는 평가 결과는 [평가 결과 이력](reports/README.md)에 있습니다.

**2026-11-14 변경**
- 검색 흐름이 바뀌어 기본 평가셋을 [v2](datasets/supervisor_v2/README.md)로 교체했습니다. 이전 평가셋은 [archive](datasets/archive/README.md), 이전 결과는 [평가 기준선](reports/baseline_2026-11-13/README.md)에 보관합니다.
- 실제 흐름 전체(자동 라우팅 + 후보 필터 + Neo4j)는 `--modes supervisor_full`로 평가합니다.
