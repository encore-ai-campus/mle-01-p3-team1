# 평가 문서 색인

평가를 **실행하고 결과를 해석하는** 안내입니다.

- [Hybrid Ragas](hybrid-ragas.md): 경로별 비교, 실행, 이어하기, 결과.
- [Neo4j GraphRAG Ragas](langgraph-ragas.md): Graph 경로, 평가셋, 결과.
- [Vector DB](vector-db.md): Chroma 검색 순위 평가.
- [가드레일 UI 평가](../../src/guardrails/README.md): 기존 Streamlit UI 경로의 안전 검사 평가.

평가 중에 발견한 문제와 개선 근거는 [검증·작업 기록](../records/README.md)에 있습니다.

- [Neo4j Context Recall 분석](../records/neo4j-context-recall-analysis.md)
- [평가 후 Supervisor·Neo4j 점검](../records/post-eval-supervisor-neo4j.md)

흐름 변경(2026-11-14) 이전 결과는 [평가 기준선](../../evaluations/reports/baseline_2026-11-13/README.md)에 보관했습니다.

평가 데이터는 [evaluations](../../evaluations/README.md), 결과는 `outputs/evaluation/`에 있습니다. 라벨 검수 전 점수는 잠정치이며 실행마다 API 비용과 시간이 듭니다.


## 결과 비교와 보존 기준

v1 150문항과 v2 196문항의 전체 평균을 직접 성능 향상으로 해석하지 않습니다. 공통 문항의 회귀 결과와 신규 46문항 결과를 나눠 확인합니다.

각 실행에는 코드 버전, 평가셋 버전·검수 상태, 모델, 검색 모드, top_k, RRF 가중치, 재정렬·후보 필터 설정, 데이터 스냅샷, 질문별 결과와 시간을 연결합니다. 기록에 없는 조건은 미기록으로 표시합니다.

단위 테스트 통과, 실제 DB 조회 성공, Supervisor 최종 답변 성공, RAGAS 점수 개선은 서로 다른 검증 단계입니다. 라우팅 정확도는 기대 경로 라벨과 실제 route_trace를 비교한 결과가 있을 때만 수치로 주장합니다. N/A 또는 빈 지표는 0점으로 바꾸지 않습니다.

원본 보고서·질문별 CSV·체크포인트·기준선은 보존합니다. 과거 보고서의 점수·조건을 현재 구현에 맞춰 덮어쓰지 않습니다.
