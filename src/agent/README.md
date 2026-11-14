# Agent와 그래프 검색

`supervisor/`는 실제 터미널 챗봇의 라우팅·검색·답변·검증을 조정합니다. `neo4j_text2cypher.py`, `neo4j_search.py`, `neo4j_tls.py`는 Neo4j 읽기 검색과 연결을 담당합니다. `graph.py`, `state.py`, `neo4j_demo.py`는 기존 GraphRAG 경로입니다.

`neo4j_text2cypher.py`의 단순한 시·구 주변 추천 전용 조회는 등록 좌표의 직선거리 5km 이내에서 출처가 연결된 두 장소를 찾습니다. 첫 장소는 해당 지역의 이름순으로 선택하고, 두 번째는 그 장소에서 가까운 순으로 선택합니다. 장소별 출처와 좌표를 반환하며 도보 거리는 계산하지 않습니다. 요금·시설 유형·명시적인 거리 등 추가 조건이 있는 질문은 이 전용 조회로 처리하지 않고 일반 Text-to-Cypher 경로를 사용합니다. 같은 좌표는 데이터에 기록된 위치가 같다는 의미이며 실제 건물 위치를 독립 검증한 것은 아닙니다.

`bm25_reranker.py`, `ragas_eval.py`, `ragas_testset.py`는 기존 import와 명령을 유지하기 위한 호환 진입점입니다. 기준 구현은 각각 `src/hybrid/`와 `src/evaluation/langgraph/`에 있으므로 중복 구현으로 합치거나 삭제하지 않습니다.

실행은 [Supervisor 안내](supervisor/README.md), 전체 구조는 [폴더 구조](../../docs/architecture/folder-structure.md)를 참고하세요.
