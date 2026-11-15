# 문서 분류표 (2026-11-14)

저장소의 모든 Markdown 73개를 목적·관련 코드·현재성에 따라 분류했습니다. 파일은 이동·삭제하지 않았고, 상단 안내 한 줄을 추가한 문서가 2개 있습니다(아래 표의 비고).

## 분류 기준

| 분류 | 판정 기준 |
|---|---|
| 유지 | 독립적인 독자·사용 목적이 있고 코드·데이터·검증 정보가 고유함 |
| 통합 후보 | 설명이 겹쳐 기준 문서 하나로 관리하는 편이 정확함. **아직 합치지 않음** |
| 보관 | 현재 사용법은 아니지만 당시 결정·실험 조건·결과를 설명함. 수정하지 않음 |
| 삭제 후보 | 고유 정보가 없고 필요한 내용과 링크가 다른 곳에 보존됨 |
| 판단 보류 | 중복·구현 상태·근거 보존 여부가 아직 확실하지 않음 |

## 결과 요약

| 분류 | 문서 수 |
|---|---:|
| 유지 | 43 |
| 보관 | 23 |
| 판단 보류 | 6 |
| 통합 후보 | 1 |
| 삭제 후보 | 0 |

- **삭제 후보는 0개입니다.** 모든 문서가 고유한 역할이 있거나 당시 기록입니다.
- **통합 후보 1개:** `docs/records/superpowers-folder-note.md`
- **판단 보류 6개:** 구현 완료 여부를 확인하지 못한 계획 5개와 `src/hybrid/README.md`. 계획 파일이 존재한다는 사실만으로 완료로 분류하지 않았습니다. `plans/README.md`에 판정 이유가 있습니다.

## 판정에 쓴 근거

- **코드 대조:** 각 문서가 backtick으로 가리키는 파일·모듈 경로가 실제로 존재하는지 확인했습니다. 존재하지 않는 경로를 가리킨 문서는 BM25 설계·계획 2개이며, 구현 전 설계라서 현재 코드와 다르다는 안내를 상단에 추가했습니다. `neo4j-load-report.md`와 `cleanup-audit.md`가 가리키는 없는 경로는 당시 상태와 이동 내역의 기록이라 정상입니다.
- **링크 대조:** 상대경로 링크와 제목 앵커가 모두 존재합니다. 아래 표의 '들어오는 링크'는 다른 문서에서 이 문서로 연결된 수입니다. 0이면 어디에서도 찾아갈 수 없는 문서입니다.
- **판정하지 않은 것:** 문서 본문의 모든 문장이 현재 코드와 일치하는지는 확인하지 않았습니다. 이 분류표는 문서의 역할과 현재성의 1차 판정입니다. 일치 여부를 확인한 문서는 비고에 적었습니다.
- **검증 수준:** 이 표는 문서만 대상으로 하며, 코드·테스트의 존재는 구현 완료나 실제 서비스 검증을 뜻하지 않습니다([검증 수준 구분](README.md#검증-수준과-기록에-남길-정보)).

## 루트와 docs

| 문서 | 목적 | 관련 코드·테스트 | 분류 | 들어오는 링크 | 비고 |
|---|---|---|---|---:|---|
| `README.md` | 설치·환경설정·대표 실행 명령 | `pyproject.toml`, `src/agent/supervisor/run.py`, `src/evaluation/hybrid/ragas_eval.py` | 유지 | 9 | 명령의 옵션(`supervisor_full`, `--no-ontology-filter`)이 코드의 `--help`에 있음 |
| `docs/README.md` | 독자 목적별 읽기 순서 | - | 유지 | 1 | docs 하위 7개 폴더 기준 문서로 연결 |
| `docs/architecture/README.md` | 구조 문서 색인 | - | 유지 | 2 | - |
| `docs/architecture/folder-structure.md` | 폴더 구조, 파일 역할, 전체 문서 위치 | `src/` 전체 | 유지 | 4 | 전체 문서 목록은 중복을 피하려고 이 분류표로 이관하고, 여기에는 기준 문서 찾기만 둠 |
| `docs/architecture/images/README.md` | 구조 이미지 상태와 갱신 방법 | `images/draw_supervisor_flow.py` | 유지 | 1 | 이번에 현재 상태로 갱신 |
| `docs/architecture/ontology-v2.md` | Neo4j 온톨로지 v2 스키마와 적재 상태 | `src/data_pipeline/neo4j/ontology_v2/`; `tests/unit/data_pipeline/neo4j/test_ontology_v2.py` | 유지 | 6 | Aura 적재 13개 항목 검증값과 일치(기록 시점) |
| `docs/architecture/supervisor-integration.md` | Supervisor·Hybrid·Neo4j 연결, 출처·속성 근거, 라우팅 순서 | `nodes.py`, `llm.py`, `connect.py`, `provenance.py`; `tests/unit/agent/test_supervisor_*.py` | 유지 | 8 | 라우팅 표를 `nodes.py`의 적용 순서에 맞게 다시 씀. 340줄로 긴 편이나 고유 내용 |
| `docs/archive/plans/2026-11-12-langgraph-ragas-parallel-collection.md` | Ragas 병렬 평가 구현 계획 | `src/evaluation/langgraph/ragas_eval.py`; `tests/unit/evaluation/langgraph/` | 보관 | 1 | 완료 체크와 구현·테스트가 대응함 |
| `docs/archive/plans/2026-11-13-chroma-sido-alias-normalization.md` | 시도 별칭 통합 구현 계획 | `src/region_aliases.py`; 별칭 관련 테스트 | 보관 | 1 | 완료 체크와 구현이 대응함 |
| `docs/archive/plans/README.md` | 보관 계획 색인 | - | 유지 | 2 | - |
| `docs/decisions/2026-11-12-langgraph-ragas-parallel-collection-design.md` | Ragas 평가의 병렬 수집 설계 | `src/evaluation/langgraph/ragas_eval.py` | 보관 | 1 | 당시 결정 기록 |
| `docs/decisions/2026-11-13-chroma-sido-alias-normalization-design.md` | 시도 별칭 통합 설계 | `src/region_aliases.py` | 보관 | 1 | 당시 결정 기록. 구현은 `src/region_aliases.py`에 존재 |
| `docs/decisions/2026-11-13-museum-bm25-hybrid-design.md` | BM25 Hybrid 구성과 대안 비교 | `src/hybrid/` | 보관 | 1 | 존재하지 않는 경로 5개를 가리킴 → 상단에 현재 코드와의 차이 안내 추가 |
| `docs/decisions/README.md` | 기술 결정 색인 | - | 유지 | 6 | - |
| `docs/decisions/ontology-filter-routing.md` | 온톨로지 후보 필터를 Hybrid 앞단에 둔 이유 | `src/hybrid/ontology_filter.py`; `tests/unit/agent/test_ontology_filter.py` | 유지 | 6 | 55개 조건 일치 점검 결과 포함 |
| `docs/decisions/region-theme-routing.md` | 지역+주제 질문을 Hybrid로 보내는 이유 | `src/hybrid/region_theme.py`; `tests/unit/agent/test_region_theme_search.py` | 유지 | 6 | 측정값은 2026-11-14 한 번의 실행 |
| `docs/evaluation/README.md` | 평가 문서 색인 | - | 유지 | 6 | - |
| `docs/evaluation/hybrid-ragas.md` | Hybrid·Supervisor·Graph 비교 평가 실행과 해석 | `src/evaluation/hybrid/ragas_eval.py`; `tests/unit/evaluation/` | 유지 | 3 | `supervisor_full` 모드 포함 |
| `docs/evaluation/langgraph-ragas.md` | Neo4j GraphRAG Ragas 평가 | `src/evaluation/langgraph/`; `tests/unit/evaluation/langgraph/` | 유지 | 3 | 세 평가가 다른 것을 잰다는 표 추가 |
| `docs/evaluation/vector-db.md` | Vector DB 평가셋과 순위 평가 | `src/evaluation/vector_db/` | 유지 | 4 | - |
| `docs/operations/README.md` | 운영 문서 색인 | - | 유지 | 1 | - |
| `docs/operations/neo4j/README.md` | CSV → Neo4j 기본 그래프 적재 | `src/data_pipeline/neo4j/load_neo4j.py`; `tests/unit/data_pipeline/neo4j/` | 유지 | 3 | v2 적재는 `ontology_v2/README.md`로 연결 |
| `docs/plans/2026-11-13-museum-bm25-hybrid.md` | BM25 Hybrid 구현 계획 (Graph 확장 포함) | `src/hybrid/` | 판단 보류 | 1 | 현재 구현과 범위가 다르고 가리키는 파일이 없음 → 완료로 분류하지 않음. 상단 안내 추가 |
| `docs/plans/2026-11-13-repository-user-guide.md` | 저장소 안내·정리 계획 | - | 판단 보류 | 1 | 이번 문서 정리와 겹침. 체크리스트 전체 충족 여부 미확인 |
| `docs/plans/2026-11-13-supervisor-hybrid-integration.md` | Supervisor–Hybrid 연동 계획 | `src/agent/supervisor/connect.py`; `tests/unit/agent/test_hybrid_integration.py` | 판단 보류 | 1 | 연결 코드는 있음. 원 계획 전체와 실환경 검증은 구분 필요(해당 테스트 1건이 이전부터 실패 중) |
| `docs/plans/2026-11-14-supervisor-context.md` | Supervisor 문맥 개선 계획 | `src/agent/supervisor/`; `tests/unit/agent/test_supervisor_context.py` | 판단 보류 | 1 | 관련 구현 있음. 잔여 항목 미확인 |
| `docs/plans/README.md` | 미완료·확인 보류 계획 색인 | - | 유지 | 2 | 계획별 판정 표 |
| `docs/plans/neo4j-load-implementation-plan.md` | Neo4j 적재기 구현 계획 | `src/data_pipeline/neo4j/` | 판단 보류 | 2 | 적재 보고서 존재. 계획 전체 완료 여부 미확인 |
| `docs/records/README.md` | 작업 기록 색인과 검증 수준 구분 | - | 유지 | 7 | - |
| `docs/records/cleanup-audit.md` | 폴더·문서 정리와 평가셋 재구축 내역 | - | 보관 | 2 | 215줄, 날짜별 이동 표. 가리키는 옛 경로는 이동 내역이라 정상 |
| `docs/records/doc-inventory.md` | 문서 전체의 분류표와 근거 | - | 유지 | 2 | 이 문서 |
| `docs/records/neo4j-context-recall-analysis.md` | Neo4j Context Recall 문항별 원인과 수정 | `src/agent/neo4j_text2cypher.py` | 보관 | 3 | 2026-11-13 4회 실행의 기록. 점수를 현재 결과로 덮어쓰지 않음 |
| `docs/records/neo4j-load-report.md` | Neo4j 기본 그래프 적재 이력과 DB 명세 | `src/data_pipeline/neo4j/` | 보관 | 3 | 구형 스키마의 당시 스냅샷. 존재하지 않는 외부 경로 2개는 당시 기록. 현재 확장은 `ontology-v2.md` |
| `docs/records/post-eval-supervisor-neo4j.md` | 평가 후 Supervisor–Neo4j 점검 메모 | - | 보관 | 2 | 당시 요금·출처 문제 기록 |
| `docs/records/superpowers-folder-note.md` | 예전 `docs/superpowers/` 폴더 안내문 | - | 통합 후보 | 1 | 3줄. 내용이 `plans/README.md`, `decisions/README.md`와 겹침. 합치기 전 들어오는 링크 확인 필요 |
| `docs/records/supervisor-retrieval-issues.md` | 검색·검증 문제의 증상·원인·해결 기록 | `nodes.py`, `llm.py`, `name_match.py`, `ragas_eval.py` | 유지 | 6 | 새 문제가 계속 추가되는 살아 있는 기록. 8건 중 5~8번은 재평가 전 |

## evaluations

| 문서 | 목적 | 관련 코드·테스트 | 분류 | 들어오는 링크 | 비고 |
|---|---|---|---|---:|---|
| `evaluations/README.md` | 평가셋·실행 코드·결과 대응표 | `src/evaluation/` | 유지 | 8 | - |
| `evaluations/datasets/README.md` | 평가셋 폴더별 상태 | - | 유지 | 2 | - |
| `evaluations/datasets/archive/README.md` | 보관된 평가셋 목록 | - | 보관 | 3 | - |
| `evaluations/datasets/archive/v1_2026-11-13/README.md` | v1 평가셋 설명과 파일 해시 | - | 보관 | 2 | 원본 CSV 해시로 변경 여부를 확인할 수 있음 |
| `evaluations/datasets/archive/v1_2026-11-13/langgraph/README.md` | v1 당시 폴더 안내문 | - | 보관 | 1 | 원문 그대로 보존 |
| `evaluations/datasets/guardrails/README.md` | 가드레일 평가셋 안내 | `src/guardrails/eval_guardrails.py` | 유지 | 1 | - |
| `evaluations/datasets/guardrails/가드레일_평가_v1.md` | 가드레일 평가표(데이터) | `src/guardrails/eval_guardrails.py`; `tests/test_guardrails.py` | 유지 | 2 | 평가 입력 데이터이므로 문서가 아니라 평가셋으로 취급 |
| `evaluations/datasets/neo4j/README.md` | Neo4j 다중 홉 10문항 | `src/evaluation/langgraph/ragas_eval.py` | 유지 | 2 | - |
| `evaluations/datasets/supervisor_v2/README.md` | v2 평가셋 구성·생성·실행 | `src/evaluation/build_evalset_v2.py`; `tests/unit/evaluation/test_evalset_v2.py` | 유지 | 7 | 정답은 규칙으로 결정적 계산 |
| `evaluations/datasets/vector_db/README.md` | Vector 검색 30문항 | `src/evaluation/vector_db/evaluate.py` | 유지 | 2 | - |
| `evaluations/reports/README.md` | 보관 결과 색인 | - | 유지 | 1 | - |
| `evaluations/reports/baseline_2026-11-13/README.md` | 흐름 변경 이전 기준선과 실행 조건 | - | 보관 | 9 | 수정 이전 결과의 기준 |
| `evaluations/reports/baseline_2026-11-13/hybrid_ragas/run_20261113_124252_summary.md` | Hybrid 150문항 결과 요약(원본) | - | 보관 | 1 | 원본 복사. 수정하지 않음 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_152004/report.md` | Neo4j 10문항 1차 결과 | - | 보관 | 1 | 원본 복사 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_160623/report.md` | Neo4j 10문항 2차 결과 | - | 보관 | 1 | 원본 복사 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_163133/report.md` | Neo4j 10문항 3차 결과 | - | 보관 | 1 | 원본 복사 |
| `evaluations/reports/baseline_2026-11-13/neo4j_multihop_ragas/run_20261113_170150/report.md` | Neo4j 10문항 4차 결과 | - | 보관 | 1 | 원본 복사 |
| `evaluations/reports/baseline_2026-11-13/vector_db/20261113_174527/report.md` | Vector 30문항 결과 | - | 보관 | 1 | 원본 복사 |
| `evaluations/reports/guardrails/README.md` | 가드레일 평가 이력 안내 | - | 보관 | 3 | - |
| `evaluations/reports/guardrails/가드레일_평가_v1_결과_20261113_2134.md` | 가드레일 평가 v1 결과 | - | 보관 | 1 | 당시 결과 |
| `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/README.md` | 흐름 변경 후 첫 v2 평가의 조건·결과·원인 | - | 보관 | 3 | 라우팅 수정 이전 결과. 수정 후 평가와 비교용 |
| `evaluations/reports/run_2026-11-14_supervisor_full_v2_first/summary.md` | 첫 v2 평가 요약(원본) | - | 보관 | 1 | 원본 복사 |

## src, tests, data, notebooks, scripts, outputs

| 문서 | 목적 | 관련 코드·테스트 | 분류 | 들어오는 링크 | 비고 |
|---|---|---|---|---:|---|
| `data/README.md` | 원본·정제 데이터와 로컬 DB 용도 | `data/` | 유지 | 1 | 1027행과 738행 CSV를 합치지 말라는 주의 포함 |
| `data/vector_db/README.md` | 로컬 Chroma DB 준비·보관 주의 | `notebooks/vector_db/` | 유지 | 1 | DB 일부만 Git 추적 |
| `notebooks/README.md` | Vector DB 구축 노트북 안내 | `notebooks/vector_db/*.ipynb` | 유지 | 5 | - |
| `outputs/README.md` | 로컬 실행 결과 폴더 안내 | - | 유지 | 1 | 결과는 Git 제외, README만 공유 |
| `scripts/README.md` | 설치 스크립트 안내 | `scripts/setup_hybrid.ps1`, `setup_hybrid.sh` | 유지 | 1 | `readme_for_scripts.md`가 합쳐짐 |
| `src/README.md` | 소스 폴더 안내 | `src/` | 유지 | 1 | - |
| `src/agent/README.md` | Agent와 Neo4j 검색 | `src/agent/` | 유지 | 1 | - |
| `src/agent/supervisor/README.md` | Supervisor 모듈 안내 | `src/agent/supervisor/` | 유지 | 1 | - |
| `src/data_pipeline/README.md` | 데이터 파이프라인 안내 | `src/data_pipeline/` | 유지 | 1 | - |
| `src/data_pipeline/neo4j/ontology_v2/README.md` | 온톨로지 v2 생성·적재·롤백 명령 | `build_cypher.py`, `apply_cypher.py`; `tests/.../test_ontology_v2.py` | 유지 | 4 | `--dry-run`, `--verify-only`, `--rollback` 옵션이 코드에 있음 |
| `src/evaluation/README.md` | 평가 코드 안내 | `src/evaluation/` | 유지 | 1 | - |
| `src/guardrails/README.md` | 입력·출력 가드레일 | `src/guardrails/guard.py`; `tests/test_guardrails.py` | 유지 | 2 | - |
| `src/hybrid/README.md` | Hybrid 검색 구조, 후보 필터, 설치·사용법 | `src/hybrid/`; `tests/unit/agent/test_hybrid_*.py` | 판단 보류 | 3 | 251줄. 후보 필터·이름 보장·확신도는 최신이나 앞부분 '새 버전' 안내의 현재성은 절별로 미확인 |
| `src/service/README.md` | Vector 검색 서비스와 별도 Streamlit UI | `src/service/` | 유지 | 1 | UI는 이번 작업에서 수정하지 않음 |
| `tests/README.md` | 테스트 구성과 실행 | `tests/` | 유지 | 1 | 하위 폴더 README는 여기에 통합됨 |

## 이전에 통합된 문서

이전 세션에서 짧은 하위 안내 문서 24개를 상위 README에 합쳤습니다(예: `tests/unit/**/README.md`, `tests/integration/**/README.md`, `scripts/readme_for_scripts.md`, 여러 `src/**/README.md`). 이 표에는 현재 남은 문서만 있습니다. 합치기 전 내용은 Git 기록에서 확인할 수 있습니다.

## 이 표가 가리키는 후속 작업 (승인 필요)

1. `docs/records/superpowers-folder-note.md`를 `plans/README.md`·`decisions/README.md`에 합치고 `records/README.md`의 링크를 정리합니다.
2. 판단 보류 계획 5개: 항목별로 코드·테스트·실행 결과를 확인해 `archive/plans/`로 옮길지 정합니다. 재평가 후 확인하는 편이 정확합니다.
3. `src/hybrid/README.md`: 절별 현재성을 확인합니다.
