# 데이터 파이프라인

`neo4j/`는 CSV에서 Neo4j 그래프를 적재·검증하는 코드입니다. `vector_db/`는 Vector 데이터 파이프라인 패키지이며 실제 구축 노트북은 [notebooks/vector_db](../../notebooks/README.md)에 있습니다. 운영 중인 DB에 적재 명령을 실행하기 전 [Neo4j 운영 안내](../../docs/operations/neo4j/README.md)를 확인하세요.


## Vector DB 파이프라인

구축 노트북과 입력 CSV는 [Vector DB 구축 안내](../../notebooks/README.md)에 정리되어 있습니다. 실행 중인 Chroma DB를 덮어쓰지 않도록 별도 경로에서 구축한 뒤 대상 경로를 확인하세요.


## Neo4j 파이프라인

`load_neo4j.py`는 적재 진입점, `graph_db.py`는 DB 접근, `parsing.py`는 입력 파싱, `validate_multihop.py`는 다중 홉 검증을 담당합니다. 실행 및 검증 절차는 [Neo4j 운영 안내](../../docs/operations/neo4j/README.md)를 참고하세요.

온톨로지 v2 확장(기관·편의시설·주제·휴관 규칙)은 CSV를 읽기만 하는 [ontology_v2 생성기](neo4j/ontology_v2/README.md)가 추가 전용 Cypher로 만듭니다.
