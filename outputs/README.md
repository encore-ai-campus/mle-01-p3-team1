# 로컬 실행 결과

`evaluation/hybrid_ragas/`, `evaluation/langgraph_ragas/`, `evaluation/neo4j_multihop_ragas/`, `evaluation/vector_db/`, `evaluation/guardrails/`는 각각 실행 결과를 보관합니다. `neo4j/`에는 Neo4j 실행 자료가 있습니다. 실행 폴더의 `per_question.csv`, 요약 파일, 체크포인트를 함께 보존하세요.

평가 진행 중인 폴더는 이동·삭제하지 않습니다. 평가 요약·문항별 결과·체크포인트·검색 결과 JSON은 Git으로 공유합니다. 로컬 채점 캐시(`judge_cache/`)와 로그는 제외합니다. `INVALID`·`STOPPED` 실행 폴더는 실패·중단 기록이며 완료된 평가와 구분하세요. 명령과 파일별 의미는 [평가 안내](../evaluations/README.md)를 참고하세요.
