# 테스트

자동 테스트는 코드 동작을 확인합니다. 실제 검색·LLM 품질은 [평가 안내](../evaluations/README.md)에 따라 별도로 측정합니다. 경로는 이 폴더 기준입니다.

| 경로 | 확인 대상 | 외부 서비스 구분 |
|---|---|---|
| `unit/agent/` | Supervisor 라우팅·근거·가드레일·시간, Hybrid·combined, Neo4j 처리 | 주로 가짜 검색기·클라이언트 주입 |
| `unit/evaluation/` | 평가셋·시간·부분 실패·출력 경로 | 실제 RAGAS 평가와 구분 |
| `unit/evaluation/langgraph/` | GraphRAG 평가 처리 | 단위 검증 |
| `unit/data_pipeline/neo4j/` | 파싱·적재·다중 홉·온톨로지 생성 | 운영 DB 적재와 구분 |
| `test_guardrails.py` | 차단·오류·메시지 흐름 | 실제 LLM 대신 가짜 Rails |
| `test_bm25_reranker.py` | 독립 BM25/RRF 모듈 순위 | 외부 API 불필요 |
| `integration/neo4j/`, `integration/vector_db/` | 통합 테스트 예정 위치 | 현재 패키지만 존재 |
| `unit/service/`, `unit/evaluation/vector_db/` | 단위 테스트 예정 위치 | 현재 패키지만 존재 |

저장소 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/agent/test_supervisor_guardrails.py tests/unit/agent/test_supervisor_graph_runtime.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/agent/test_combined_route.py tests/unit/agent/test_ontology_filter.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/evaluation tests/unit/data_pipeline/neo4j -q
```

단위 테스트 통과가 라우팅 정확도나 RAGAS 개선을 증명하지는 않습니다. 실제 가드레일 평가와 API·DB 연결 검증은 별도로 수행합니다. 터미널 Supervisor와 Streamlit의 평가 결과도 구분합니다.
