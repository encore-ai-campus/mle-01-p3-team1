# Supervisor Ragas 평가셋 v2 (2026-11-14)

`Supervisor_Ragas_v2_draft.csv`는 현재 기본 평가셋입니다. Hybrid 비교(`src.evaluation.hybrid.ragas_eval`)와 Neo4j GraphRAG 평가(`src.evaluation.langgraph.ragas_eval`)가 모두 이 파일을 기본으로 읽습니다.

## 왜 다시 만들었나

2026-11-14에 검색 흐름이 바뀌었습니다.
- 온톨로지 후보 필터 → Hybrid
- 기관 질문 → Graph 고정 쿼리
- 조건을 만족하는 기록이 없으면 재시도 없이 보류

v1(150문항)에는 이 흐름을 시험하는 문항이 없었습니다. 그래서 v1을 그대로 가져오고, 새 흐름을 확인하는 문항을 더했습니다. v1 원본은 [archive/v1_2026-11-13](../archive/v1_2026-11-13/README.md)에 보관합니다.

## 구성 (196문항)

| 출처 | 분류 | 문항 | 확인하는 흐름 | 기대 동작 |
|---|---|---:|---|---|
| v1 | direct, semantic, geo_semantic, single_hop… | 144 | 기존 의미·사실 검색 (회귀 확인) | 답변 |
| v1 | unanswerable | 6 | 근거 없는 질문 | 보류 |
| v2 | `structured_filter` | 12 | 지역 + 편의시설 → 후보 필터 → Hybrid | 답변 |
| v2 | `structured_weekday` | 6 | 지역 + 편의시설 + 개관 요일 | 답변 |
| v2 | `structured_no_record` | 5 | 조건을 만족하는 기록 0곳 | 이유를 안내하며 보류 |
| v2 | `org_same_operator` | 10 | "○○과 같은 기관이 운영하는 다른 시설" → Graph | 답변 |
| v2 | `org_same_manager` | 4 | 같은 질문, 관리기관(UNVERIFIED) | 답변 |
| v2 | `closure_fact` | 6 | 특정 시설의 정기 휴관 요일 | 답변 |
| v2 | `unanswerable_count_live` | 3 | 편의시설 개수, 오늘 운영 여부 | 보류 |

추가된 열은 다음과 같습니다.
- `expected_route`: `hybrid_ontology_filter`, `graph`, `any`
- `expected_behavior`: `answer`, `abstain`, `abstain_no_record`
- `source_set`: `v1_2026-11-13` 또는 `v2_2026-11-14`

## 만드는 방법

```powershell
.\.venv\Scripts\python.exe -m src.evaluation.build_evalset_v2
```

- **결정적 생성:** 새 문항의 정답은 LLM이 아니라 CSV와 온톨로지 v2 규칙(`rules.py`, 후보 필터)으로 계산합니다. 같은 CSV에서는 항상 같은 파일이 나옵니다.
- **경로 검증:** 생성할 때 각 질문이 의도한 코드 경로를 실제로 타는지 확인합니다. 조건 추출기가 같은 조건을 뽑는지, 기관 고정 쿼리가 선택되는지를 보고, 맞지 않으면 그 문항을 넣지 않습니다.
- **지역 분산:** 한 지역에 몰리지 않도록 분류마다 지역당 1문항으로 제한했습니다.
- **라벨 상태:** 새 문항의 `label_status`는 `auto_generated_needs_human_review`입니다. 규칙으로 정확히 계산했지만, 질문 표현과 정답 문장은 사람이 확인한 뒤 점수를 확정하세요.

## 평가 실행

```powershell
# 실제 Supervisor 흐름 전체 (자동 라우팅 + 후보 필터 + Neo4j). Neo4j 설정 필요
.\.venv\Scripts\python.exe -m src.evaluation.hybrid.ragas_eval --modes supervisor_full --top-k 5

# 이전 기준선과 같은 조건(Hybrid Cross-Encoder)으로 회귀 확인
.\.venv\Scripts\python.exe -m src.evaluation.hybrid.ragas_eval --modes hybrid_rerank --top-k 5
```

`supervisor` 모드는 경로를 Hybrid로 고정한 비교용입니다. 바뀐 라우팅까지 평가하려면 `supervisor_full`을 쓰세요.
