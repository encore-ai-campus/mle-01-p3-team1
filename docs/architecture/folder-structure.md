# 프로젝트 폴더 구조와 파일 쓰임새

이 문서는 현재 저장소의 역할별 구조와 주요 파일의 쓰임새를 설명합니다. `data/processed`에는 파이프라인이 소비하는 정제 데이터, `evaluations/datasets`에는 평가 기준 CSV, `outputs`에는 실행 결과를 둡니다. 로컬 DB와 실행 결과는 `.gitignore`로 제외합니다.

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
│   └── vector_db/museum_chroma/       # 로컬 Chroma 영구 저장소, Git 제외
├── evaluations/datasets/
│   ├── langgraph/                     # LangGraph Ragas 시드와 300문항 CSV
│   └── vector_db/                     # Vector 검색 평가 CSV
├── notebooks/vector_db/               # Chroma 구축·검토 노트북
├── outputs/                           # 평가·적재 실행 결과, Git 제외
├── src/
│   ├── agent/                         # LangGraph 실행 흐름과 Neo4j 검색 어댑터
│   ├── data_pipeline/
│   │   ├── neo4j/                     # CSV 파싱, Neo4j 적재와 검증
│   │   └── vector_db/                 # VectorDB 구축 파이프라인 모듈 공간
│   ├── evaluation/
│   │   ├── langgraph/                 # Ragas 평가·평가셋 생성 CLI
│   │   └── vector_db/                 # 검색 평가·평가셋 생성 CLI
│   └── service/                       # Streamlit UI와 검색 서비스
├── tests/
│   ├── unit/                          # 외부 DB 없이 실행하는 단위 테스트
│   └── integration/                   # 외부 DB/저장소 연결 통합 테스트 공간
└── docs/
    ├── architecture/                  # 구조·설계 문서
    ├── evaluation/                    # 평가 실행·검수 안내
    └── operations/neo4j/              # Neo4j 적재·검증 운영 안내
```

## 주요 파일과 역할

### 실행 코드

| 파일 | 역할 |
|---|---|
| `src/agent/state.py` | LangGraph 노드 사이에서 주고받는 상태와 검색 근거 타입을 정의합니다. |
| `src/agent/graph.py` | 질문 라우팅, 검색, 답변 생성, 근거 검증, 재검색 흐름을 조립합니다. |
| `src/agent/demo_graph.py` | 실제 DB 없이 예시 함수로 오케스트레이션 흐름을 보여 줍니다. |
| `src/agent/neo4j_demo.py` | Aura Neo4j에 연결해 실제 GraphRAG 질문을 실행하는 데모 CLI입니다. |
| `src/agent/neo4j_search.py` | 박물관 TextSpan 근거를 파라미터화한 Cypher로 검색합니다. |
| `src/agent/neo4j_text2cypher.py` | 자연어 질문을 읽기 전용 Cypher로 바꾸고 답변 생성을 연결합니다. |
| `src/agent/neo4j_tls.py` | Windows 인증서 저장소를 사용해 Aura TLS 연결을 설정합니다. |
| `src/agent/__init__.py` | LangGraph의 공개 진입 함수인 `build_graph`를 내보냅니다. |
| `src/agent/ragas_eval.py`, `src/agent/ragas_testset.py` | 이전 `src.agent.*` 명령과 import를 유지하는 호환 진입점입니다. 새 개발은 `src/evaluation/langgraph/`를 수정합니다. |
| `src/data_pipeline/neo4j/parsing.py` | 정제 CSV를 검증하고 Neo4j 적재 레코드로 변환합니다. |
| `src/data_pipeline/neo4j/graph_db.py` | 파라미터화한 Cypher, 그래프 적재와 읽기 검증을 구현합니다. |
| `src/data_pipeline/neo4j/load_neo4j.py` | Neo4j 적재·`--dry-run`·`--verify-only` CLI입니다. 기본 CSV는 `data/processed/museum_final_738.csv`입니다. |
| `src/data_pipeline/neo4j/validate_multihop.py` | 그래프에서 2~4홉 읽기 경로를 점검하는 CLI입니다. |
| `src/evaluation/langgraph/ragas_testset.py` | 원문 구간에서 Ragas 질문·기준 답변 초안을 생성합니다. |
| `src/evaluation/langgraph/ragas_eval.py` | 실제 GraphRAG 결과를 Ragas로 평가하고 문항별/요약 보고서를 씁니다. |
| `src/evaluation/vector_db/generate_testset.py` | VectorDB 검색용 30문항 평가셋 초안을 생성합니다. |
| `src/evaluation/vector_db/evaluate.py` | 기존 Chroma 컬렉션의 Hit@k, Recall@5, MRR@10을 계산합니다. |
| `src/service/app.py` | Streamlit 박물관 서비스의 시작점입니다. |
| `src/service/ui/data.py` | 대시보드·지도·챗봇에서 공유하는 박물관 CSV 로딩과 필드 정제를 담당합니다. |
| `src/service/ui/dashboard.py` | 박물관 수, 지역 분포, 상세 정보를 보여 주는 대시보드 탭입니다. |
| `src/service/ui/map_view.py` | 지역 필터와 박물관 위치를 지도에 표시합니다. |
| `src/service/ui/chatbot.py` | Chroma 검색과 OpenAI 답변 생성으로 박물관 챗봇 탭을 제공합니다. |
| `src/service/ui/graph_rag.py` | Aura 스키마 확인, 그래프 탐색, 자연어 Cypher 질의를 제공합니다. |
| `src/service/ui/style.py` | Streamlit 탭의 색상, CSS, 차트 공통 스타일을 정의합니다. |
| `src/service/static/fonts/` | 화면에서 사용하는 IBM Plex Sans KR 글꼴과 라이선스 파일입니다. |
| `src/service/vector_search_analyzer.py` | 질문에서 Vector 검색 조건을 만들고 후보 관련성을 평가합니다. |
| `src/service/vector_search_chroma.py` | 기존 Chroma 컬렉션을 읽어 검색합니다. |
| `src/service/vector_search_service.py` | 질문 분석, Chroma 검색, 후보 평가를 묶는 서비스 계층입니다. |
| `src/service/vector_search_rag_agent.py` | 대화형 에이전트에서 Vector 검색 서비스를 부르는 래퍼입니다. |

### 데이터, 평가셋, 문서

| 경로 | 역할 |
|---|---|
| `data/raw/museum_base_1070.csv` | 박물관 기초 원본 데이터입니다. |
| `data/raw/museum_tourapi_with_overview.csv` | 관광 API 개요를 포함한 원본 데이터입니다. |
| `data/processed/museum_final_1027.csv` | 1,027행·59열 정제 데이터이며 Streamlit 화면의 기본 입력입니다. |
| `data/processed/museum_final_738.csv` | 738개 박물관 기반 Neo4j 적재와 평가셋 생성에 쓰는 데이터입니다. |
| `data/processed/museum_chroma_ready.csv` | Chroma 구축 노트북이 저장하는 준비 데이터입니다. |
| `data/vector_db/museum_chroma/` | Chroma의 SQLite/HNSW 영구 파일입니다. 로컬 실행 산출물이라 Git에서 제외합니다. |
| `evaluations/datasets/langgraph/LangGraph_Ragas_평가셋_30문항.csv` | 300문항 Ragas 세트의 시드입니다. |
| `evaluations/datasets/langgraph/LangGraph_Ragas_평가셋_300문항.csv` | 실제 Aura GraphRAG 평가용 CSV입니다. 현재 `draft_needs_human_review` 라벨이므로 사람 검수 후 점수를 기준선으로 사용해야 합니다. |
| `evaluations/datasets/vector_db/VectorDB_평가셋_30문항.csv` | Vector 검색의 정답 박물관 ID와 평가 질문을 담습니다. |
| `notebooks/vector_db/vector_db_builder.ipynb` | 정제 CSV에서 Chroma 입력을 준비하고 영구 DB에 적재합니다. |
| `notebooks/vector_db/vector_db_builder_test.ipynb` | 빌더 과정을 확인하는 별도 노트북입니다. |
| `docs/operations/neo4j/README.md` | Aura 설정, Neo4j 적재, 읽기 검증 명령을 안내합니다. |
| `docs/evaluation/langgraph_ragas.md` | Ragas 평가셋 생성, 연결 사전 점검, 평가, 라벨 검수 절차를 안내합니다. |
| `docs/evaluation/vector_db.md` | Vector 평가셋 검수와 Chroma 평가 명령·지표를 안내합니다. |
| `docs/operations/neo4j/IMPLEMENTATION_PLAN.md` | Neo4j 적재기 구현 범위와 검증 기준을 기록합니다. |
| `docs/operations/neo4j/LOAD_REPORT.md` | Aura에 적재한 그래프 구조와 검증 결과를 설명합니다. 실행 JSON은 로컬 `outputs/neo4j/`에 둡니다. |
| `src/data_pipeline/neo4j/requirements.txt` | Neo4j 적재만 별도 설치할 때 필요한 최소 의존성을 나열합니다. |
| `tests/unit/` | 에이전트, 적재 파싱, 평가 코드의 빠른 단위 테스트입니다. |
| `tests/integration/` | 실제 Neo4j/Chroma 연결 검증을 추가할 위치입니다. 현재 연결 테스트는 아직 배치하지 않았습니다. |
| `outputs/` | 평가 보고서와 Neo4j 검증 JSON의 로컬 출력입니다. Git에는 올리지 않습니다. |

현재 단위 테스트의 세부 구분은 `tests/unit/agent/`의 그래프·Neo4j 검색, `tests/unit/data_pipeline/neo4j/`의 CSV 파싱·적재·다중 홉, `tests/unit/evaluation/langgraph/`의 Ragas 평가셋·점수 처리입니다. 파일 이름은 각각 `test_*.py`이며 실제 Aura 연결이 필요한 테스트는 이 단위 테스트와 별도로 `tests/integration/neo4j/`에 둡니다.

`data/processed/museum_final_1027.csv`와 `museum_final_738.csv`는 행·열 수와 내용이 다른 데이터입니다. 동일한 데이터처럼 합치지 말고 각각의 원천·용도를 유지합니다.

## 주요 실행 명령

저장소 루트에서 실행합니다.

```powershell
uv run python -m src.data_pipeline.neo4j.load_neo4j --verify-only
uv run python -m src.agent.neo4j_demo --question "서울 전통문화" --top-k 5
uv run python -m src.evaluation.langgraph.ragas_eval --check-only
uv run python -m src.evaluation.vector_db.evaluate --check-only
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

Ragas 전체 평가는 GraphRAG 질의와 LLM 채점을 수행해 OpenAI API 비용이 발생할 수 있습니다. `--check-only`는 데이터와 환경을 확인하며 평가용 임베딩/채점 호출은 하지 않습니다. Chroma 평가의 전체 실행은 질문 임베딩을 위해 OpenAI API를 사용합니다.

현재 300문항 CSV는 로컬 파일로 이동했지만 아직 Git에서 추적하지 않습니다. 팀원이 동일 평가셋을 쓰도록 하려면 사람이 라벨을 검수하고 저장소 변경에 CSV를 포함해야 합니다. `.env`에는 실제 비밀번호와 API 키를 저장하며 Git에 올리지 않습니다. `.env.example`에는 변수 이름과 예시만 둡니다.
