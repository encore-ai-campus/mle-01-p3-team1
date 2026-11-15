# 폴더 정리 기록

2026-11-13 기준으로 실행 중인 Hybrid 평가의 코드, DB, 평가셋과 결과 폴더는 이동하지 않았습니다. 주요 폴더 설명과 평가 색인은 각 폴더의 README에 연결했습니다.

- `src/agent/bm25_reranker.py`는 `src/hybrid/bm25_reranker.py`의 호환 import이며 두 구현을 따로 유지하는 파일이 아닙니다.
- `src/agent/ragas_eval.py`, `ragas_testset.py`는 `src/evaluation/langgraph/`의 호환 진입점입니다. 기존 명령과 테스트를 위해 유지합니다.
- `notebooks/vector_db/`의 두 노트북은 파일 해시가 달라 동일 파일로 취급하지 않았습니다.
- 생성된 흐름도 ZIP 두 개는 원본 이미지와 중복되어 제거했습니다. 이미지와 Mermaid 원본은 보존했으며 일부 오래된 흐름도는 현재 코드와 다를 수 있습니다.
- `outputs/`의 결과는 이동하지 않았으며 Git에서 제외합니다. `outputs/README.md`만 공유합니다.
- 현재 로컬의 `LangGraph_Ragas_150_draft.csv`, Neo4j 10문항 및 새 README 일부는 아직 Git에 추가되지 않은 파일입니다. 새 클론에 포함하려면 저장소에 별도로 반영해야 합니다.
- Chroma DB는 Git에서 일부 파일만 추적합니다. 완전한 DB 폴더를 별도 전달하거나 새로운 환경에서 구축해야 합니다.

실제 파일 변경과 평가 연결을 재검토하려면 현재 실행이 끝난 뒤 전체 테스트와 새 환경 설치를 별도로 확인하세요.

## 2026-11-14 후속 정리

평가 종료 후 가드레일 평가셋은 `evaluations/datasets/guardrails/`, 이전 평가 보고서는 `evaluations/reports/guardrails/`로 옮겼습니다. 새 가드레일 결과는 `outputs/evaluation/guardrails/`에 실행별로 저장합니다. Neo4j 적재 보고서는 `docs/records/neo4j-load-report.md`로 옮겼습니다. 각 이동은 기존 파일 내용을 보존합니다.

현재 코드와 다른 옛 구조 이미지 5개와 그 오래된 묶음 문서를 제거했습니다. 최신 Supervisor·Hybrid 설계도, 선택 연결/UI 설계도와 별도 UI 흐름 이미지는 유지합니다.

## 2026-11-14 문서 재배치

문서를 **읽는 목적**별 폴더로 나눴습니다. 성격이 비슷하거나 겹치는 문서는 지우지 않고 같은 폴더로 모았습니다. 파일 내용은 바꾸지 않았고, 상대 링크만 새 위치에 맞게 다시 계산했습니다. 루트 경로로 적힌 언급(`docs/...`)도 함께 고쳤습니다.

| 이전 위치 | 새 위치 | 이유 |
|---|---|---|
| `docs/architecture/region-theme-routing.md` | `docs/rationale/region-theme-routing.md` | 설계 근거 |
| `docs/architecture/ontology-filter-routing.md` | `docs/rationale/ontology-filter-routing.md` | 설계 근거 |
| `docs/operations/supervisor-retrieval-issues/README.md` | `docs/rationale/supervisor-retrieval-issues.md` | 문제 해결 기록 |
| `docs/evaluation/neo4j_context_recall_analysis.md` | `docs/rationale/neo4j-context-recall-analysis.md` | 문제 해결 기록 |
| `docs/evaluation/post-eval-supervisor-neo4j.md` | `docs/rationale/post-eval-supervisor-neo4j.md` | 문제 해결 기록 |
| `docs/superpowers/specs/*-design.md` (3개) | `docs/rationale/` | 시점별 설계 보고서 |
| `docs/superpowers/plans/*.md` (6개) | `docs/plans/` | 구현 계획 |
| `docs/operations/neo4j/IMPLEMENTATION_PLAN.md` | `docs/plans/neo4j-load-implementation-plan.md` | 구현 계획 |
| `docs/architecture/cleanup-audit.md` | `docs/records/cleanup-audit.md` | 작업 기록 |
| `docs/operations/neo4j/LOAD_REPORT.md` | `docs/records/neo4j-load-report.md` | 작업 기록 |
| `docs/superpowers/README.md` | `docs/records/superpowers-folder-note.md` | 예전 폴더 안내문 보존 |
| `docs/superpowers/plans/README.md`, `specs/README.md` | `docs/plans/README.md`, `docs/rationale/README.md` | 새 색인으로 다시 씀 |

- `docs/superpowers/` 폴더와 `docs/operations/supervisor-retrieval-issues/` 폴더는 비어서 없어졌습니다.
- 파일은 일반 이동으로 옮겼고 Git 인덱스는 건드리지 않았습니다. 커밋할 때 `git add -A docs`로 올리면 Git이 이름 변경으로 인식합니다.
- superpowers 플러그인을 다시 쓰면 새 설계·계획 문서가 `docs/superpowers/`에 생깁니다. 그때는 위 기준대로 `rationale/`, `plans/`로 옮기면 됩니다.

### 코드 쪽 중복은 옮기지 않음

코드에서 비슷하거나 겹쳐 보이는 파일은 import 경로와 실행 명령이 걸려 있어 옮기지 않았습니다. 위 2026-11-13 기록과 같은 이유입니다.

| 파일 | 실제 관계 | 옮기지 않은 이유 |
|---|---|---|
| `src/agent/bm25_reranker.py` | `src/hybrid/bm25_reranker.py`를 다시 내보내는 호환 import | 기존 import 경로 유지 |
| `src/agent/ragas_eval.py`, `ragas_testset.py` | `src/evaluation/langgraph/`의 호환 진입점 | 기존 실행 명령과 테스트 유지 |
| `src/agent/region_normalization.py` | `src/region_aliases.py`를 쓰는 Neo4j·Supervisor용 헬퍼 | `neo4j_search.py`, `neo4j_text2cypher.py`, `supervisor/adapters.py`가 import |
| `src/*/requirements*.txt` (3개) | 모듈별 최소 설치 목록 | 각 README의 설치 명령이 경로를 참조 |
| `scripts/README.md`, `scripts/readme_for_scripts.md` | 앞의 것은 뒤의 것을 가리키는 색인 | 이미 같은 폴더에 있음 |

## 2026-11-14 문서 가독성 정리

내용과 수치는 그대로 두고, 읽는 순서와 형식만 바꿨습니다. 날짜가 붙은 설계 보고서와 `plans/`는 당시 기록이라 원문을 유지했습니다.

- **요약 먼저:** `supervisor-retrieval-issues.md`(문제별 요약표), `neo4j-context-recall-analysis.md`, `region-theme-routing.md`, `supervisor-integration.md`(한눈에 보기) 맨 위에 요약을 넣었습니다.
- **긴 문단과 표 칸을 목록으로 풀기:** 위 문서들의 300자가 넘는 문단을 증상, 원인, 수정, 결과 같은 항목별 목록으로 나눴습니다.
- **중복은 기준 문서 하나 + 링크:**
  - 지역·주제 질문의 수치: `region-theme-routing.md`
  - 후보 필터와 Neo4j 일치 점검: `ontology-filter-routing.md`
  - v2 적재 후 상태: `ontology-v2.md`
- **현재 동작 반영:** `supervisor-integration.md`의 흐름도에 후보 필터, 기록 없음 보류, 가드레일을 추가했고, 속성 근거 필드 목록도 갱신했습니다.
- **파일 이름 하이픈 통일:** `langgraph_ragas.md` → `langgraph-ragas.md`, `vector_db.md` → `vector-db.md`, `neo4j_context_recall_analysis.md` → `neo4j-context-recall-analysis.md`. 저장소 안의 링크 14곳을 함께 고쳤습니다.

## 2026-11-14 평가셋 재구축과 이전 결과 보관

검색 흐름(후보 필터, Neo4j v2, 기관 Graph, 기록 없음 보류)이 바뀌어 기본 Ragas 평가셋을 새로 만들고, 이전 평가셋과 결과는 지우지 않고 보관했습니다.

| 항목 | 이전 위치 | 새 위치 |
|---|---|---|
| v1 150문항, 30문항, 폴더 안내문 | `evaluations/datasets/langgraph/` | `evaluations/datasets/archive/v1_2026-11-13/langgraph/` (내용 그대로, sha256은 보관 README에 기록) |
| 이전 평가 결과 요약 | `outputs/evaluation/…` (Git 제외) | `evaluations/reports/baseline_2026-11-13/`에 **복사**. 원본은 그대로 둠 |
| 새 기본 평가셋 | — | `evaluations/datasets/supervisor_v2/Supervisor_Ragas_v2_draft.csv` (v1 150 + 새 흐름 46 = 196) |

- 생성기 `src/evaluation/build_evalset_v2.py`를 추가했습니다. CSV와 v2 규칙으로 새 문항의 정답을 결정적으로 계산합니다.
- 평가 코드의 기본 평가셋을 v2로 바꿨습니다(`hybrid/ragas_eval.py`, `langgraph/ragas_eval.py`). `ragas_testset`의 시드는 보관된 30문항을 가리킵니다.
- 실제 CLI 흐름 전체를 평가하는 `supervisor_full` 모드를 추가했습니다. 기존 `supervisor` 모드는 경로를 Hybrid로 고정한 비교용으로 그대로 둡니다.
- `connect.build_connected_supervisor`에 `region_theme_routing` 인자를 추가했습니다. 평가처럼 Hybrid 결과를 재생하는 경우에도 CLI와 같은 고정 경로를 쓰도록 하기 위해서입니다.
- Neo4j 10문항과 Vector 30문항은 이번 흐름 변경과 무관해서 그대로 사용합니다.

## 2026-11-14 평가 결과 기록과 수정 내역

- 첫 `supervisor_full` v2 평가의 요약과 문항별 핵심 열 CSV를 `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/`에 복사했습니다. 원본 실행 폴더는 로컬 `outputs/`에 그대로 있습니다.
- 평가 결과로 드러난 문제 8건의 근거와 해결 방법은 `docs/rationale/supervisor-retrieval-issues.md`에 정리했습니다.
- 새 환경변수 `HYBRID_NAME_MATCH`, `HYBRID_RERANK_MIN_CONFIDENCE`를 `.env.example`과 `src/hybrid/README.md`에 적었습니다.


## 2026-11-14 승인 후 문서 통합

문서만 변경했습니다. Python·테스트 코드·CSV·DB·평가 원본은 변경하지 않았습니다. 미완료 계획은 완료로 간주하지 않았습니다. 소스 README의 고유 안내는 상위 문서에 보존했습니다.

| 이전 문서 | 처리 | 현재 위치·이유 |
|---|---|---|
| `README.md` | 유지 | `README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `data/README.md` | 유지 | `data/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `data/processed/README.md` | 통합 | `data/README.md` — 상위 안내에 원문 내용 보존 |
| `data/raw/README.md` | 통합 | `data/README.md` — 상위 안내에 원문 내용 보존 |
| `data/vector_db/README.md` | 유지 | `data/vector_db/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/README.md` | 유지 | `docs/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/architecture/README.md` | 유지 | `docs/architecture/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/architecture/folder-structure.md` | 유지 | `docs/architecture/folder-structure.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/architecture/images/README.md` | 유지 | `docs/architecture/images/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/architecture/ontology-v2.md` | 유지 | `docs/architecture/ontology-v2.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/architecture/supervisor-integration.md` | 유지 | `docs/architecture/supervisor-integration.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/evaluation/README.md` | 유지 | `docs/evaluation/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/evaluation/hybrid-ragas.md` | 유지 | `docs/evaluation/hybrid-ragas.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/evaluation/langgraph-ragas.md` | 유지 | `docs/evaluation/langgraph-ragas.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/evaluation/vector-db.md` | 유지 | `docs/evaluation/vector-db.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/operations/README.md` | 유지 | `docs/operations/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/operations/neo4j/README.md` | 유지 | `docs/operations/neo4j/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/plans/2026-11-12-langgraph-ragas-parallel-collection.md` | 보관 | `docs/archive/plans/2026-11-12-langgraph-ragas-parallel-collection.md` — 독자 목적에 따른 분류 |
| `docs/plans/2026-11-13-chroma-sido-alias-normalization.md` | 보관 | `docs/archive/plans/2026-11-13-chroma-sido-alias-normalization.md` — 독자 목적에 따른 분류 |
| `docs/plans/2026-11-13-museum-bm25-hybrid.md` | 유지 | `docs/plans/2026-11-13-museum-bm25-hybrid.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/plans/2026-11-13-repository-user-guide.md` | 유지 | `docs/plans/2026-11-13-repository-user-guide.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/plans/2026-11-13-supervisor-hybrid-integration.md` | 유지 | `docs/plans/2026-11-13-supervisor-hybrid-integration.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/plans/2026-11-14-supervisor-context.md` | 유지 | `docs/plans/2026-11-14-supervisor-context.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/plans/README.md` | 유지 | `docs/plans/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/plans/neo4j-load-implementation-plan.md` | 유지 | `docs/plans/neo4j-load-implementation-plan.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/rationale/2026-11-12-langgraph-ragas-parallel-collection-design.md` | 이동 | `docs/decisions/2026-11-12-langgraph-ragas-parallel-collection-design.md` — 독자 목적에 따른 분류 |
| `docs/rationale/2026-11-13-chroma-sido-alias-normalization-design.md` | 이동 | `docs/decisions/2026-11-13-chroma-sido-alias-normalization-design.md` — 독자 목적에 따른 분류 |
| `docs/rationale/2026-11-13-museum-bm25-hybrid-design.md` | 이동 | `docs/decisions/2026-11-13-museum-bm25-hybrid-design.md` — 독자 목적에 따른 분류 |
| `docs/rationale/README.md` | 이동 | `docs/decisions/README.md` — 독자 목적에 따른 분류 |
| `docs/rationale/neo4j-context-recall-analysis.md` | 이동 | `docs/records/neo4j-context-recall-analysis.md` — 독자 목적에 따른 분류 |
| `docs/rationale/ontology-filter-routing.md` | 이동 | `docs/decisions/ontology-filter-routing.md` — 독자 목적에 따른 분류 |
| `docs/rationale/post-eval-supervisor-neo4j.md` | 이동 | `docs/records/post-eval-supervisor-neo4j.md` — 독자 목적에 따른 분류 |
| `docs/rationale/region-theme-routing.md` | 이동 | `docs/decisions/region-theme-routing.md` — 독자 목적에 따른 분류 |
| `docs/rationale/supervisor-retrieval-issues.md` | 이동 | `docs/records/supervisor-retrieval-issues.md` — 독자 목적에 따른 분류 |
| `docs/records/README.md` | 유지 | `docs/records/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/records/cleanup-audit.md` | 유지 | `docs/records/cleanup-audit.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/records/neo4j-load-report.md` | 유지 | `docs/records/neo4j-load-report.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `docs/records/superpowers-folder-note.md` | 유지 | `docs/records/superpowers-folder-note.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/README.md` | 유지 | `evaluations/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/README.md` | 유지 | `evaluations/datasets/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/archive/README.md` | 유지 | `evaluations/datasets/archive/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/archive/v1_2026-11-13/README.md` | 유지 | `evaluations/datasets/archive/v1_2026-11-13/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/archive/v1_2026-11-13/langgraph/README.md` | 유지 | `evaluations/datasets/archive/v1_2026-11-13/langgraph/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/guardrails/README.md` | 유지 | `evaluations/datasets/guardrails/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/guardrails/가드레일_평가_v1.md` | 유지 | `evaluations/datasets/guardrails/가드레일_평가_v1.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/neo4j/README.md` | 유지 | `evaluations/datasets/neo4j/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/supervisor_v2/README.md` | 유지 | `evaluations/datasets/supervisor_v2/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/datasets/vector_db/README.md` | 유지 | `evaluations/datasets/vector_db/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/README.md` | 유지 | `evaluations/reports/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/README.md` | 유지 | `evaluations/reports/baseline_2026-11-13/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/hybrid_ragas/run_20261113_124252_summary.md` | 유지 | `evaluations/reports/baseline_2026-11-13/hybrid_ragas/run_20261113_124252_summary.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_152004/report.md` | 유지 | `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_152004/report.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_160623/report.md` | 유지 | `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_160623/report.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_163133/report.md` | 유지 | `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_163133/report.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_170150/report.md` | 유지 | `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_170150/report.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/baseline_2026-11-13/vector_db/20261113_174527/report.md` | 유지 | `evaluations/reports/baseline_2026-11-13/vector_db/20261113_174527/report.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/guardrails/README.md` | 유지 | `evaluations/reports/guardrails/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/guardrails/가드레일_평가_v1_결과_20261113_2134.md` | 유지 | `evaluations/reports/guardrails/가드레일_평가_v1_결과_20261113_2134.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/README.md` | 유지 | `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/summary.md` | 유지 | `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/summary.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `notebooks/README.md` | 유지 | `notebooks/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `notebooks/vector_db/README.md` | 통합 | `notebooks/README.md` — 상위 안내에 원문 내용 보존 |
| `outputs/README.md` | 유지 | `outputs/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `scripts/README.md` | 유지 | `scripts/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `scripts/readme_for_scripts.md` | 통합 | `scripts/README.md` — 상위 안내에 원문 내용 보존 |
| `src/README.md` | 유지 | `src/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/agent/README.md` | 유지 | `src/agent/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/agent/supervisor/README.md` | 유지 | `src/agent/supervisor/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/data_pipeline/README.md` | 유지 | `src/data_pipeline/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/data_pipeline/neo4j/README.md` | 통합 | `src/data_pipeline/README.md` — 상위 안내에 원문 내용 보존 |
| `src/data_pipeline/neo4j/ontology_v2/README.md` | 유지 | `src/data_pipeline/neo4j/ontology_v2/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/data_pipeline/vector_db/README.md` | 통합 | `src/data_pipeline/README.md` — 상위 안내에 원문 내용 보존 |
| `src/evaluation/README.md` | 유지 | `src/evaluation/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/evaluation/hybrid/README.md` | 통합 | `src/evaluation/README.md` — 상위 안내에 원문 내용 보존 |
| `src/evaluation/langgraph/README.md` | 통합 | `src/evaluation/README.md` — 상위 안내에 원문 내용 보존 |
| `src/evaluation/vector_db/README.md` | 통합 | `src/evaluation/README.md` — 상위 안내에 원문 내용 보존 |
| `src/guardrails/README.md` | 유지 | `src/guardrails/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/guardrails/config/README.md` | 통합 | `src/guardrails/README.md` — 상위 안내에 원문 내용 보존 |
| `src/hybrid/README.md` | 유지 | `src/hybrid/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/service/README.md` | 유지 | `src/service/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `src/service/static/README.md` | 통합 | `src/service/README.md` — 상위 안내에 원문 내용 보존 |
| `src/service/static/fonts/README.md` | 통합 | `src/service/README.md` — 상위 안내에 원문 내용 보존 |
| `src/service/ui/README.md` | 통합 | `src/service/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/README.md` | 유지 | `tests/README.md` — 독립 안내 또는 역사·검증 근거 보존 |
| `tests/integration/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/integration/neo4j/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/integration/vector_db/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/agent/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/data_pipeline/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/data_pipeline/neo4j/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/evaluation/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/evaluation/langgraph/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/evaluation/vector_db/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |
| `tests/unit/service/README.md` | 통합 | `tests/README.md` — 상위 안내에 원문 내용 보존 |

완료: 기술 결정/검증 기록 분리, 짧은 README 통합, 두 계획 보관, 현재 라우팅·평가 버전 설명 보완. 원본 평가 보고서는 내용 그대로 보존했습니다.

 
### 정리 후 확인과 인계

- 작업 시작 시 목록은 95개 MD였습니다. 이전 검토의 93개 이후 추가된 평가 보고서 안내도 보존했습니다.
- 11개 문서를 목적에 따라 이동했고, 24개 하위 안내를 상위 문서로 통합했습니다. 보관 계획 색인 1개를 추가해 최종 72개 MD, README 39개입니다.
- 평가 원본 report/summary 및 데이터는 수정하지 않았습니다. 평가 보고서 폴더의 README 두 개는 이동된 해설 문서의 링크만 수정했습니다.
- 현재 설명의 196문항, 규칙 기반 후보 필터, Graph 재시도, 별도 Streamlit 경로를 보완했습니다.
- 기존 이미지의 갱신 필요 범위를 images/README.md에 명시했습니다. 이미지 자체의 재생성은 이번 문서 작업에 포함하지 않았습니다.
- 미완료·상태 확인 보류 계획은 docs/plans에 유지했습니다. 과거 계획을 새 실행 명령으로 바꾸지 않았습니다.
- Python 소스·테스트·CSV·DB는 변경하지 않았고, 이 문서 작업에서는 테스트나 DB/API 실행도 하지 않았습니다.

## 2026-11-14 문서 재배치 점검과 보완

- `rationale/` → `decisions/`(기술 선택)와 `records/`(실패 분석·검증), 구현된 계획은 `archive/plans/`, 짧은 하위 README 통합으로 MD가 93개에서 72개가 됐습니다. 이후 상대경로 링크와 제목 앵커 검사에서 깨진 항목은 없었습니다.
- 점검 중 남아 있던 옛 표현을 고쳤습니다.
  - 라우팅 설명을 코드의 적용 순서(지정 경로 → 지역+주제 → 후보 필터 → 준비된 Graph 쿼리 → LLM)와 재시도 규칙으로 다시 썼습니다. 이전에는 "지역·요금은 Graph 우선"으로 적혀 있었습니다.
  - `rationale` 이름이 남은 안내를 새 위치로 고쳤습니다.
  - Graph 단독 평가, Hybrid 고정 평가, `supervisor_full`이 서로 다른 것을 잰다는 표를 추가했습니다.
- 기준선과 첫 v2 평가에 실행 조건 표를 추가했고, 기록의 검증 수준 구분은 `docs/records/README.md`에 두었습니다.
- 이번 점검에서 소스코드·테스트·데이터는 바꾸지 않았습니다.

## 2026-11-14 남은 항목 처리 (문서 분류표, 구조 이미지)

- **문서 분류표:** 모든 Markdown 73개를 유지 43 · 보관 23 · 판단 보류 6 · 통합 후보 1 · 삭제 후보 0으로 분류했습니다([doc-inventory.md](doc-inventory.md)). 이동·삭제는 하지 않았습니다.
- **연결이 끊긴 문서:** 다른 문서에서 링크되지 않던 문서 10개(평가 결과 요약과 보고서, `evaluations/reports/README.md`, `data/vector_db/README.md`)에 링크를 연결했습니다.
- **현재 코드와 다른 문서:** 구현 전 BM25 설계·계획 2개가 만들어지지 않은 파일을 가리켜, 상단에 차이를 알리는 한 줄을 추가했습니다. 원문은 바꾸지 않았습니다.
- **구조 이미지:** 갱신 전 흐름도(2026-11-13)는 `docs/architecture/images/archive/`로 보관하고, `supervisor-hybrid-flow-clarified.png`와 `.mmd`를 현재 라우팅(후보 필터, 이름 보장, 재정렬 확신도, 준비된 쿼리 우선, Graph 실패 시 Hybrid, 기록 없음 보류)에 맞게 새로 만들었습니다. PNG는 `images/draw_supervisor_flow.py`로 다시 그릴 수 있고, `.mmd`에서 렌더링한 것이 아니라서 흐름이 바뀌면 둘 다 고쳐야 합니다.
- 소스코드·테스트·데이터는 바꾸지 않았습니다(구조 이미지를 그리는 스크립트만 문서 폴더에 추가).
