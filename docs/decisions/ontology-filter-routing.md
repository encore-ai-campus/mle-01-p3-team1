# 온톨로지 후보 필터 → Hybrid 검색

Neo4j 온톨로지 v2에 넣는 구조 정보(편의시설, 휴관 규칙 등)를 Graph 경로에서만 쓰지 않고, **Hybrid 검색 앞단에서 후보를 거르는 데** 쓰도록 바꾼 기록입니다. 기준은 2026-11-14의 연결형 Supervisor CLI입니다.

- 흐름도: [박물관 RAG 권장 흐름](https://claude.ai/artifact/VWnWKhqqeVGuVLgkEc6H2R)
- 온톨로지 설계: [ontology-v2.md](../architecture/ontology-v2.md)
- 구현: [`src/hybrid/ontology_filter.py`](../../src/hybrid/ontology_filter.py)

## 한 줄 요약

> 구조 조건은 온톨로지가 후보를 거르고, 의미 판단은 Hybrid가 그 후보 안에서 순위를 정한다.

```
질문 → Supervisor 경로 판단
        ├─ 구조 조건 있음 → 온톨로지 후보 필터 → museum_id 집합 → Hybrid (Vector + BM25 → RRF → Cross-Encoder)
        ├─ 의미 조건만     → Hybrid (기존과 같음)
        └─ 관계·다중홉·출처 → Graph Agent (기존과 같음)
```

## 왜 바꿨나

### 1. v2를 Neo4j에만 넣으면 대부분의 질문에는 영향이 없다
- 기본 경로는 Hybrid이고, Neo4j는 `--with-neo4j`로 연결할 때 일부 질문 유형에서만 쓰입니다([supervisor-integration.md](../architecture/supervisor-integration.md), [region-theme-routing.md](region-theme-routing.md)).
- 그래서 그래프에 기관·편의시설·휴관 정보를 넣어도, Hybrid로 가는 질문은 그 정보를 전혀 쓰지 못합니다.

### 2. 같은 질문이 경로에 따라 다른 답을 낸다
- 예: "경기도에 주차 가능하고 카페 있는 박물관"
- Graph로 가면 `HAS_AMENITY`로 정확히 걸러집니다.
- Hybrid로 가면 Chroma·BM25 메타데이터에 편의시설이 없어서 본문이 비슷한 시설이 섞여 나옵니다.
- 어떤 경로를 타느냐에 따라 조건 충족 여부가 달라지는 것은 사용자 입장에서 설명할 수 없는 동작입니다.

### 3. 두 Agent를 나란히 돌려 결과를 합치는 방식은 기준을 새로 만들어야 한다
- 참고 구조처럼 Vector Agent와 Graph Agent를 병렬로 실행해 근거를 통합하는 방법도 검토했습니다.
- 하지만 Cypher 결과에는 관련도 점수가 없고, Hybrid 결과는 Cross-Encoder 점수를 가집니다. 서로 비교할 수 없는 점수를 합치려면 새 기준이 필요합니다.
- 구조 조건도 Graph 쪽 결과에만 걸려 있어서, Hybrid 쪽 결과는 여전히 조건을 어길 수 있습니다.
- 현재 설계 원칙인 "한 시도에 한 경로, 비교할 수 없는 점수는 합치지 않는다"와도 맞지 않습니다.

### 4. 이미 효과가 확인된 패턴을 일반화한 것이다
- "경기도 권에 있고 자연과 관련된 곳"이라는 질문이 이전에는 Graph로 갔다가 근거 부족으로 보류됐습니다(52.57초).
- 지역 필터를 Vector와 BM25 양쪽에 먼저 걸고 Hybrid로 검색하도록 바꾸자 답변에 성공했습니다([region-theme-routing.md](region-theme-routing.md)).
- 후보 필터는 이 "먼저 거르고, 그 안에서 고르기" 방식을 지역에서 편의시설과 개관 요일로 넓힌 것입니다.

### 5. 연결 지점이 이미 코드에 있었다
- [`vector_search_chroma.py`](../../src/service/vector_search_chroma.py)에는 처음부터 `candidate_ids` 인자가 있었습니다. 주석에 "GraphDB에서 넘어온 ID 목록"이라고 적혀 있지만 어디서도 쓰이지 않았어요.
- 이번 변경으로 이 인자가 실제로 쓰이고, BM25에도 같은 인자를 추가했습니다.

## 무엇을 필터로 쓰고, 무엇을 쓰지 않나

**필터(후보를 빼는 조건)는 기록된 사실로 판정할 수 있는 것만** 씁니다. 묘사하는 말은 Hybrid의 의미 검색에 맡깁니다.

| 조건 | 처리 | 이유 |
|---|---|---|
| 편의시설 ("수유실 있는", "주차 가능한") | **필터** | `amenities_raw` 기록에서 판정할 수 있습니다. 결과에 원문 토큰을 근거로 붙입니다. |
| 개관 요일 ("월요일에도 여는", "주말에 여는") | **필터** | `closure_rule_raw`를 파싱한 휴관 요일로 판정합니다. 파싱하지 못한 시설은 통과시키지 않습니다. |
| 지역 | 위 조건이 있을 때만 함께 적용 | 단독 지역 질문은 기존 지역 필터 경로가 그대로 처리합니다. |
| 주제 ("자연 관련", "도자기") | 필터 아님, 의미 검색 | 주제 라벨은 키워드로 붙인 추정치(UNVERIFIED)이고, 738곳 중 446곳에만 있습니다. 필터로 쓰면 맞는 시설까지 빠집니다. |
| 시설 유형 ("미술관", "전시관") | 필터 아님, 의미 검색 | 사용자가 느슨하게 씁니다. 평가셋에서 `홍주성역사관`을 "전시관"으로 묻는 질문이 실제로 있습니다. |
| 수량·실시간 ("주차면 몇 면", "오늘 휴관") | 필터 아님 | 기록에 없는 정보입니다. 필터를 적용하지 않고 기존 검증 단계에서 보류합니다. |

## 더 좋아지는 점

| 항목 | 이전 | 지금 | 확인 |
|---|---|---|---|
| 조건 보장 | 구조 조건이 Hybrid 결과에 보장되지 않음 | 최종 근거가 모두 조건을 만족함 | 단위 테스트, 실제 검색: 경기도 + 주차장 + 카페 → 후보 3곳 안에서만 순위 |
| 근거 표시 | 편의시설·휴관을 본문에서 추정 | `metadata.structured_match`에 "편의시설 기록 '카페' (원문: 카페테리아)"처럼 붙음 | Answer/Verifier LLM이 metadata를 그대로 받음 |
| 없을 때의 답 | 조건과 무관한 비슷한 시설로 채워짐 | 조건을 빼지 않고 `no_results`와 경고를 반환 → 검증 단계에서 보류 | 실제 검색: 서울 + 휠체어 대여 + 주말 개관 → 0곳, 23ms 만에 종료 |
| 추가 비용 | — | 규칙 기반이라 LLM 호출이 없고 로컬 조회만 함 | Graph 경로의 Cypher 생성은 이전 사례에서 16.88초가 걸렸음 |
| Neo4j 의존 | 구조 정보는 `--with-neo4j`일 때만 쓰임 | 연결 여부와 관계없이 같은 후보 | 로컬 조회표와 Neo4j v2가 같은 `rules.py`에서 나옴 |
| 적용 범위 | — | `HybridSearchService` 한 곳에 넣어 Supervisor, Hybrid 평가, CLI가 모두 사용 | `build_hybrid_service`가 기본으로 연결 |
| 기존 평가 영향 | — | 기존 40문항(LangGraph 30, Neo4j 10) 중 필터가 걸리는 질문 0개 | 테스트로 고정 (`test_existing_evaluation_questions_are_untouched`) |
| 되돌리기 | — | `HYBRID_ONTOLOGY_FILTER=off`로 이전 동작과 같아짐 | 테스트 포함 |

## 바뀐 파일

| 파일 | 변경 |
|---|---|
| `src/hybrid/ontology_filter.py` (신규) | 조건 추출, `LocalOntologyIndex`(CSV), `Neo4jOntologyIndex`(v2 그래프), `OntologyCandidateFilter` |
| `src/hybrid/service.py` | 0단계 `ontology_filter` 추가. 후보 ID를 Vector·BM25에 전달하고, 받을 수 없는 검색기는 결과를 후처리로 거름. `structured_match` 첨부, `search_summary.ontology_filter` 기록 |
| `src/hybrid/bm25_retriever.py` | `search(..., candidate_ids=None)` |
| `src/hybrid/adapters.py` | Chroma 검색에 `candidate_ids` 전달 (값이 있을 때만) |
| `src/hybrid/factory.py` | 기본 필터 연결 (`candidate_filter="default"`) |
| `src/agent/supervisor/nodes.py` | 구조 조건이 있는 질문은 LLM 라우터 대신 Hybrid로 보냄 |
| `src/data_pipeline/neo4j/ontology_v2/rules.py` | 공용 규칙 (편의시설 매핑에서 "라운지" 제외) |
| `src/hybrid/cli.py`, `src/agent/supervisor/run.py` | `--no-ontology-filter` 옵션: 필터 없이 이전 방식으로 검색해 비교 |

실제 질문으로 점검하며 고친 근거 전달 문제(편의시설 근거 인정, 기록이 없을 때 재시도 없이 보류)는 [문제 해결 기록](../records/supervisor-retrieval-issues.md#온톨로지-v2-연결-후-근거-전달-점검-2026-11-14)에 있습니다.

## 한계와 다음 단계

- **편의시설 기록이 있는 시설은 292곳뿐입니다.** 필터 결과는 "기록된 시설 기준"이고, 답변에서도 그렇게 표현해야 합니다.
- **조건 어휘가 제한적입니다.** 편의시설 14개 표현과 개관 요일만 인식합니다. 운영기관("○○시가 운영하는")과 무료·국립 같은 조건은 아직 넣지 않았습니다.
- **기본값은 로컬 조회표로 유지합니다.**
  - v2 적재(2026-11-14) 후 `python -m src.hybrid.ontology_filter --check-neo4j`로 두 백엔드를 비교했습니다. 편의시설 24종, 요일 7개, 지역 8곳 조합으로 만든 55개 조건 모두에서 후보가 같았습니다.
  - 결과가 같으므로, 네트워크 왕복이 없는 로컬 조회표를 기본으로 씁니다.
  - 그래프 데이터를 손으로 고치기 시작하면 Neo4j 백엔드로 바꾸고 이 점검을 다시 돌립니다.
- **Streamlit UI는 아직 별도 경로입니다.** UI도 같은 Supervisor나 HybridSearchService를 호출하도록 맞춰야 이 필터가 적용됩니다.
- **주제 어휘가 아직 두 벌입니다.** [`region_theme.py`](../../src/hybrid/region_theme.py)의 주제 단어(8개)와 v2 Theme·Topic은 아직 별도입니다. 지금은 주제를 필터로 쓰지 않아서 결과에 영향은 없지만 한쪽으로 합쳐야 합니다.
- **조건 완화는 자동으로 하지 않습니다.** 후보가 0개일 때 조건을 슬쩍 빼면 질문과 다른 답이 나오므로 의도적으로 넣지 않았습니다. 대안을 제시하려면 "조건 없이 찾은 결과"임을 명시하는 별도 응답 형식이 필요합니다.
- **새 평가셋과 비교 검증을 구분합니다.** v2 196문항(기존 150 + 신규 46)이 생성됐습니다. 후보 필터의 효과는 동일 문항·모델·검색 설정에서 off/on을 비교해야 하며, 평가셋 생성만으로 성능 개선을 확정하지 않습니다.
- 별개로, 이 변경과 무관하게 원래 실패하던 테스트가 1건 있습니다: `tests/unit/agent/test_hybrid_integration.py::test_default_vector_adapter_uses_current_service_module`. 테스트의 가짜 서비스에 `is_query_analysis_enabled`가 없어서 실패합니다.
