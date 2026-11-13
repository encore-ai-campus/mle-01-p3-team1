# Supervisor 전용 구현 및 팀원 연동 안내

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
- 팀원의 최종 Hybrid 함수명·생성자는 아직 제공되지 않았으므로 실제 경로를 추측해서 import하지 않았음.
- Hybrid 함수는 `state -> dict` 또는 컴파일된 하위 그래프의 `.invoke`로 연결하도록 제안했음.
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
| Hybrid 담당 팀원 | Neo4j + Vector 복합 검색, 조건 유지, 결과 통합, 필요시 재정렬, 근거·진단 반환 |
| Supervisor 담당 | 질문 라우팅, 팀원 함수 호출, 공통 State, Answer·Verifier 연결, 재검색 예산, 종료·보류 |
| Answer·Verifier 담당 | 기존 에이전트가 있으면 주입함. 없으면 제공한 `llm.py`를 초기 구현으로 사용 가능함 |

Supervisor 안에서 Hybrid 검색 알고리즘이나 Chroma 임베딩을 다시 구현하지 않았음.

## 4. 실제 흐름

```text
질문 → 초기화 → Supervisor 경로 결정
                  ├─ Vector 서비스
                  ├─ Graph 서비스
                  └─ 팀원 Hybrid 함수
                         ↓
                  근거·진단 정규화
                         ↓
                  Answer → 인용 구조 검사 → 실제 Verifier
                         ↓
                  Supervisor 결과 판정
                  ├─ 통과: 답변·출처 반환
                  ├─ 실패, 예산 남음: Hybrid 재검색
                  └─ 실패, 예산 소진: 답변 보류
```

Hybrid만 연결해도 실행 가능함. 단, Vector·Graph 단독 서비스가 연결되지 않으면 해당 경로 선택을 Hybrid로 명시적으로 전환함. 이것을 독립된 세 검색 경로가 모두 완성됐다고 설명하면 안 됨.

## 5. 팀원과 합의할 Hybrid 입력

아래는 확정된 기존 함수가 아니라 이번 코드가 제안하는 연결 계약임.

```python
def hybrid_search_node(state: dict) -> dict:
    question = state["question"]
    top_k = state["top_k"]
    retry_count = state.get("retry_count", 0)
    feedback = state.get("feedback", "")
    # 팀원의 기존 복합 검색 실행 후 아래 형식 반환
```

`question`은 재검색 때도 사용자 원본 질문을 그대로 유지함. `feedback`에는 부족한 근거·조건을 전달함. 이를 활용한 검색어 확장·후보 확대·필터 수정은 Hybrid 담당이 구현해야 함. Supervisor가 재호출한다고 검색 결과가 자동으로 좋아지는 것은 아님. 필수 지역·요금·관계 조건은 임의로 완화하지 않음.

## 6. 팀원과 합의할 Hybrid 출력

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

`hybrid_search_diagnostics`는 이번에 추가 제안한 확장 필드임. `resolved_constraints`라는 문자열만 있다고 사실로 승인하지 않음. 관련 속성·경로·근거가 최종 evidence에 있어야 Verifier가 대조할 수 있음.

`top_k`는 최종 답변에 전달할 **근거 수**임. 서로 다른 박물관 K개를 보장하는 값이 아님. 반환 순위는 팀원 함수의 순서를 유지하고, 정확히 같은 근거만 정리한 뒤 마지막에 K개로 제한함. 서로 다른 근거의 점수를 임의로 합산하지 않았음.

## 7. 설치 및 데모

프로젝트 루트에서 실행함. Python 3.12 이상을 대상으로 작성했음.

```powershell
uv add langgraph langchain-openai python-dotenv
uv add --dev pytest
uv run python -m src.agent.supervisor.run --demo --question "경기도 전통문화 박물관 추천"
uv run python -m src.agent.supervisor.run --demo --empty-demo --question "자료에 없는 질문"
```

첫 번째는 가상 근거로 정상 종료, 두 번째는 근거 없음 → 1회 재검색 → 보류 흐름을 실행함. 데모는 실제 LangGraph 라이브러리가 필요함. 검색 결과와 판정은 가상임.

`requirements-supervisor.txt`는 참고용 의존성 범위이며 팀의 기존 `pyproject.toml`·`uv.lock`을 덮어쓰기 위한 파일이 아님.

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

Hybrid만 먼저 연동하는 경우:

```python
app = build_connected_supervisor(
    hybrid_node=team_hybrid_node,
    llm=team_llm,
)
result = app.invoke({"question": "경기도 전통문화 박물관 추천", "top_k": 5})
print(result["answer"])
print(result["route"], result["status"], result["retry_count"])
print(result["sources"])
print(result["trace"])
```

팀원의 Hybrid가 컴파일된 LangGraph이면 `hybrid_node=team_hybrid_graph.invoke`, `hybrid_accepts_config=True`로 연결함. 이 경우에도 하위 그래프의 반환값에 최종 `evidence`와 진단 필드가 있어야 함. 비동기 전용 함수는 이 동기 어댑터에 직접 넣지 말고 별도 비동기 연동이 필요함.

CLI로 연결하는 경우 아래 `actual_team_module:actual_function`을 팀원이 알려준 실제 import 경로와 함수명으로 바꿈. 문서에는 이 경로가 없어 고정하지 않았음.

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

기존 `src/evaluation/langgraph/ragas_eval.py`가 이 Supervisor를 호출하도록 변경해야 Hybrid 평가가 됨. 기존 평가 코드를 이 ZIP에서 수정하지 않았음. 300문항 초안의 사람 검수 상태도 유지해야 함.

NeMo Guardrails, 실제 Langfuse 연결, Streamlit 화면 변경, RAGAS 실행, 팀원 검색 알고리즘 수정은 포함하지 않았음. 이 패키지는 1회 질문 처리용이며 대화 메모리·checkpointer는 추가하지 않았음.

## 11. 검증 및 적용 전 확인

```powershell
uv run python -m pytest tests/unit/agent/test_supervisor_contract.py tests/unit/agent/test_supervisor_llm.py tests/unit/agent/test_supervisor_graph_runtime.py -q
```

새 패키지의 검증 결과는 루트 `verification.json`에 기록했음. 실제 LangGraph가 설치되지 않은 환경에서는 런타임 테스트 모듈을 명시적으로 skip하며, 가짜 StateGraph로 통과시켰다고 표시하지 않음.

적용 후 기존 팀 저장소의 테스트도 실행해야 함. 새 테스트는 pytest 방식이며 기존 unittest 명령만으로 실행되지 않음. 실제 Neo4j·Chroma·LLM 연결은 팀 환경에서 별도로 확인해야 함.

## 12. 참고

자료에서 확인한 인터페이스 외에 Hybrid의 실제 함수명이나 생성자는 추측하지 않았음. `top_k` 상한 50, 최대 재시도 상한 2, 하위 패키지 경로, `feedback`과 Hybrid 진단 필드는 이번 패키지에서 선택한 운영 기준이므로 팀에서 조정 가능함.

LangGraph 공식 API: https://docs.langchain.com/oss/python/langgraph/graph-api
LangChain 구조화 출력 API: https://reference.langchain.com/python/langchain-openai/langchain_openai/chat_models/base/ChatOpenAI/with_structured_output