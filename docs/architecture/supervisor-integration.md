# Supervisor와 팀 Hybrid 연동 안내

## 한눈에 보기

| 항목 | 내용 |
|---|---|
| 진입점 | `src.agent.supervisor.connect.build_connected_supervisor()` · CLI `python -m src.agent.supervisor.run` |
| 기본 검색 | `HybridRAGAgent`: 온톨로지 후보 필터 → BM25 + Chroma Vector → RRF → Cross-Encoder |
| Graph | `--with-neo4j`(또는 `graph_retriever` 전달)일 때만 연결. Hybrid는 Neo4j를 조회하지 않음 |
| 출처 | CSV와 본문이 정확히 일치할 때만 원문 출처·속성 근거(`metadata_provenance`)를 붙임 |
| 검증 | Answer → 인용 구조 검사 → Verifier. 실패 시 1회 재검색, 기록이 없는 조건이면 바로 보류 |
| 가드레일 | 입력은 검색 전, 최종 답변은 반환 전에 검사 (13절) |
| 관련 문서 | 설계 이유는 [기술 결정](../decisions/README.md), 문제 해결 기록은 [supervisor-retrieval-issues](../records/supervisor-retrieval-issues.md) |

기존 `src.agent.build_graph`와 Streamlit UI는 자동으로 새 Supervisor를 쓰지 않습니다.

## 0. 출처를 붙이는 방식

- 검색 결과의 박물관 ID는 원문 출처 ID가 아닙니다.
- 기본 연결은 벡터 DB를 만든 `data/processed/museum_final_738.csv`에서 원문 문서 ID, 원본 파일 행 위치, 본문 구간, 기록된 원문 URL을 찾아 Supervisor에 넘깁니다.
- **박물관 ID와 전체 본문이 CSV와 정확히 같고, 본문 구간이 유효하게 연결된 경우에만** 출처를 붙입니다. 파일이 없거나 본문이 바뀌면 출처를 만들지 않으며, 답변이 보류될 수 있습니다.
- 현재 로컬 Chroma 738건을 CSV와 대조하면 738건 모두 원본 문서 ID와 파일 위치가 있고, 22건에는 원문 URL도 있습니다. 박물관 홈페이지와 원문 URL은 별개입니다.
- 이 연결은 CSV에 기록된 출처를 추적할 뿐, URL의 현재 상태나 사실의 정확성을 보증하지 않습니다. 문서별 `match_trust`(자동 매칭/사람 검수 여부)를 최종 검증에서 함께 확인해야 합니다.
- CSV는 최초 검색 때 읽어 재사용하므로, CSV를 바꾼 뒤에는 Supervisor를 다시 생성해야 합니다.

## 1. 기준 문서와 설계 결정

첨부한 `folder-structure.md`, `LangGraph_Hybrid_연동가이드.md`, `전체LangGraph개발자가 알아야 할 벡터rag정보.md`를 기준으로 작성했음.

문서에서 확인한 사실:
- `src/agent/`가 LangGraph 실행 흐름을 담당함.
- 기존 `src/agent/graph.py`, `state.py`, `__init__.py`가 이미 존재함.
- Vector 서비스는 `VectorSearchRetriever.retrieve(query, top_k)`로 호출함.
- Graph 서비스는 `Neo4jText2Cypher.search(question, k)`로 호출함.
- Vector 반환값의 `source_ids`는 박물관 ID임. 원문 문서 ID가 아님.
- Vector 상태와 진단 정보를 보존해야 하며, `partial`만으로 실패를 확정하면 안 됨.
- 동일 박물관의 서로 다른 근거 구간을 `museum_id`만으로 합치면 안 됨.
- 기존 Ragas 경로는 Graph 단독이므로 새 Supervisor를 쓰려면 평가 호출부도 교체해야 함.

이번 패키지의 설계 제안:
- 기존 `.py` 본문은 첨부되지 않았으므로 안전하게 `src/agent/supervisor/` 하위 패키지를 추가했음.
- 실제 팀 Hybrid `HybridRAGAgent.retrieve(query, top_k)`를 기본 연결함. 기존에 주입하던 `state -> dict` 함수와 컴파일된 하위 그래프 `.invoke`도 지원함.
- 재검색은 기본 최대 1회임. 최초 검색을 포함하면 최대 2회이며 0~2회로 설정 가능함.
- 외부 검색 결과가 `verified`, `retry_count`, 원본 질문을 임의로 변경하지 못하도록 허용 필드만 받아들임.

## 2. 어디에 넣는가

ZIP 내부의 상대 경로를 프로젝트 루트에 맞춰 복사함. 기존 파일 전체를 바꾸지 않음.

```text
src/agent/
├── graph.py                  # 기존 파일 유지
├── state.py                  # 기존 파일 유지
├── neo4j_text2cypher.py       # 기존 파일 유지
└── supervisor/               # 이번에 추가하는 폴더
    ├── __init__.py           # 공개 함수
    ├── state.py              # 공통 상태·입출력 타입
    ├── adapters.py           # 팀원 검색 결과 형식 연결
    ├── nodes.py              # 라우팅·호출·검증·재검색·종료
    ├── graph.py              # 실제 LangGraph 노드·간선 조립
    ├── llm.py                # 선택 사용: LLM 라우팅·답변·검증
    ├── connect.py            # 팀원 함수 연결 지점
    └── run.py                # 데모 및 실서비스 실행 CLI

tests/unit/agent/
├── test_supervisor_contract.py
├── test_supervisor_llm.py
└── test_supervisor_graph_runtime.py
```

`src/agent/__init__.py` 및 기존 `build_graph`는 변경하지 않았음. 새 진입점은 `src.agent.supervisor.build_supervisor` 또는 `src.agent.supervisor.connect.build_connected_supervisor`임. 기존 UI가 기존 `build_graph`를 호출하면 자동으로 새 Supervisor가 실행되는 것은 아님.

## 3. 역할 분담

| 담당 | 구현 범위 |
|---|---|
| Hybrid 담당 팀원 | BM25 + Vector 검색, 조건 유지, RRF 결합, Cross-Encoder 재정렬, 근거·진단 반환. Neo4j 검색은 별도. |
| Supervisor 담당 | 질문 라우팅, 팀원 함수 호출, 공통 State, Answer·Verifier 연결, 재검색 예산, 종료·보류 |
| Answer·Verifier 담당 | 기존 에이전트가 있으면 주입함. 없으면 제공한 `llm.py`를 초기 구현으로 사용 가능함 |

Supervisor 안에서 Hybrid 검색 알고리즘이나 Chroma 임베딩을 다시 구현하지 않았음.

## 4. 실제 흐름

```text
질문 → 입력 가드레일 → 초기화 → Supervisor 경로 결정
                  ├─ 구조 조건(편의시설·개관 요일) → Hybrid (온톨로지 후보 필터 적용)
                  ├─ 단순 지역+주제               → Hybrid (지역 필터 적용)
                  ├─ 그 밖의 질문                  → LLM 라우터가 Hybrid / Graph / Vector 선택
                  │                                   (기관 관계 등은 Graph, 연결된 경우)
                         ↓
                  근거·진단 정규화 + CSV 출처 연결
                         ↓
                  Answer → 인용 구조 검사 → 실제 Verifier
                         ↓
                  Supervisor 결과 판정
                  ├─ 통과: 답변·출처 반환
                  ├─ 기록이 없는 조건: 재시도 없이 이유를 안내하며 보류
                  ├─ 실패, 예산 남음: 재검색 (구조 정보 부족 + Graph 연결 시 Graph)
                  └─ 실패, 예산 소진: 답변 보류
                         ↓
                  출력 가드레일 → 최종 결과
```

후보 필터와 지역 필터를 앞단에 두는 이유는 [온톨로지 후보 필터](../decisions/ontology-filter-routing.md)와 [지역·주제 검색 설계](../decisions/region-theme-routing.md)에 있습니다.

Hybrid만 연결해도 실행 가능함. 단, Vector·Graph 단독 서비스가 연결되지 않으면 해당 경로 선택을 Hybrid로 명시적으로 전환함. 이것을 독립된 세 검색 경로가 모두 완성됐다고 설명하면 안 됨.

## 5. Hybrid 입력

실제 기본 경로는 `HybridRAGAgent.retrieve(query, top_k)`임. 아래는 별도로 주입하는 상태 기반 검색 함수의 계약임.

```python
def hybrid_search_node(state: dict) -> dict:
    question = state["question"]
    top_k = state["top_k"]
    retry_count = state.get("retry_count", 0)
    feedback = state.get("feedback", "")
    # 팀원의 기존 복합 검색 실행 후 아래 형식 반환
```

`question`은 재검색 때도 사용자 원본 질문을 그대로 유지함. 상태 기반 함수에는 `feedback`을 전달하지만, 현재 팀 `HybridRAGAgent.retrieve`는 질문과 `top_k`만 받으므로 피드백을 이용한 검색어 수정은 구현되어 있지 않음. Supervisor가 재호출한다고 검색 결과가 자동으로 좋아지는 것은 아님. 필수 지역·요금·관계 조건은 임의로 완화하지 않음.

## 6. Supervisor가 받는 Hybrid 출력

아래 값은 형식 설명용 가상 예시임.

```python
{
    "evidence": [
        {
            "museum_id": "M0001",
            "name": "예시 박물관",
            "text": "검색에서 확인한 실제 근거 구간",
            "span_id": "span_001",
            "source_doc_ids": ["doc_001"],
            "source_urls": [],
            "sido": "경기도",
            "sigungu": "예시 시군구",
            "retriever": "hybrid",
            "metadata": {"graph_path": "실제로 확인한 경로·속성만 전달"}
        }
    ],
    "vector_evidence": [],
    "vector_source_ids": ["M0001"],
    "vector_search_status": "partial",
    "vector_search_diagnostics": {
        "warnings": [],
        "unsupported_constraints": ["지역 조건"],
        "applied_filters": {}
    },
    "graph_evidence": [],
    "hybrid_search_diagnostics": {
        "resolved_constraints": ["지역 조건"],
        "unresolved_constraints": []
    }
}
```

필수는 최종 `evidence` 목록임. 근거별 `museum_id`와 비어 있지 않은 `text`가 필요함. 답변에 인용하려면 실제 문서 ID·출처 위치·원문 URL 중 확인 가능한 출처 정보도 필요함. `source_doc_ids`에 박물관 ID를 복사하면 안 됨.

실제 팀 Hybrid 결과의 `results`, `warnings`, `unsupported_constraints`, `search_summary`는 어댑터에서 `evidence`와 `hybrid_search_diagnostics`로 변환함. 아래 예시는 상태 기반 함수의 형식이며 `resolved_constraints`가 실제로 자동 산출된다는 의미는 아님. 진단 문자열만으로 조건이 충족되었다고 승인하지 않음.

CSV와 일치한 근거에 추가되는 필드는 다음과 같습니다.

- `source_doc_ids`, `source_locator`, `source_urls`
- `source_documents`: 실제 원본 경로·URL과 `match_trust`
- `source_spans`: 어떤 본문 구간이 어떤 문서와 연결되는지
- `source_scope: text`: 이 연결은 **본문에만 적용**되며, 요금·주소·운영시간 같은 메타데이터의 출처까지 증명하지 않습니다. 메타데이터 근거는 14절의 `metadata_provenance`입니다.

CSV가 없으면 `hybrid_search_diagnostics.provenance_csv_status`가 `unavailable`로 표시됩니다. Vector 단독 경로에서도 같은 CSV 매칭을 씁니다. CSV 경로를 바꾸려면 `build_connected_supervisor(provenance_csv=...)`를 사용합니다.

`top_k`는 최종 답변에 전달할 **근거 수**임. 서로 다른 박물관 K개를 보장하는 값이 아님. 반환 순위는 팀원 함수의 순서를 유지하고, 정확히 같은 근거만 정리한 뒤 마지막에 K개로 제한함. 서로 다른 근거의 점수를 임의로 합산하지 않았음.

## 7. 설치 및 데모

프로젝트 루트에서 실행함. Python 3.12 이상을 대상으로 작성했음.

```powershell
uv sync
uv run python -m src.agent.supervisor.run --demo --question "경기도 전통문화 박물관 추천"
uv run python -m src.agent.supervisor.run --demo --empty-demo --question "자료에 없는 질문"
```

첫 번째는 가상 근거로 정상 종료, 두 번째는 근거 없음 → 1회 재검색 → 보류 흐름을 실행함. 데모는 실제 LangGraph 라이브러리가 필요함. 검색 결과와 판정은 가상임.

실제 Hybrid 검색은 Chroma 컬렉션, 질문 분석에 필요한 환경과 선택한 Cross-Encoder 모델이 필요함. 준비 절차는 `src/hybrid/README.md` 참고.

## 8. 실제 서비스 연결 예제

팀원이 만든 함수를 호출하는 쪽에서 아래 팩토리를 사용함. `team_hybrid_node`와 `team_graph_retriever`는 실제 객체를 전달받는 매개변수이며, 존재하지 않는 모듈을 가정한 import가 아님.

```python
from src.agent.supervisor.connect import build_connected_supervisor
from src.service.vector_search_rag_agent import VectorSearchRetriever


def create_supervisor(team_hybrid_node, team_graph_retriever, team_llm):
    return build_connected_supervisor(
        hybrid_node=team_hybrid_node,
        vector_retriever=VectorSearchRetriever(),
        graph_retriever=team_graph_retriever,  # .search(question, k) 지원 객체
        llm=team_llm,                       # 팀에서 설정한 ChatOpenAI 객체
        max_retries=1,
    )
```

팀 Hybrid를 기본 연결하는 경우:

```python
app = build_connected_supervisor(
    llm=team_llm,
)
result = app.invoke({"question": "경기도 전통문화 박물관 추천", "top_k": 5})
print(result["answer"])
print(result["route"], result["status"], result["retry_count"])
print(result["sources"])
print(result["trace"])
```

팀원의 Hybrid가 컴파일된 LangGraph이면 `hybrid_node=team_hybrid_graph.invoke`, `hybrid_accepts_config=True`로 연결함. 이 경우에도 하위 그래프의 반환값에 최종 `evidence`와 진단 필드가 있어야 함. 비동기 전용 함수는 이 동기 어댑터에 직접 넣지 말고 별도 비동기 연동이 필요함.

팀 Hybrid를 CLI로 연결하는 경우:

```powershell
uv run python -m src.agent.supervisor.run --team-hybrid --model TEAM_MODEL --question "경기도 전통문화 박물관 추천"
```

별도의 상태 기반 검색 함수를 사용하는 경우 실제 import 경로를 지정함.

```powershell
uv run python -m src.agent.supervisor.run --hybrid actual_team_module:actual_function --with-vector --model TEAM_MODEL --question "경기도 전통문화 박물관 추천" --out outputs/supervisor/result.json
```

`TEAM_MODEL`은 구조화 출력을 지원하는 팀의 실제 모델명으로 교체함. 또는 로컬 `.env`의 `SUPERVISOR_MODEL`을 설정하고 `--model`을 생략함. 실제 API 키는 기존 `OPENAI_API_KEY`를 사용하며 저장소에 올리지 않음.

## 9. 답변 및 검증 연결

`llm.py`는 LLM을 이용한 초기 라우터·답변 생성·검증 구현임. 기존 에이전트가 있으면 아래 세 함수를 직접 주입할 수 있음.

```python
route_question(state, config) -> RouteDecision
answer_question(state, config) -> AnswerDraft
verify_answer(state, config) -> VerificationResult
```

답변은 `E1`, `E2`처럼 이번 검색에서 배정한 근거 라벨을 사용함. `AnswerDraft("설명 [E1]", ["E1"])` 형식임. 실제 doc_id와 URL은 해당 evidence에 남아 있음.

구조 검사는 존재하지 않는 인용·출처 없는 근거를 막음. 그 뒤 실제 Verifier를 실행함. `partial` 또는 Vector의 `no_results`만으로 보류하지 않으며, Graph를 포함한 최종 근거가 질문을 충족하는지 확인함. `missing_aspects`가 남으면 passed가 true여도 통과시키지 않음.

LLM 검증은 독립적인 공식 사실 확인이나 정확성 보장이 아님. 정적 데이터만으로 현재 무료·오늘 개관·현재 특별전을 보증하지 않음. 정식 성능 평가는 별도로 필요함.

## 10. UI·평가·추적 연결

Streamlit은 최종 `answer`, `sources`, `route`, `status`, `failure_reason`을 표시할 수 있음. 상위 `app.invoke(..., config={"callbacks": [...], "tags": [...]})`의 config를 제공한 LLM 함수와 검색 호출에 전달함.

단, 원래 Vector/Graph 인터페이스에는 config 인자가 없으므로 내부 검색 서비스의 LLM 호출까지 추적되는지는 해당 서비스의 callback 지원 여부를 따로 확인해야 함. Langfuse 연결 완료를 뜻하지 않음.

Hybrid 비교는 별도 `src/evaluation/hybrid/ragas_eval.py`에서 수행하며, Neo4j 전용 평가는 `src/evaluation/langgraph/ragas_eval.py`에 남아 있음. 현재 기본 평가셋은 v2 196문항이며 사람 검수 전 초안이므로 점수는 잠정치임. v1 150문항은 이전 기준선으로 보존함.

NeMo Guardrails, 실제 Langfuse 연결, Streamlit 화면 변경, RAGAS 실행, 팀원 검색 알고리즘 수정은 포함하지 않았음. 이 패키지는 1회 질문 처리용이며 대화 메모리·checkpointer는 추가하지 않았음.

## 11. 검증 및 적용 전 확인

```powershell
uv run python -m pytest tests/unit/agent/test_supervisor_contract.py tests/unit/agent/test_supervisor_llm.py tests/unit/agent/test_supervisor_graph_runtime.py -q
```

팀 Hybrid와 Supervisor 연결 테스트는 `tests/unit/agent/test_hybrid_integration.py`에 있음. 이 테스트는 외부 모델·DB 호출을 대체하므로 실제 환경 연결 검증과 구분해야 함.
CSV 출처 대조 테스트는 `tests/unit/agent/test_csv_provenance.py`에 있음.

적용 후 기존 팀 저장소의 테스트도 실행해야 함. 새 테스트는 pytest 방식이며 기존 unittest 명령만으로 실행되지 않음. 실제 Neo4j·Chroma·LLM 연결은 팀 환경에서 별도로 확인해야 함.

## 12. 참고

Supervisor 입력의 `top_k` 상한은 50이지만 실제 팀 Hybrid는 설정된 `fusion_top_k` 이내만 허용함(기본 20). 최대 재시도는 2회임. 설정에 맞지 않는 `top_k` 요청은 검색 실패로 처리되므로 팀 설정에 맞춰 사용해야 함.

LangGraph 공식 API: https://docs.langchain.com/oss/python/langgraph/graph-api
LangChain 구조화 출력 API: https://reference.langchain.com/python/langchain-openai/langchain_openai/chat_models/base/ChatOpenAI/with_structured_output

## 13. Supervisor 가드레일

- `build_connected_supervisor()`는 `src.guardrails`의 입력·출력 검사를 연결합니다. 입력은 검색 전에, 최종 답변은 반환 전에 검사합니다.
- 차단되거나 검사에 실패하면 `status=blocked`와 안내 문구를 반환합니다.
- 실제 가드레일은 `GUARDRAILS_MODEL` 설정과 API 키를 씁니다. `build_supervisor()`에 직접 주입할 때는 `guardrails_factory`를 넘겨야 합니다.
- LangGraph 중간 노드 스트림에는 검사 전 답변 초안이 섞일 수 있으므로, 사용자 화면에는 `invoke()`의 최종 결과만 표시해야 합니다.
- Streamlit UI는 별도의 가드레일 경로를 씁니다.

## 14. 라우팅과 속성 근거 보완

**라우팅 (첫 시도, 위에서부터 처음 맞는 규칙)**

| 순서 | 규칙 | 경로 | 비고 |
|---|---|---|---|
| 1 | `route_override`로 사용자가 경로를 지정 | 지정한 경로 | 재시도에서도 유지 |
| 2 | 단순 `지역 + 주제` 문장 (`region_theme.py`) | Hybrid | 지역 필터를 검색 전에 적용 |
| 3 | 편의시설·개관 요일 같은 기록된 조건 (`ontology_filter.py`) | Hybrid | 후보 필터가 후보를 먼저 거름. `--no-ontology-filter`로 끔 |
| 4 | 준비된 Graph 쿼리와 맞는 질문 (같은 시군구·같은 기관·인용 출처 등) | Graph | Graph가 연결된 경우만. LLM 호출 없음 |
| 5 | 위에 해당하지 않음 | LLM 라우터 | 설명으로 답하는 질문은 지역이 있어도 Hybrid, 레코드 사이의 구조가 필요한 질문만 Graph |

- 2·3·4번은 기본 `HybridRAGAgent` 연결에서만 적용됩니다. 사용자 정의 Hybrid를 주입하면 적용되지 않을 수 있습니다.
- 연결되지 않은 경로가 선택되면 Hybrid로 전환합니다.

**재시도 (첫 시도가 검증에 실패한 경우)**
- 경로를 지정했다면 같은 경로를 씁니다.
- 직전이 Graph였다면 기본은 **Hybrid**입니다. Graph가 근거를 찾았고 부족한 것이 요금·운영시간 같은 구조 정보일 때만 Graph를 다시 씁니다.
- 직전이 Hybrid였다면 구조 정보가 부족하고 Graph가 연결돼 있을 때만 Graph로 갑니다.
- 후보 필터가 0건을 냈다면 재시도 없이 어떤 조건의 기록이 없는지 안내하며 보류합니다.
- 재검색 결과는 이전 결과를 대체합니다.

**한계**
- LLM 라우터의 선택은 항상 정확하지 않습니다. 터미널의 `route`와 `reason`으로 확인하세요.
- 이 규칙이 평가에서 바뀐 이유는 [Supervisor 검색 문제 기록](../records/supervisor-retrieval-issues.md#5-라우터가-설명형-질문을-graph로-보냄)에 있습니다. 다만 수정 후 재평가는 아직 하지 않았습니다.
- 후보 필터의 기본 데이터는 로컬 조회표입니다. 매 질문마다 Neo4j에 접속하지 않습니다.

**속성 근거 (`metadata_provenance`)**
- Hybrid/Vector 결과의 문서 ID와 전체 텍스트가 CSV와 일치하고 출처 범위 검사를 통과하면, CSV의 속성값을 `metadata_provenance`로 따로 붙입니다.
- 대상 필드는 지역·주소·요금·운영시간·휴관 규칙(`closure_rule_raw`)·편의시설(`amenities_raw`)입니다. 목록은 `provenance.py`의 `METADATA_FIELDS`에 있습니다.
- 검색 결과에 같은 속성이 있으면 값도 일치해야 합니다. 시도 별칭은 원본 값과 정규화 사실을 함께 기록합니다.
- 설명문의 `source_scope=text`와 속성 근거는 별개입니다. 검색기가 임의로 넣은 `metadata_provenance`는 지우고, 신뢰된 CSV에서 다시 만듭니다. Graph 고유 출처는 유지합니다.
- 이 근거는 가공된 CSV 행을 가리킬 뿐, 원본 공식 문서가 속성을 검증했다는 뜻이 아닙니다. 사람 검수나 최신성도 보장하지 않으며, 요금 0원에는 기존 예외 확인 규칙이 적용됩니다.
- 변경 효과는 평가셋과 실제 서비스 환경에서 따로 측정해야 합니다.


## 현재 라우팅 우선순위 (2026-11-14 코드 대조)

기준은 src/agent/supervisor/nodes.py의 supervisor입니다.

1. 재시도는 이전 근거·누락 조건·명시적 경로에 따라 판단합니다.
2. 첫 시도에서 명시한 route_override가 있으면 그 경로를 사용합니다.
3. 단순 지역+주제 질문은 Hybrid로 보냅니다.
4. 인식 가능한 구조 조건은 온톨로지 후보 필터를 사용하는 Hybrid로 보냅니다.
5. 연결된 Graph의 준비된 쿼리에 맞으면 Graph로 보냅니다.
6. 나머지는 연결된 경로 목록을 전달해 LLM이 판단합니다.

연결되지 않은 검색 경로는 Hybrid로 대체될 수 있습니다. Graph 재시도는 항상 Graph로 고정되지 않습니다. 자동 경로에서 이전 Graph 근거가 없거나 부족한 부분이 구조 조건이 아니면 Hybrid로 전환합니다.

온톨로지 후보 필터의 기본 백엔드는 738 CSV와 공용 규칙으로 만든 로컬 조회표입니다. 매 질문마다 Neo4j에 접속하는 의미가 아닙니다. Streamlit은 별도 검색·응답 경로이며 이 Supervisor 흐름을 자동으로 공유하지 않습니다.

평가에서 supervisor_full은 연결형 Supervisor 전체 경로를, supervisor는 Hybrid 고정 비교를, langgraph.ragas_eval은 기존 GraphRAG 경로를 평가합니다. 세 결과를 동일한 시스템의 점수로 취급하지 않습니다.
