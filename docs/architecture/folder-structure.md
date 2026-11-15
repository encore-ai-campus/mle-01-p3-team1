# 프로젝트 폴더 구조와 파일 쓰임새

이 문서는 현재 저장소의 역할별 구조, 주요 파일의 쓰임새, 기준 문서의 위치를 설명합니다.

- `data/processed`: 파이프라인이 쓰는 정제 데이터
- `evaluations/datasets`: 평가 기준 CSV
- `evaluations/reports`: 보관하는 평가 결과
- `outputs`: 로컬 실행 결과 (Git 제외)

로컬 DB 파일과 실행 결과는 제외 규칙을 확인하세요. 이미 Git이 추적하는 DB 파일에는 제외 규칙이 적용되지 않습니다.

## 터미널 챗봇 흐름

1. 질문이 입력 가드레일을 통과하면 Supervisor가 경로를 정합니다.
2. **편의시설·개관 요일 조건**이 있으면 온톨로지 후보 필터가 museum_id 후보를 먼저 거르고, Hybrid가 그 안에서만 검색합니다.
3. **단순 지역 + 주제** 질문은 지역 필터를 건 Hybrid로 갑니다.
4. 준비된 Graph 쿼리에 맞고 Neo4j가 연결되어 있으면 Graph로 보내며, 나머지는 LLM 라우터가 고릅니다. 기관 관계처럼 그래프가 필요한 질문은 `--with-neo4j`로 연결된 Graph(Neo4j 온톨로지 v2)로 갑니다.
5. Hybrid는 Chroma Vector와 BM25를 검색하고, RRF로 합친 뒤 로컬 Cross-Encoder로 재정렬합니다.
6. Supervisor는 CSV에서 확인 가능한 출처를 붙이고, 답변을 생성·검증합니다.
   - 조건을 만족하는 기록이 없으면 재시도 없이 이유를 안내하며 보류합니다.
   - 그 밖의 실패는 1회 재검색합니다.
7. 출력 가드레일을 거쳐 결과를 반환합니다.

검색 전 LLM 질의 분석은 기본적으로 꺼져 있습니다. Streamlit UI는 자체 Chroma·Neo4j 검색과 가드레일을 가진 별도 실행 경로입니다. 설치와 실제 실행 명령은 [루트 README](../../README.md)를 기준으로 합니다. 설계 이유는 [기술 결정](../decisions/README.md)에 있습니다.

## 디렉터리 구조

```text
.
├── README.md                         # 팀 공용 시작 안내와 주요 실행 명령
├── pyproject.toml, uv.lock            # Python 의존성 선언과 잠금 파일
├── .env.example                       # 필요한 환경 변수 이름과 빈 예시
├── .gitignore                         # 비밀값·캐시·DB·실행 결과 제외 규칙
├── 업데이트.py                        # 수업/저장소 업데이트 도우미
├── .streamlit/config.toml              # Streamlit 화면 설정
├── data/
│   ├── raw/                           # 원본 데이터
│   ├── processed/                     # 파이프라인 입력용 정제 데이터
│   └── vector_db/museum_chroma/       # Chroma 영구 저장소 (일부 파일 Git 추적)
├── evaluations/
│   ├── datasets/
│   │   ├── supervisor_v2/             # 현재 기본 Ragas 평가셋 196문항 (v1 150 + 새 흐름 46)
│   │   ├── archive/                   # 기본값에서 내려온 이전 평가셋 (v1)
│   │   ├── neo4j/                     # Neo4j 다중 홉 평가 CSV
│   │   ├── vector_db/                 # Vector 검색 평가 CSV
│   │   └── guardrails/                # 가드레일 평가표
│   └── reports/
│       ├── baseline_2026-11-13/       # 흐름 변경 이전 평가 결과 요약 (기준선)
│       ├── run_2026-11-14_supervisor_full_v2_first/  # 흐름 변경 후 첫 평가 (라우팅 수정 이전)
│       └── guardrails/                # 가드레일 평가 보고서
├── notebooks/vector_db/               # Chroma 구축·검토 노트북
├── outputs/                           # 평가·적재 실행 결과, Git 제외
├── scripts/                           # Hybrid 설치·모델 준비 스크립트
├── src/
│   ├── region_aliases.py              # 시도 별칭 공용 사전 (질의 시점 정규화)
│   ├── agent/                         # 기존 그래프, Neo4j 검색(Text2Cypher) 및 Supervisor
│   │   └── supervisor/                # 라우팅·검증·재검색·출처 연결
│   ├── hybrid/                        # 온톨로지 후보 필터 + BM25·Vector·RRF·Cross-Encoder
│   ├── guardrails/                    # 입력·출력 가드레일
│   ├── data_pipeline/
│   │   ├── neo4j/                     # CSV 파싱, Neo4j 기본 적재와 검증
│   │   │   └── ontology_v2/           # 온톨로지 v2 규칙, Cypher 생성·적재·롤백
│   │   └── vector_db/                 # VectorDB 구축 파이프라인 모듈 공간
│   ├── evaluation/
│   │   ├── build_evalset_v2.py        # v2 평가셋 생성기
│   │   ├── hybrid/                    # Hybrid·Supervisor·Graph 비교 평가
│   │   ├── langgraph/                 # Neo4j GraphRAG Ragas 평가·평가셋 합성
│   │   └── vector_db/                 # 검색 평가·평가셋 생성
│   └── service/                       # Streamlit UI와 Vector 검색 서비스
├── tests/
│   ├── unit/                          # 외부 DB 없이 실행하는 단위 테스트
│   └── integration/                   # 외부 DB/저장소 연결 통합 테스트 공간
└── docs/
    ├── architecture/                  # 현재 구조와 연결 방식 (어떻게)
    ├── decisions/                     # 기술 선택 이유와 대안
    ├── archive/plans/                 # 구현이 확인된 과거 계획
    ├── evaluation/                    # 평가 실행·검수 안내
    ├── operations/neo4j/              # Neo4j 적재·검증 운영 안내
    ├── plans/                         # 미완료·확인 보류 계획
    └── records/                       # 정리·적재 결과 기록
```

## 주요 파일과 역할

### 실행 코드

| 파일 | 역할 |
|---|---|
| `src/agent/supervisor/` | Supervisor 흐름. `connect.py`가 통합 진입점, `run.py`가 CLI입니다. `nodes.py`는 라우팅·검증·재검색·기록 없음 보류, `provenance.py`는 CSV 출처·속성 근거 연결, `llm.py`는 라우터·답변·검증 프롬프트를 담당합니다. |
| `src/agent/neo4j_text2cypher.py` | 자연어 → 읽기 전용 Cypher. v2 라벨 허용, 고정 쿼리(같은 시군구, 인용 출처, 같은 기관 운영·관리 등), 기준 시설(anchor) 근거를 다룹니다. |
| `src/agent/neo4j_search.py` | 박물관 TextSpan 근거를 파라미터화한 Cypher로 검색합니다. |
| `src/agent/neo4j_tls.py` | Windows 인증서 저장소를 사용해 Aura TLS 연결을 설정합니다. |
| `src/agent/neo4j_demo.py` | Aura Neo4j에 연결해 실제 GraphRAG 질문을 실행하는 데모 CLI입니다. |
| `src/agent/region_normalization.py` | Neo4j·Supervisor에서 쓰는 시도 별칭 헬퍼입니다(`src/region_aliases.py` 사용). |
| `src/agent/state.py`, `graph.py`, `__init__.py` | 기존 LangGraph 상태·흐름과 공개 진입 함수 `build_graph`입니다. |
| `src/agent/demo_graph.py` | 실제 DB 없이 예시 함수로 오케스트레이션 흐름을 보여 줍니다. |
| `src/agent/ragas_eval.py`, `ragas_testset.py`, `bm25_reranker.py` | 이전 import·명령을 유지하는 호환 진입점입니다. 새 개발은 `src/evaluation/`과 `src/hybrid/`를 수정합니다. |
| `src/hybrid/service.py` | Hybrid 검색 본체. 0단계 온톨로지 후보 필터 → BM25·Vector → RRF → Cross-Encoder 순서입니다. |
| `src/hybrid/ontology_filter.py` | 질문의 편의시설·개관 요일·지역 조건 추출, 후보 museum_id 계산(로컬 CSV 또는 Neo4j v2), `--check-neo4j` 일치 점검을 담당합니다. |
| `src/hybrid/name_match.py` | 질문에 적힌 시설명을 CSV에서 찾아 재정렬 후보에 반드시 포함시킵니다. |
| `src/hybrid/region_theme.py` | 단순 지역 + 주제 질문 인식입니다. |
| `src/hybrid/bm25_reranker.py` | BM25 점수와 후보 순위를 계산하는 기준 구현입니다. |
| `src/data_pipeline/neo4j/parsing.py`, `graph_db.py`, `load_neo4j.py` | 정제 CSV 검증, Neo4j 기본 그래프 적재(`--dry-run`, `--verify-only`)를 담당합니다. |
| `src/data_pipeline/neo4j/validate_multihop.py` | 그래프에서 2~4홉 읽기 경로를 점검하는 CLI입니다. |
| `src/data_pipeline/neo4j/ontology_v2/rules.py` | 시설 유형, 기관 정규화, 편의시설 사전, 주제 키워드, 휴관 규칙 파싱. 필터·그래프·평가셋이 공유하는 규칙입니다. |
| `src/data_pipeline/neo4j/ontology_v2/build_cypher.py`, `apply_cypher.py` | v2 Cypher 생성과 적재·검증·롤백 CLI입니다. |
| `src/evaluation/build_evalset_v2.py` | v2 평가셋 생성기. CSV와 v2 규칙으로 정답을 결정적으로 계산합니다. |
| `src/evaluation/hybrid/ragas_eval.py` | BM25·Vector·Hybrid·Supervisor·`supervisor_full`(실제 흐름 전체)·Graph를 비교 평가합니다. |
| `src/evaluation/langgraph/ragas_eval.py`, `ragas_testset.py` | Neo4j GraphRAG Ragas 평가와 LLM 기반 평가셋 합성입니다. |
| `src/evaluation/vector_db/evaluate.py`, `generate_testset.py` | Chroma 검색 순위 평가(Hit@k, Recall@5, MRR@10)와 30문항 초안 생성입니다. |
| `src/service/app.py` | Streamlit 박물관 서비스의 시작점입니다. |
| `src/service/ui/` | 대시보드(`dashboard.py`), 지도(`map_view.py`), 챗봇(`chatbot.py`), 지식그래프(`kg.py`), 공용 데이터·스타일(`data.py`, `style.py`, `themes.py`)입니다. |
| `src/service/vector_search_*.py` | 질문 분석, Chroma 검색(`candidate_ids` 지원), 후보 평가, 에이전트 래퍼입니다. |
| `src/service/static/fonts/` | 화면에서 사용하는 IBM Plex Sans KR 글꼴과 라이선스 파일입니다. |

### 데이터와 평가셋

| 경로 | 역할 |
|---|---|
| `data/raw/museum_base_1070.csv` | 박물관 기초 원본 데이터입니다. |
| `data/raw/museum_tourapi_with_overview.csv` | 관광 API 개요를 포함한 원본 데이터입니다. |
| `data/processed/museum_final_1027.csv` | 1,027행·59열 정제 데이터이며 Streamlit 화면의 기본 입력입니다. |
| `data/processed/museum_final_738.csv` | 738개 박물관. Neo4j 적재, 온톨로지 v2, 후보 필터, 출처 연결, 평가셋 생성의 기준 데이터이며 **읽기만 합니다**. |
| `data/processed/museum_chroma_ready.csv` | Chroma 구축 노트북이 저장하는 준비 데이터입니다. |
| `data/vector_db/museum_chroma/` | Chroma의 SQLite/HNSW 영구 파일입니다. 일부는 Git에서 추적하며 나머지 로컬 파일은 제외될 수 있습니다. |
| `evaluations/datasets/supervisor_v2/Supervisor_Ragas_v2_draft.csv` | 현재 기본 Ragas 평가셋 196문항입니다. `src.evaluation.build_evalset_v2`로 다시 만들 수 있습니다. |
| `evaluations/datasets/archive/v1_2026-11-13/langgraph/` | 이전 기본값이던 150문항과 30문항 시드(보관). 결과는 `evaluations/reports/baseline_2026-11-13/`에 있습니다. |
| `evaluations/datasets/neo4j/Neo4j_multihop_core10_draft.csv` | Neo4j 다중 홉 평가용 10문항 초안입니다. |
| `evaluations/datasets/vector_db/VectorDB_평가셋_30문항.csv` | Vector 검색의 정답 박물관 ID와 평가 질문입니다. |
| `notebooks/vector_db/vector_db_builder.ipynb` | 정제 CSV에서 Chroma 입력을 준비하고 영구 DB에 적재합니다. |
| `notebooks/vector_db/vector_db_builder_test.ipynb` | 빌더 과정을 확인하는 별도 노트북입니다. |
| `outputs/` | 평가 보고서와 Neo4j 검증 JSON의 로컬 출력입니다. README만 Git에 포함합니다. |

`data/processed/museum_final_1027.csv`와 `museum_final_738.csv`는 행·열 수와 내용이 다른 데이터입니다. 동일한 데이터처럼 합치지 말고 각각의 원천·용도를 유지합니다.

### 테스트

| 경로 | 내용 |
|---|---|
| `tests/unit/agent/` | Supervisor, Neo4j 검색·Text2Cypher(v2 포함), 후보 필터, Hybrid 연동 |
| `tests/unit/data_pipeline/neo4j/` | CSV 파싱, 적재, 다중 홉, 온톨로지 v2 규칙·Cypher 생성 |
| `tests/unit/evaluation/` | Ragas 평가, v2 평가셋, 시간 계측, 가드레일 출력 경로 |
| `tests/integration/` | 실제 Neo4j/Chroma 연결 검증을 둘 위치입니다. 아직 연결 테스트는 없습니다. |

## 기준 문서 찾기

- 설치·실행 명령: [루트 README](../../README.md)
- 현재 모듈 연결·라우팅 우선순위: [Supervisor 연결](supervisor-integration.md)
- 온톨로지 스키마: [온톨로지 v2](ontology-v2.md)
- 선택 이유·대안: [기술 결정](../decisions/README.md)
- 실패와 해결 전후 근거: [검증 기록](../records/README.md)
- 평가 방법·비교 조건: [평가 문서](../evaluation/README.md)
- 평가셋·원본 결과: [평가 자료](../../evaluations/README.md)
- 문서별 이전 경로와 통합 위치: [문서 정리 기록](../records/cleanup-audit.md)
- 모든 Markdown 문서의 목적·분류·들어오는 링크: [문서 분류표](../records/doc-inventory.md)

단순 폴더 설명은 상위 README에서 관리합니다. 독립적인 설치·운영·데이터 버전·검증 의미가 있는 안내만 하위 README로 유지합니다.
