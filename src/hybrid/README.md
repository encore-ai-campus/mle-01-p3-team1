# `src/hybrid` — 박물관 Sparse + Dense Hybrid 검색

## 0. 모델 자동 준비 (새 버전)

`uv sync`는 **Python 패키지**만 설치합니다. Hugging Face의 대형 모델 가중치/토크나이저는 `uv sync`의 자동 후처리 대상이 **아닙니다**. 이 패키지의 `scripts/setup_hybrid.ps1`은 `uv sync` 다음에 모델 준비까지 실행하는 **한 번의 설치 명령**입니다.

```powershell
# 이후 처음 설정하거나 다른 PC에 설치할 때
.\scripts\setup_hybrid.ps1

# 준비 여부만 확인 (네트워크/모델 메모리 로딩 없음)
uv run --no-sync python -m src.hybrid.prepare_models --check-only

# 필요할 때만 검증용 오프라인 모델 로딩
uv run --no-sync python -m src.hybrid.prepare_models --verify

# 검색: 이제 Hugging Face 모델 다운로드 없음
uv run --no-sync python -m src.hybrid.hybrid_rag_agent "역사 박물관"
```

Linux/macOS/CI에서는 `sh scripts/setup_hybrid.sh`를 사용합니다. 필요한 패키지는 프로젝트 `pyproject.toml`과 `uv.lock`에 선언되어 있습니다.

- 기본 모델: `BAAI/bge-reranker-v2-m3` (가중치 약 2.27GB + 토크나이저)
- **기존 사용자 Hugging Face 캐시가 온전하면 재활용**하며, 없을 때만 프로젝트 `.models/hybrid/`에 다운로드합니다.
- 초기 검증이 완료된 모델은 준비 기록(`.hybrid_model_ready.json`)을 저장하여, 다음 설치 명령에서 **네트워크 조회까지 생략**합니다.
- 검색 코드에서는 `CrossEncoder(로컬경로, local_files_only=True)`를 호출해 원격 모델 확인을 하지 않습니다.
- 모델은 각 Python 프로세스 시작 후 최초 호출에서 메모리로 로딩됩니다. **디스크 다운로드와 모델의 메모리 로딩은 서로 다릅니다.** LangGraph에서는 Agent 객체를 재사용하세요.
- `.models/`는 대형 파일이므로 Git에 포함하지 않도록 내부 `.gitignore`를 준비합니다. 배포 서버에도 설치 스크립트가 한 번 필요합니다.
- 모델이 준비되지 않으면 임의로 다운로드하지 않고 예외를 내며, 기존 서비스의 `rerank_failure_policy` 설정에 따라 명시적 실패 또는 경고를 동반한 RRF 폴백으로 처리합니다. 엄격하게 실패시키려면 `HYBRID_RERANK_FAILURE_POLICY=raise`를 설정하세요.
- 기존 `HybridRAGAgent`의 출력에 `model_load_ms`, `inference_ms`가 추가되어 CPU 추론 병목과 다운로드 이슈를 구분할 수 있습니다.

### 선택 환경변수

```dotenv
HYBRID_RERANK_MODEL=BAAI/bge-reranker-v2-m3
# 기본 모델 저장 경로를 변경하고 싶을 때만 지정 (프로젝트 루트 상대경로 가능)
# HYBRID_RERANK_LOCAL_DIR=.models/hybrid/my_reranker
# 모델 버전을 고정하고 싶은 경우 Hugging Face commit SHA 지정
# HYBRID_RERANK_REVISION=<commit_sha>
```

**매번 새 모델을 내려받는 것으로 보이는 경우:** 이전 구현은 HF 모델 ID로 `CrossEncoder`를 로딩하여 캐시 버전 확인 HTTP 요청이 생길 수 있었고, 모델 가중치를 매 프로세스마다 RAM으로 다시 올렸습니다. 새 버전은 런타임 네트워크 요청을 차단합니다. 다만 추론 시간이 느린 경우 모델을 다운로드해 두는 것만으로 속도가 개선되지는 않습니다.

---

## 검색 구조와 수정 범위

```text
                          사용자 질문
                                │
          온톨로지 후보 필터 (구조 조건이 있을 때만, LLM 호출 없음)
          편의시설·개관 요일·지역 → museum_id 후보 집합
                                │
             질문 분석 선택 (기본 OFF: 원문 사용)
                       /                    \
         기존 VectorService                 BM25SpanRetriever
    Chroma Top 20; rerank=False           Top 20; 원문 질의
      (분석 ON이면 확장/필터)            (전체 코퍼스 독립 검색)
                       \                    /
                           가중 RRF
                    중복 제거 · Top 20
                                │
                      Cross-Encoder 평가
                                │
                          최종 Top 10
```

**온톨로지 후보 필터(`ontology_filter.py`):**
- **작동 조건:** 질문에 "수유실 있는", "월요일에도 여는"처럼 기록된 사실로 판정할 수 있는 조건이 있을 때만 작동합니다.
- **동작:** 조건을 만족하는 museum_id 집합을 만들고, Vector와 BM25가 그 안에서만 검색합니다.
- **근거 표시:** 결과의 `metadata.structured_match`에 어떤 기록으로 통과했는지 붙습니다.
- **후보가 0개일 때:** 조건을 빼고 검색하지 않고 `no_results`로 끝냅니다.
- **데이터 원천:** 속성은 Neo4j 온톨로지 v2와 같은 규칙(`src/data_pipeline/neo4j/ontology_v2/rules.py`)으로 CSV에서 계산합니다.
- **끄기:** `HYBRID_ONTOLOGY_FILTER=off`로 끌 수 있습니다.

**시설명 보장(`name_match.py`):** 질문에 CSV에 기록된 시설명이 그대로 적혀 있으면 그 시설을 재정렬 후보에 반드시 넣습니다. 최종 순서는 재정렬이 정합니다. `HYBRID_NAME_MATCH=off`로 끌 수 있습니다.

**재정렬 확신도:** Cross-Encoder 최고 점수가 `HYBRID_RERANK_MIN_CONFIDENCE`(기본 0.1)보다 낮으면 재정렬 순서를 쓰지 않고 RRF 순서를 유지합니다. 0으로 두면 이 기능이 꺼집니다. 두 기능의 근거는 `docs/records/supervisor-retrieval-issues.md`에 있습니다.
- 근거와 설계 판단은 `docs/decisions/ontology-filter-routing.md`에 있습니다.

이 패키지는 Neo4j에 직접 연결하지 않습니다. 기존 Vector 검색(`src/service/vector_search_service.py`, `vector_search_chroma.py`, `vector_search_analyzer.py`)을 사용합니다. 기본값은 `MUSEUM_QUERY_ANALYSIS_ENABLED=false`로, 검색어 확장과 메타데이터 필터 추출을 위한 LLM 호출을 생략하고 원문 질문으로 검색합니다. 다시 켜려면 환경변수를 `true`로 설정하세요. 질문 분석을 꺼도 BM25·Vector 검색, RRF 통합, Cross-Encoder 재정렬은 그대로 동작합니다. 기존 `VectorSearchService.execute_plan(..., top_k=20, rerank=False)` 경로로 Vector 단계의 LLM 후보 재평가는 계속 건너뜁니다. Supervisor 연결 방법은 `docs/architecture/supervisor-integration.md`를 참고하세요.

## 전달받은 BM25 파일과 연결 방식

- **`bm25_reranker.py`**: `BM25Reranker`, `SpanDocument`, `RankedMuseum`, 한국어 Kiwi 토큰화 및 `rank_bm25.BM25Okapi`의 기준 구현입니다. 기존 `src.agent.bm25_reranker`도 같은 클래스를 내보냅니다.
- **`bm25_retriever.py`**: 신규 어댑터 `BM25SpanRetriever` 구현. 전체 코퍼스의 모든 `museum_id`를 대상(필터가 있으면 해당 ID만)으로 원본 `BM25Reranker.rerank(question, eligible_ids, vector_weight=0, bm25_weight=1)`을 호출합니다. 원본의 BM25 순위만 `score`와 `rank`로 반환합니다.
- **`factory.py`**: `build_hybrid_service()`가 인덱스를 1회 구축하고 `HybridSearchService`에 연결합니다.
- **`fusion.py`**: BM25 원점수와 Vector 거리값은 직접 더하지 않고, 조절 가능한 순위 기반 RRF로 통합합니다. 원본 BM25 `best_span_id`를 함께 보존하도록 보완했습니다.
- **`reranker.py`**: 기존 다국어 Cross-Encoder를 사용합니다(지연 로딩).
- **`service.py`**: 두 검색기를 병렬 실행하고 Fusion 상위 20개를 재정렬하여 Top 10 반환합니다.
- **`cli.py`**: 실제 프로젝트 연결 후 바로 실행할 수 있는 CLI입니다.

> **중요:** 전달받은 `BM25Reranker.rerank`에 벡터 ID 20개만 넘기면 키워드 검색이 독립적으로 후보를 찾지 못합니다. 따라서 어댑터에서는 그 메서드에 **전체 박물관 코퍼스 ID**를 넘깁니다. 원본 메서드 내부의 BM25-only RRF 값은 검색 결과에 넣지 않으며, 실제 Fusion은 `fusion.py`에서 한 번만 계산합니다.

## 1. 의존성

기존 프로젝트의 Python 3.12/Chroma/LLM 설치가 준비되어 있어야 합니다.

프로젝트 루트에서 `uv sync`를 실행합니다. 이미 선언된 패키지를 `uv add`로 다시 추가할 필요는 없습니다.

대부분의 개발 환경에서 `rank-bm25`, `kiwipiepy`는 이미 프로젝트 의존성으로 선언되어 있을 수 있습니다. Cross-Encoder를 실제 실행할 때만 `sentence-transformers`가 필요합니다. 기본 모델 `BAAI/bge-reranker-v2-m3`는 설치 스크립트로 사전 준비하며 검색 실행 중에는 다운로드하지 않습니다. 별도 모델 다운로드 없이 RRF만 검증할 때는 `rerank=False`를 사용하세요.

## 2. 사용법 — 기존 Chroma를 BM25 코퍼스로 활용 (추천 시작점)

```python
from src.hybrid import HybridConfig, build_hybrid_service

config = HybridConfig(
    vector_top_k=20,
    bm25_top_k=20,
    fusion_top_k=20,
    final_top_k=10,
    vector_weight=1.0,
    bm25_weight=1.0,
    rrf_k=60,
)
hybrid = build_hybrid_service(config=config)
response = hybrid.search("서울에서 독립운동과 관련된 박물관")
print(response["search_summary"])
for hit in response["results"]:
    print(hit["museum_id"], hit["name"], hit["score_type"], hit["score"])
```

`build_hybrid_service()`는 기존 `data/vector_db/museum_chroma/museum_documents` 컬렉션의 **전체 문서**를 읽기 전용으로 가져와 BM25 코퍼스를 1회 구축합니다. 초기화 시 컬렉션이 존재하지 않으면 오류를 내며 새 DB/컬렉션을 만들지 않습니다. **컬렉션 문서는 기존 설계대로 박물관 단위(하나의 Chroma ID = 하나의 museum_id)여야 합니다.**

Chroma에 저장된 `name + text` 문서가 BM25 대상이고, 각 문서의 `span_id`는 `chroma:M001` 같은 **내부 합성 식별자**입니다. 이는 실제 `TextSpan`/`SourceDocument` 출처 ID가 아니므로 사용자에게 근거 출처로 제시하면 안 됩니다. 현재 Vector와 동일한 문서를 BM25가 사용하게 되어 검색 결과 비교가 수월하지만, 팀원이 의도한 실제 TextSpan 단위 코퍼스와는 검색 점수가 다를 수 있습니다.

## 3. 사용법 — 팀원 원본에 맞는 TextSpan 코퍼스 파일 사용

Neo4j를 조회하지 않고도 **전체 TextSpan을 별도 JSONL/CSV로 받아서** 원본 BM25 모델의 코퍼스로 사용할 수 있습니다. `museum_id`, `span_id`, `text`는 필수이고, 메타데이터 필터가 필요한 경우 각 박물관의 `metadata`도 제공해야 합니다.

`data/museum_spans.jsonl` 예시:

```jsonl
{"museum_id":"M001","span_id":"S001","text":"독립운동과 관련한 항일 전시","metadata":{"name":"예시 박물관","sido":"서울특별시","adult_fee":0}}
{"museum_id":"M001","span_id":"S002","text":"일제강점기 역사자료","metadata":{"name":"예시 박물관","sido":"서울특별시","adult_fee":0}}
{"museum_id":"M002","span_id":"S003","text":"현대미술 작가 작품","metadata":{"name":"다른 박물관","sido":"경기도","adult_fee":3000}}
```

```python
from src.hybrid import build_hybrid_service

hybrid = build_hybrid_service(
    corpus_source="file",
    corpus_path="data/museum_spans.jsonl",  # 또는 .csv
)
result = hybrid.search("독립운동 박물관")
```

`SpanDocument` 목록을 이미 메모리에 가지고 있다면:

```python
from src.hybrid import BM25SpanRetriever, HybridSearchService, SpanDocument

spans = [SpanDocument(museum_id="M001", span_id="S001", text="..."), ...]
meta = {"M001": {"name": "박물관", "sido": "서울특별시"}}
bm25 = BM25SpanRetriever(spans, metadata_by_museum=meta)
hybrid = HybridSearchService(bm25_retriever=bm25)
```

TextSpan 파일에는 **전체 검색 대상 코퍼스**가 있어야 전체 코퍼스 기반 IDF가 정확하게 계산됩니다. 일부 박물관만 담긴 파일이라면 그 일부에 대한 검색이 됩니다. 문서에 메타데이터가 없는데 지역·요금 필터가 들어오면 조건을 무시하지 않고 명시적으로 예외를 발생시킵니다.

## 4. 가중치와 후보 수 설정

```python
from src.hybrid import HybridConfig

# BM25 강조
cfg = HybridConfig(vector_weight=0.7, bm25_weight=1.3)
# Vector 강조
cfg = HybridConfig(vector_weight=1.3, bm25_weight=0.7)
```

동일한 설정을 `.env`로도 적용할 수 있습니다(공장 함수가 기존 프로젝트 `.env` 파일을 먼저 불러옴).

```dotenv
HYBRID_VECTOR_TOP_K=20
HYBRID_BM25_TOP_K=20
HYBRID_FUSION_TOP_K=20
HYBRID_FINAL_TOP_K=10
HYBRID_RRF_K=60
HYBRID_VECTOR_WEIGHT=1.0
HYBRID_BM25_WEIGHT=1.0
HYBRID_RERANK_MODEL=BAAI/bge-reranker-v2-m3
HYBRID_RERANK_FAILURE_POLICY=rrf_fallback
HYBRID_RETRIEVER_FAILURE_POLICY=raise
```

**RRF 합산은 Fusion 단계에서만 수행합니다.** BM25 모듈에서 내부적으로 계산한 RRF 값은 순위 산출용일 뿐, Fusion에 전달하지 않습니다. 최종 Reranker 성공 시 해당 점수로 정렬하며 RRF는 동점일 때만 사용합니다.

## 5. CLI/테스트

```bash
# 현재 프로젝트 환경에 DB, OpenAI 환경변수, rank-bm25/kiwi가 있는 경우
python -m src.hybrid.cli "독립운동 관련 박물관" --no-rerank
python -m src.hybrid.cli "독립운동 관련 박물관" --bm25-weight 1.4 --vector-weight 0.6
python -m src.hybrid.cli "독립운동 관련 박물관" --corpus data/museum_spans.jsonl

# 표준 라이브러리 기반 통합 계약 테스트 (rank-bm25 미설치 시 테스트용 BM25 대역 사용)
python -m unittest discover -s src/hybrid/tests -p 'test_*.py' -v
```

검색 결과는 기존 포맷(`tool`, `status`, `results`, `source_ids`, `warnings`, `search_summary`)을 유지합니다. `results`에는 `vector_rank`, `bm25_rank`, `fusion_score`, `rerank_score`, `score`, `score_type`, `best_span_id`, `best_span_text` 등이 포함됩니다. `rerank=False`는 Cross-Encoder를 실행하지 않고 RRF 결과를 확인할 수 있는 평가 모드입니다.

## 6. 확인해야 할 제한

- **현재 업로드된 파일은 검색 모듈(알고리즘)뿐**이므로, 실행할 전체 문서 코퍼스와 박물관 메타데이터는 별도로 필요합니다. 기본 설정에서는 기존 Chroma에서 가져옵니다.
- **실제 데이터 검증은 아직 수행하지 않았습니다.** 현재 제공 파일/환경에는 박물관 데이터와 실 OpenAI/Chroma 연결이 없으므로, 모의 검색기와 테스트용 BM25 구현으로 동작 계약만 검증했습니다. 실운영 시 `rank-bm25`, `kiwipiepy`, Chroma, Cross-Encoder 추론 및 품질 측정을 별도 확인해야 합니다.
- 검색 필터는 지역(`sido`·`sidos`·`sigungu`), 소유 유형, 입장료 범위를 적용합니다. 모르는 필터가 넘어오면 조용히 무시하지 않고 예외를 발생시킵니다. 원본 Vector 질의 분석기의 `unsupported_constraints`는 응답의 경고에 남습니다.
- 원본 BM25 로직처럼 어휘 점수 0 이하 후보를 결과에서 제외하므로 검색 결과가 20개보다 적을 수 있습니다. 불필요한 후보를 채우지 않습니다.
- BM25의 문서 단위는 입력 코퍼스 단위입니다. Chroma로 로드하면 박물관 1건, TextSpan JSONL로 로드하면 구간 단위로 IDF를 계산하고 박물관별 최고 구간 점수를 사용합니다. 두 방식의 품질이 같다고 가정하지 마세요.
- 이 패키지는 `src/agent/graph.py`를 자동으로 연결하거나 API 라우터를 변경하지 않습니다. 상위 통합에서는 `build_hybrid_service()`를 생성하고 `hybrid.search()` 호출 결과를 소비해야 합니다.
- 하이브리드 검색기는 호출할 때마다 인덱스를 만들지 않고 생성 시 한 번 구축합니다. 코퍼스를 업데이트하면 서비스 인스턴스를 새로 생성해 인덱스를 갱신하세요.

## 7. `src/hybrid/hybrid_rag_agent.py` — LangGraph 전용 인터페이스와 검색 과정 확인

기존 Vector Agent처럼 상위 그래프에 바로 등록할 수 있는 Agent 래퍼가 추가되었다. **자동으로 사용자 프로젝트의 `graph.py`를 수정하지는 않는다.**

```python
from src.hybrid.hybrid_rag_agent import HybridRAGAgent

agent = HybridRAGAgent()  # lazy: 실제 DB 로드는 최초 검색에서 실행
response = agent.retrieve("독립운동 관련 박물관", top_k=10)
print(response["results"])
print(response["search_summary"]["stages"])

# LangGraph ToolNode
search_tool = agent.as_langchain_tool()  # name='museum_hybrid_retrieve'
# graph_builder.add_node('tools', agent.as_langgraph_tool_node())

# StateGraph 고정 노드
search_node = agent.as_langgraph_node(input_key="question", output_key="hybrid_result", top_k=10)
# graph_builder.add_node('hybrid_retrieve', search_node)
```

실제 검색 결과·과정:

```powershell
uv run python -m src.hybrid.hybrid_rag_agent
uv run python -m src.hybrid.hybrid_rag_agent "독립운동 관련 박물관" --show-stages --show-fusion
uv run python -m src.hybrid.hybrid_rag_agent "독립운동 관련 박물관" --json
uv run python -m src.hybrid.hybrid_rag_agent --info
```

기본 CLI 출력은 단계별 시간·후보 수·경고, 최종 후보 10개의 `museum_id`, 이름, 지역, 개별 검색 순위, 재정렬 점수, 설명문을 보여준다. `--show-stages`는 BM25와 Vector 각자의 검색 결과를, `--show-fusion`은 RRF 결과를 추가 출력한다. `--no-rerank`는 RRF만 실행한다.

원본 `vector_search_rag_agent.py`와 동일하게 최종 자연어 답변을 생성하거나 스스로 재검색을 반복하지 않는다. 도구 이름은 `museum_hybrid_retrieve`로 독립된다. 신규 테스트/성능 평가는 차후 진행한다.

### 배치 위치 (단일 파일 경로)

`hybrid_rag_agent.py`는 **`src/hybrid/hybrid_rag_agent.py`**에만 위치한다. 별도의 `src/service/hybrid_rag_agent.py`는 필요 없으며, 모든 Import와 CLI는 `src.hybrid.hybrid_rag_agent` 경로를 사용한다.
