# 평가 데이터셋

평가셋은 질문·정답·출처 라벨이며, 평가 실행 결과가 아닙니다. 평가 명령과 저장 위치는 [평가 안내](../README.md)를 참고하세요.

| 폴더 | 내용 | 상태 |
|---|---|---|
| [supervisor_v2/](supervisor_v2/README.md) | Hybrid·Supervisor·GraphRAG 비교 196문항 (v1 150 + 새 흐름 46) | **현재 기본** |
| [neo4j/](neo4j/README.md) | Graph 다중 홉 10문항 | 현재 사용 (흐름 변경과 무관해 유지) |
| [vector_db/](vector_db/README.md) | Chroma 순위 평가 30문항 | 현재 사용 (흐름 변경과 무관해 유지) |
| [guardrails/](guardrails/README.md) | 안전 검사 평가 | 현재 사용 |
| [archive/](archive/README.md) | 기본값에서 내려온 이전 버전 (v1 LangGraph 150·30문항) | 보관 |
