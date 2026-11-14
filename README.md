# 박물관 RAG 챗봇

박물관 질문에 대해 Chroma 벡터 검색과 BM25 키워드 검색을 결합하고, Cross-Encoder로 재정렬한 뒤 근거와 함께 답변합니다. Supervisor는 질문 경로를 선택하고 답변·출처를 검증합니다. Neo4j Graph 검색은 별도로 연결할 수 있습니다. 아래 안내는 **터미널 챗봇** 기준입니다. Streamlit UI는 별도 실행 경로입니다.

## 1. 준비물

- Windows PowerShell, Python **3.12** 및 [uv 설치](https://docs.astral.sh/uv/getting-started/installation/). macOS/Linux 명령은 [Hybrid 안내](src/hybrid/README.md)를 참고하세요.
- OpenAI API 키와 사용할 모델의 접근 권한. 질문, 근거와 가드레일 검사가 API로 전송되며 사용료가 발생합니다.
- Chroma 컬렉션 `museum_documents`의 **완전한 데이터 폴더**. 이 저장소는 DB 내부 파일을 일부만 추적하므로 새 클론이 완전한 인덱스라는 보장은 없습니다. 팀에서 `data/vector_db/museum_chroma/` 전체를 받거나, [벡터 DB 구축 안내](notebooks/README.md)에 따라 새 환경에서 다시 만드세요.
- Neo4j를 함께 쓰려면 연결 가능한 Aura DB와 계정 정보. Hybrid만 사용하는 경우에는 필요하지 않습니다.

저장소를 내려받은 뒤 해당 폴더로 이동합니다. 이미 내려받았다면 이 단계는 건너뜁니다.

```powershell
git clone https://github.com/encore-ai-campus/mle-01-p3-team1.git
cd mle-01-p3-team1
```

## 2. 설치와 설정

저장소 루트 PowerShell에서 실행합니다. 기존 `.env`가 있으면 덮어쓰지 않습니다.

```powershell
uv sync
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

`.env`에 `OPENAI_API_KEY`를 입력합니다. Neo4j를 사용할 때는 `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`도 입력합니다. `SUPERVISOR_MODEL`을 설정하거나 아래 실행 명령처럼 `--model`로 모델명을 지정하세요. `OPENAI_CHAT_MODEL`, `RAGAS_JUDGE_MODEL`, `GUARDRAILS_MODEL`은 필요에 따라 지정합니다.

다른 터미널에서 평가가 실행 중이라면 그 평가가 끝난 뒤 같은 `.venv`의 설치·동기화를 진행하세요.

```dotenv
OPENAI_API_KEY=발급받은_키
SUPERVISOR_MODEL=gpt-6-luna
MUSEUM_QUERY_ANALYSIS_ENABLED=false
```

`gpt-6-luna`는 팀에서 사용한 예시입니다. 계정에서 접근 가능한 구조화 출력 모델을 사용하세요. `.env`는 공유하거나 Git에 올리지 않습니다.

Cross-Encoder 모델을 한 번 준비합니다. 처음에는 모델 파일 다운로드와 저장 공간이 필요하며, 이미 준비된 모델은 재사용합니다.

```powershell
uv run --no-sync python -m src.hybrid.prepare_models
```

의존성 전체 설치와 모델 준비를 한 번에 하려면 `.\scripts\setup_hybrid.ps1`을 사용해도 됩니다. 루트 의존성에는 실습용 패키지도 포함돼 있어 초기 설치가 오래 걸릴 수 있습니다.

## 3. 터미널 챗봇 실행

Hybrid + Supervisor + 입력·출력 가드레일:

```powershell
.\.venv\Scripts\python.exe -m src.agent.supervisor.run --team-hybrid --interactive --timings --model gpt-6-luna
```

질문을 반복 입력하고 `q`로 종료합니다. 같은 프로세스에서 Cross-Encoder 모델을 재사용하므로 매 질문마다 새 프로세스를 시작할 필요가 없습니다. 최초 모델 메모리 로딩은 시간이 걸릴 수 있습니다.

Neo4j도 연결해 질문 유형에 따라 Graph 경로를 사용하려면:

```powershell
.\.venv\Scripts\python.exe -m src.agent.supervisor.run --team-hybrid --with-neo4j --interactive --timings --model gpt-6-luna
```

`--with-neo4j`가 없으면 Supervisor의 별도 Graph retriever는 연결되지 않습니다. 단일 질문은 `--interactive` 대신 `--question "질문"`을 사용합니다. 결과의 `status`, `trajectory`, 시간 정보를 터미널에서 확인할 수 있습니다. 가드레일 차단 또는 검사 오류는 `status: blocked`로 표시됩니다.

기본 설정에서는 검색 전 LLM 질문 분석이 꺼져 있습니다. 규칙 기반 지역 필터와 온톨로지 후보 필터는 별도로 적용될 수 있습니다. 원문으로 Vector와 BM25를 검색한 뒤 RRF와 Cross-Encoder를 사용합니다. 지역·요금 조건의 검색 품질을 비교하려면 `.env`에 `MUSEUM_QUERY_ANALYSIS_ENABLED=true`를 설정할 수 있습니다. 재정렬과 질문 분석의 설정은 서로 다릅니다. 상세 흐름은 [구조 설명](docs/architecture/folder-structure.md)과 [Supervisor 연결](docs/architecture/supervisor-integration.md)을 참고하세요.

## 4. 평가와 결과

평가는 OpenAI API를 사용합니다. 아래 예시는 각각 독립 평가이며 동시에 돌릴 필요는 없습니다.

```powershell
# 실제 Supervisor 흐름 전체(자동 라우팅 + 후보 필터 + Neo4j), v2 196문항 (Neo4j 설정 필요)
.\.venv\Scripts\python.exe -m src.evaluation.hybrid.ragas_eval --modes supervisor_full --top-k 5

# Hybrid + Cross-Encoder, v2 196문항 (이전 기준선과 평가셋이 다르므로 공통 문항을 따로 비교)
.\.venv\Scripts\python.exe -m src.evaluation.hybrid.ragas_eval --modes hybrid_rerank --top-k 5

# Neo4j GraphRAG, 10문항 (Neo4j 설정 필요)
.\.venv\Scripts\python.exe -m src.evaluation.langgraph.ragas_eval --evalset "evaluations/datasets/neo4j/Neo4j_multihop_core10_draft.csv" --top-k 5 --batch-size 8

# Chroma 검색 순위 평가, 30문항. 실행별 폴더를 만들어 기존 결과 보존
$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
.\.venv\Scripts\python.exe -m src.evaluation.vector_db.evaluate --output "outputs/evaluation/vector_db/run_$runStamp"
```

평가셋과 명령어는 [평가 안내](evaluations/README.md), 지표와 이어하기는 [평가 문서 색인](docs/evaluation/README.md)을 참고하세요. Hybrid 결과는 `outputs/evaluation/hybrid_ragas/`, Neo4j 결과는 `outputs/evaluation/neo4j_multihop_ragas/`, Vector 결과는 `outputs/evaluation/vector_db/`의 실행별 폴더에 저장됩니다. 작성 중인 결과 폴더는 이동하거나 지우지 마세요. 평가셋은 사람 검수 전 초안이므로 점수는 잠정치입니다. 2026-11-14 흐름 변경 이전 결과는 [평가 기준선](evaluations/reports/baseline_2026-11-13/README.md)에 보관했습니다.

## 5. 폴더 안내

| 폴더 | 내용 |
|---|---|
| [src](src/README.md) | Supervisor, Hybrid, 가드레일, 데이터 구축, 평가 및 별도 UI 코드 |
| [data](data/README.md) | 원본·정제 CSV와 로컬 Chroma DB |
| [evaluations](evaluations/README.md) | 평가셋. 실행 결과와 구분 |
| [outputs](outputs/README.md) | 로컬 평가·실행 결과. Git에는 README만 포함 |
| [notebooks](notebooks/README.md) | DB 구축 노트북 |
| [scripts](scripts/README.md) | 설치·모델 준비 스크립트 |
| [docs](docs/README.md) | 구조, 설계 근거·문제 해결 기록, 평가, DB 운영 문서 |
| [tests](tests/README.md) | 단위·통합 테스트 |

문제 해결: 모델이 없다는 오류는 모델 준비 명령을 다시 실행하고, Chroma 오류는 완전한 DB 폴더와 컬렉션을 확인하세요. Neo4j 연결 오류는 `.env`와 Aura 상태를 확인하세요. 가드레일 검사 실패 시 안전을 위해 답변이 차단됩니다. LangGraph의 중간 스트림에는 검사 전 초안이 포함될 수 있어 사용자 화면에는 `invoke()`의 최종 결과만 표시해야 합니다.
