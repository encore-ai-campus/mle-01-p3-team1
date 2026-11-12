# mle-01-p3-team1

## LangGraph 오케스트레이션

`src/agent/graph.py`는 질문 라우팅, Vector/Graph/Hybrid 검색 호출, 답변 생성, 답변 검증, 실패 시 Hybrid 재검색과 근거 부족 응답을 연결합니다. 라이브 Neo4j 데모는 `Neo4jText2Cypher`를 연결해 자연어 질문에서 Cypher를 만들고, Neo4j 근거를 읽은 뒤 OpenAI로 답변을 생성합니다.

- 검색 함수: `(question: str, k: int) -> list[Evidence]`
- 라우터: `(question: str) -> "vector" | "graph" | "hybrid"`
- 답변 생성기: `(question: str, evidence: list[Evidence]) -> str`
- 검증기: `(question: str, answer: str, evidence: list[Evidence]) -> bool`

하이브리드 결과는 같은 근거를 한 건으로 합치고 검색 출처를 보존합니다. 첫 검증에 실패하면 기본 1회 재검색한 뒤, 검증되지 않으면 근거 부족 응답으로 끝냅니다. 실제 사실과 인용 검증은 주입하는 `verify_answer`가 담당하며, 데모 함수는 이를 대체하지 않습니다.

```powershell
uv run python -m src.agent.demo_graph
uv run python -m unittest discover -s tests -v
```

테스트는 가짜 검색·LLM 함수를 사용해 오케스트레이션만 확인하며 실제 Neo4j·ChromaDB 연결은 시험하지 않습니다. Neo4j 적재 절차는 [`src/for_build/build_neo4j/README.md`](src/for_build/build_neo4j/README.md)를 참고하세요.

### 실제 Neo4j 데이터로 읽기 시험

루트 `.env`에 `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `OPENAI_API_KEY`를 설정한 뒤 실행합니다. `OPENAI_CHAT_MODEL`은 선택이며 기본 모델은 `gpt-4o-mini`입니다.

```powershell
uv run python -m src.agent.neo4j_demo --question "서울 전통문화" --top-k 5
```

이 명령은 OpenAI가 질문에 맞는 Cypher를 생성하고, `Museum → TextSpan → SourceDocument` 그래프에서 근거를 읽은 뒤 OpenAI가 한국어 답변을 작성하는 GraphRAG 경로입니다. 생성된 Cypher는 결과 JSON의 `generated_cypher`에 표시됩니다. Cypher는 읽기 전용 검사와 `RoutingControl.READ`를 거칩니다. 질문과 조회 근거가 답변 생성 모델에 전달되며, OpenAI API 사용료가 발생할 수 있습니다. `verified`는 답변에 근거 박물관 ID가 포함됐는지만 검사하며 사실 검증은 아닙니다.

### LangGraph Ragas 평가

실제 Aura GraphRAG 경로를 Ragas로 평가하려면 [`LangGraph_Ragas_사용설명서.md`](vector_db_평가셋/LangGraph_Ragas_사용설명서.md)를 참고하세요. 루트에서 평가셋 재생성은 `uv run python -m src.agent.ragas_testset --count 300`, 설정 점검은 `uv run python -m src.agent.ragas_eval --check-only`, 전체 평가는 `uv run python -m src.agent.ragas_eval`로 실행합니다. 전체 평가는 GraphRAG 생성과 Ragas 채점 모두 OpenAI API를 사용하므로 사용료가 발생할 수 있습니다.
