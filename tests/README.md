# 테스트

`unit/`은 검색·라우팅·평가 처리 단위 테스트, `integration/`은 DB 연동 테스트를 모읍니다. `test_guardrails.py`와 `test_bm25_reranker.py`는 팀 구현 테스트입니다. 외부 DB 또는 실제 API가 필요한 테스트는 실행 전 설정을 확인하세요.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/agent/test_supervisor_guardrails.py tests/unit/agent/test_supervisor_graph_runtime.py -q
```

가드레일의 실제 UI 평가와 위 자동 테스트는 서로 다릅니다. [평가 안내](../evaluations/README.md)를 참고하세요.


## 서비스 테스트 공간

Vector 검색 서비스와 UI 서비스 관련 단위 테스트를 둘 위치입니다.


## 단위 테스트

`agent/`는 Supervisor·Graph·Neo4j, `data_pipeline/`은 적재와 파싱, `evaluation/`은 평가 처리, `service/`는 서비스 관련 테스트를 모읍니다. 실행 예시는 [테스트 안내](README.md)에 있습니다.


## Vector 평가 테스트 공간

Vector DB 평가 관련 단위 테스트를 둘 위치입니다. 실제 평가 절차는 [Vector 평가 문서](../docs/evaluation/vector-db.md)를 참고하세요.


## 평가 코드 단위 테스트

`langgraph/`는 GraphRAG 평가 처리, `test_timing.py`는 문항별 시간, `test_hybrid_partial_status.py`는 Hybrid 평가 상태 처리를 검증합니다. `vector_db/`는 Vector 평가 테스트 공간입니다.


## LangGraph 평가 테스트

평가셋 읽기·생성과 GraphRAG 결과 및 Ragas 보고서 조립을 테스트합니다.


## Agent 단위 테스트

Supervisor, 검색 어댑터, Neo4j 질의·연결 처리와 가드레일 연결을 검증합니다. 실제 외부 서비스 대신 테스트용 객체를 사용하는 경우가 많습니다.


## 데이터 파이프라인 단위 테스트

`neo4j/`는 CSV 파싱과 그래프 적재·검증 로직의 테스트입니다.


## 통합 테스트

`neo4j/`와 `vector_db/`는 각 저장소의 통합 테스트를 위한 폴더입니다. 외부 DB 또는 실제 API가 필요한 경우 실행 전에 연결 정보와 데이터 상태를 확인하세요.


## Neo4j 통합 테스트 공간

실제 Neo4j 연결 검증을 둘 위치입니다. 외부 DB에 접근하는 테스트는 실행 전 대상과 권한을 확인하세요.


## Neo4j 파이프라인 테스트

CSV 파싱, 적재 요청과 다중 홉 검증을 테스트합니다. 실제 Aura 연결 검증과 구별하세요.


## Vector DB 통합 테스트 공간

Chroma 컬렉션과 연결되는 통합 테스트를 둘 위치입니다. 실행 중인 DB와 평가를 보호할 수 있는 별도 데이터로 검증하세요.
