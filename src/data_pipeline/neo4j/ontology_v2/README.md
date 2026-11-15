# 온톨로지 v2 Cypher 생성기

`museum_final_738.csv`를 **읽기만** 해서, 기존 Neo4j 그래프에 노드와 관계를 추가하는 Cypher 스크립트를 만듭니다. 설계 설명은 [온톨로지 v2](../../../../docs/architecture/ontology-v2.md)를 참고하세요.

| 파일 | 역할 |
|---|---|
| `rules.py` | 시설 유형, 기관 정규화, 편의시설 사전, 주제 키워드, 휴관 규칙 파싱 |
| `build_cypher.py` | 규칙 결과를 `UNWIND` Cypher, 검증 쿼리, 롤백 쿼리, 검수용 CSV로 출력 |

## 생성

```powershell
uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.build_cypher
```

기본 출력 위치는 `outputs/neo4j/ontology_v2/`이고, Git에는 올라가지 않습니다. 같은 CSV에서는 항상 같은 결과가 나옵니다.

| 출력 | 내용 |
|---|---|
| `00_constraints.cypher` | 고유 제약과 인덱스 |
| `01_facility_type.cypher` | `Museum.facility_type` |
| `02_organization.cypher` | `Organization`, `OPERATED_BY`, `MANAGED_BY`, `PART_OF_ORG` |
| `03_amenity.cypher` | `Amenity`, `HAS_AMENITY` |
| `04_theme_topic.cypher` | `Theme`, `Topic`, `HAS_TOPIC`, `MENTIONS_TOPIC`, `HAS_THEME` |
| `05_activity_types.cypher` | `Museum.activity_types` |
| `06_opening_rule.cypher` | `Museum.closure_*` |
| `90_verify.cypher` | 적재 후 개수 확인 (`value`와 `expected` 비교), 기존 노드 수 불변 확인, 샘플 조회 |
| `99_rollback.cypher` | v2에서 추가한 것만 삭제 |
| `review/*.csv` | 기관 정규화 결과, 매핑되지 않은 편의시설 토큰, 시설별 주제 근거 (검수용) |
| `summary.json` | 기대 개수와 분포 |

## 적재 (`apply_cypher.py`)

`.env`의 `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`를 사용합니다. `load_neo4j.py`와 같은 설정이에요.

```powershell
# 1) 검수: review/organizations.csv, review/museum_topics.csv를 훑어봅니다.
#    고칠 것이 있으면 rules.py의 사전을 수정하고 build_cypher를 다시 실행합니다.

# 2) 사전 점검: 쓰기 없이 기존 그래프 개수를 확인하고, 모든 문장을 EXPLAIN으로 컴파일합니다.
uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --dry-run

# 3) 적재: 00~06을 순서대로 실행한 뒤 90_verify로 자동 검증합니다.
uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher

# 검증만 다시 실행
uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --verify-only

# 일부 파일만 다시 적용 (예: 사전을 고친 뒤 주제만 다시 넣기)
uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --only 04

# 되돌리기: v2에서 추가한 것만 삭제합니다.
uv run --no-sync python -m src.data_pipeline.neo4j.ontology_v2.apply_cypher --rollback --yes
```

실행기에 들어 있는 안전장치는 다음과 같습니다.

- **CSV 확인:** 스크립트를 만든 뒤 CSV가 바뀌었으면 실행을 멈춥니다. `summary.json`의 sha256과 현재 CSV를 비교해요.
- **기존 그래프 확인:** 실행 전후에 기존 그래프 개수가 `738 / 20 / 199 / 1027 / 3260`인지 확인하고, 다르면 실패로 끝냅니다.
- **실행 단위:** 문장마다 별도의 쓰기 트랜잭션으로 실행합니다. 모든 문장이 `MERGE`/`SET`이라 중간에 실패해도 같은 명령을 다시 실행하면 됩니다.
- **결과 기록:** 실행 결과는 `outputs/neo4j/ontology_v2/apply_result_<mode>.json`에 남습니다.
- **롤백 확인:** 롤백 후에는 v2 노드, v2 관계, 추가했던 Museum 속성이 모두 0개인지 확인합니다.

Cypher 파일을 Neo4j Browser나 `cypher-shell -f`로 직접 실행해도 결과는 같습니다.

`--only`로 일부만 다시 적용할 때는 순서에 주의하세요. `04`는 `01`의 `facility_type`이 있어야 시설 유형에서 `HAS_THEME`을 만들 수 있습니다.
