# 데이터 파이프라인

이 폴더 기준 경로입니다. 운영 DB 적재 전 [Neo4j 운영 안내](../../docs/operations/neo4j/README.md)를 확인하세요.

| 경로 | 역할 |
|---|---|
| `neo4j/load_neo4j.py` | CSV → Neo4j 적재 진입점 |
| `neo4j/graph_db.py` | DB 접근 |
| `neo4j/parsing.py` | 입력 파싱 |
| `neo4j/validate_multihop.py` | 다중 홉 검증 |
| [neo4j/ontology_v2](neo4j/ontology_v2/README.md) | 기관·편의시설·주제·휴관 규칙 확장용 Cypher 생성·적용 |
| `vector_db/` | 패키지 위치. 실제 구축은 노트북에서 수행 |

Vector 구축 절차와 입력 CSV는 [노트북 안내](../../notebooks/README.md)에 있습니다. 실행 중인 Chroma를 덮어쓰지 않도록 별도 경로에 구축한 뒤 대상을 확인하세요.

온톨로지 v2 생성기는 CSV를 읽어 추가 전용 Cypher를 만듭니다. 생성과 DB 적용은 별도 단계입니다. [데이터 안내](../../data/README.md)에 따라 Supervisor·Neo4j용 738 CSV와 별도 Streamlit용 1027 CSV를 구분합니다.
