# 평가 기준선 (2026-11-13, 흐름 변경 이전)

2026-11-14에 온톨로지 후보 필터, Neo4j v2, 기관 고정 쿼리, 기록 없음 보류가 추가되기 **전의** 평가 결과입니다. 새 흐름과 비교할 기준선으로 보관합니다.

- 원본 실행 폴더는 로컬 `outputs/evaluation/`에 그대로 있습니다. 여기에는 Git으로 공유할 수 있게 요약 파일만 복사했습니다.
- Hybrid의 문항별 결과(`per_question.csv`, 4.4MB)와 캐시는 용량 때문에 복사하지 않았습니다.
- 요약 파일에 적힌 평가셋 경로(`evaluations/datasets/langgraph/...`)는 실행 당시 위치입니다. 지금은 `evaluations/datasets/archive/v1_2026-11-13/langgraph/`에 있습니다.
- 모든 평가셋 라벨이 사람 검수 전(`draft_needs_human_review`)이라 **점수는 잠정치**입니다.

## 요약

| 평가 | 평가셋 | 실행 | 핵심 결과 |
|---|---|---|---|
| Hybrid Cross-Encoder | v1 150문항 | `run_20261113_124252` (top-k 5, `gpt-6-luna`) | Hit@1 0.972 · Recall@5 0.986 · MRR@10 0.979 · Faithfulness 0.950 · Context Recall 0.983 · Context Precision 0.963 · 부당 보류율 0.000 · 평균 141초 |
| Neo4j GraphRAG | Neo4j 10문항 | 4회 (`run_20261113_152004` → `170150`) | 4차: Faithfulness 0.978 · Context Recall 0.850 · Context Precision 0.950 · 정답 ID recall 0.900 |
| Vector 검색 순위 | Vector 30문항 | `20261113_174527` | Hit@1 0.708 · Hit@5 0.792 · Recall@5 0.792 · MRR@10 0.755 |

**해석할 때 주의할 점**
- **Hybrid:** 답변 불가 6문항 모두 검색 결과가 나와 `거짓 검색률`이 1.000입니다. 보류는 답변·검증 단계에서 판단합니다. 이 실행은 Supervisor 모드를 포함하지 않았습니다.
- **Neo4j:** 네 번의 실행 사이에 코드와 `top-k`가 바뀌어, 점수 변화를 코드만의 효과로 볼 수 없습니다. 문항별 분석은 [Neo4j Context Recall 분석](../../../docs/records/neo4j-context-recall-analysis.md)에 있습니다.
- **Vector:** 순위만 측정하며 답변 품질은 측정하지 않습니다.

## 실행 조건 (Hybrid 150문항)

| 항목 | 값 |
|---|---|
| 실행 | `run_20261113_124252_352465Z` |
| 평가셋 | v1 150문항, sha256 `3ab95ff0acadf714…`, 라벨 150개 모두 `draft_needs_human_review` |
| 모드 / top-k | `hybrid_rerank` (경로 Hybrid 고정) / 5 |
| 모델 | 답변·Supervisor·Graph·Ragas judge 모두 `gpt-6-luna` |
| 병렬도 | 질문 8개, Ragas 4개 |
| 검색 설정 | Vector 20 + BM25 20 → 가중 RRF(k=60, 가중치 1:1) 20 → `BAAI/bge-reranker-v2-m3` 재정렬. 코드 기본값이며 `.env` 재정의는 기록되지 않았음 |
| 후보 필터 · 이름 보장 · 재정렬 확신도 판단 | 없음 (이후에 추가됨) |
| Neo4j | 사용하지 않음 |
| 시간 | 평균 141초, 최대 203초, Ragas 채점 2,131초 |
| 코드 상태 | 브랜치 `codex/project-structure-reorganization`, 이 평가 이후 흐름이 바뀌었음 (당시 커밋은 따로 기록되지 않음) |

## 파일

| 폴더 | 내용 |
|---|---|
| `hybrid_ragas/` | [요약](hybrid_ragas/run_20261113_124252_summary.md), `_summary.csv` |
| `neo4j_multihop_ragas/run_*/` | 실행별 보고서: [1차](neo4j_multihop_ragas/run_20261113_152004/report.md), [2차](neo4j_multihop_ragas/run_20261113_160623/report.md), [3차](neo4j_multihop_ragas/run_20261113_163133/report.md), [4차](neo4j_multihop_ragas/run_20261113_170150/report.md). 각 폴더에 `summary.json`, `per_question.csv`도 있음 |
| `vector_db/20261113_174527/` | [보고서](vector_db/20261113_174527/report.md), `summary.json`, `per_question.csv`, `missed_at_5.csv` |

## 이후 평가와 비교하는 방법

- v2 평가셋에 v1의 150문항이 같은 ID로 들어 있습니다. `source_set == v1_2026-11-13`인 문항만 골라 위 Hybrid 결과와 비교하면 같은 문항 기준의 회귀 확인이 됩니다.
- Neo4j 10문항과 Vector 30문항은 평가셋이 바뀌지 않았으므로 그대로 다시 실행해 비교합니다.
