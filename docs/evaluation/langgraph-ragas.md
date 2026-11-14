# LangGraph Ragas 평가

Neo4j의 실제 박물관 근거를 LangGraph `graph` 경로로 검색하고 Ragas로 채점합니다. 기본 평가셋은 [v2 196문항](../../evaluations/datasets/supervisor_v2/README.md)이고, 모든 라벨이 사람 검수 전이라 점수는 잠정치입니다. Graph 다중 홉 전용 평가는 `evaluations/datasets/neo4j/`의 10문항을 `--evalset`으로 지정합니다.

**어떤 평가가 무엇을 재는가**

| 명령 | 경로 | 재는 것 |
|---|---|---|
| `src.evaluation.langgraph.ragas_eval` (이 문서) | Graph 경로 단독 (Text2Cypher) | Neo4j 검색과 그 답변 |
| `src.evaluation.hybrid.ragas_eval --modes hybrid_rerank` | Hybrid 고정 | 검색·재정렬 품질 |
| `src.evaluation.hybrid.ragas_eval --modes supervisor_full` | 실제 Supervisor 전체 흐름 | 자동 라우팅, 후보 필터, Graph, 기록 없음 보류까지 포함 |

세 평가는 서로 다른 것을 재므로 점수를 같은 선상에서 비교하지 마세요. 실제 서비스 흐름의 평가는 [Hybrid 통합 평가](hybrid-ragas.md)의 `supervisor_full`입니다.

## 평가셋 준비

기본 평가는 `evaluations/datasets/supervisor_v2/Supervisor_Ragas_v2_draft.csv`(196문항, 답변 가능 182 · 보류 기대 14)를 사용합니다. 이 파일은 `uv run python -m src.evaluation.build_evalset_v2`로 결정적으로 다시 만들 수 있습니다. 이전 기본값(v1 150문항)은 `evaluations/datasets/archive/v1_2026-11-13/`에 보관했습니다.

LLM으로 새 문항 초안을 합성하려면(시드는 보관된 v1 30문항):

```powershell
uv run python -m src.evaluation.langgraph.ragas_testset --count 150 --output "evaluations/datasets/generated/LangGraph_Ragas_150_generated.csv"
```

합성에는 OpenAI API 비용이 발생할 수 있습니다. 기본 경로에 파일이 이미 있으면 덮어쓰지 않습니다. 의도적으로 다시 만들 때만 `--force`를 추가하세요. 새 문항은 모두 `draft_needs_human_review` 상태이므로 질문, 정답, 근거, 박물관 ID를 검수해야 합니다.

## 평가 실행

저장소 루트에서 PowerShell로 실행합니다. `.bat` 파일은 필요하지 않습니다.

```powershell
uv run python -m src.evaluation.langgraph.ragas_eval --check-only
uv run python -m src.evaluation.langgraph.ragas_eval
uv run python -m src.evaluation.langgraph.ragas_eval --evalset "evaluations/datasets/neo4j/Neo4j_multihop_core10_draft.csv" --top-k 5 --batch-size 8
```

첫 명령은 평가셋 형식, Ragas 설치, `.env`의 Neo4j 설정, Aura 접속을 점검하며 OpenAI API는 호출하지 않습니다. 두 번째 명령은 GraphRAG의 Cypher 생성·답변 작성과 Ragas 채점을 모두 실행합니다.

`--batch-size`는 GraphRAG에서 동시에 처리할 질문 수이며 기본값은 `8`입니다. 실행 중 `[GraphRAG] 완료/전체`와 `question_id`가 질문마다 표시되고, Ragas 채점 단계에는 진행 막대가 표시됩니다. OpenAI rate limit이 발생하면 `--batch-size 4` 또는 `--batch-size 2`로 낮춰 실행하세요. `--batch-size 1`은 순차 처리입니다.

## 설정

루트 `.env`에 다음 값이 필요합니다.

- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
- `OPENAI_API_KEY`
- 선택: `OPENAI_CHAT_MODEL` (GraphRAG 생성 모델, 기본값 `gpt-4o-mini`)
- 선택: `RAGAS_JUDGE_MODEL` (Ragas 채점 모델, 기본값 `gpt-4o-mini`)

GraphRAG 질문당 Cypher 생성과 답변 작성, Ragas 채점이 OpenAI API를 호출하므로 실행할 때 사용료가 발생할 수 있습니다. `--judge-model`로 Ragas 채점 모델을 지정할 수 있습니다.

## 평가 내용

- `faithfulness`: 답변 내용이 검색 문맥에 근거하는지
- `context_recall`: 정답에 필요한 내용을 검색 문맥이 포함하는지
- `context_precision_with_reference`: 정답 기준으로 검색 문맥의 순위와 관련성을 평가
- `factual_correctness`: 답변과 기준 정답의 사실 일치도
- `evidence_presence_accuracy`: 답변 가능 라벨과 검색 결과 유무를 전체 문항에서 비교하는 보조 지표

Ragas 점수는 답변 가능 문항에 대해서만 계산하고, 근거 부족 문항은 `evidence_presence_accuracy`로 별도 확인합니다. GraphRAG는 질문에 맞는 Cypher를 생성해 Neo4j를 읽고, 반환된 근거를 바탕으로 답변을 생성하므로 평가에는 검색과 답변 생성이 모두 반영됩니다.

## 평가셋 검수

파일: `Supervisor_Ragas_v2_draft.csv`

- 답변 가능 182개, 보류 기대 14개입니다. Ragas 네 지표는 답변 가능 문항에서, evidence presence는 전체에서 계산합니다.
- v1 문항은 `draft_needs_human_review`, v2 새 문항은 `auto_generated_needs_human_review`입니다. 정답·근거를 확인한 뒤 `label_status`를 `human_verified`로 바꾸세요.
- 검수 전에도 실행은 되지만 점수는 잠정 결과로 표시됩니다.
- v2를 생성기로 다시 만들면 검수 표시가 초기화되니, 검수한 뒤에는 파일을 직접 고치고 생성기는 다시 돌리지 마세요.

## 결과

각 실행은 평가셋 경로에 따라 저장됩니다. `evaluations/datasets/neo4j/` 안의 평가셋은 `outputs/evaluation/neo4j_multihop_ragas/run_<시각>/`, 그 외 평가셋은 `outputs/evaluation/langgraph_ragas/run_<시각>/`에 저장됩니다. `--output`을 지정하면 이 기본 위치를 덮어씁니다.

- `report.md`: 평균 점수와 라벨 상태
- `summary.json`: 설정 및 전체 요약
- `per_question.csv`: 질문별 답변, 검색된 박물관·구간 ID, Ragas 점수와 검색·답변 시간(초)

`summary.json`과 `report.md`에는 검색·답변의 평균·최대 시간과 Ragas 전체 채점 시간이 저장됩니다. 질문별 검색·답변 시간에는 Ragas 채점이 포함되지 않습니다.

검색은 Neo4j 읽기 전용이며 DB를 수정하지 않습니다.
