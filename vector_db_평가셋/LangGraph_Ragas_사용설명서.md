# LangGraph Ragas 평가

Neo4j의 실제 박물관 근거를 LangGraph `graph` 경로로 검색하고 Ragas로 채점합니다. 기존 VectorDB 30문항을 시드로 만든 별도 평가셋이며, 현재 모든 라벨은 `draft_needs_human_review` 상태입니다. 질문, 정답, 근거 문장을 먼저 사람이 확인하면 비교 가능한 점수가 됩니다.

## 평가셋 준비

300문항 평가셋은 기존 VectorDB 평가셋의 30문항을 포함하고, 박물관 원문에서 Ragas가 질문·기준 답변·근거를 합성해 채웁니다. 재생성이 필요하면 저장소 루트에서 실행합니다.

```powershell
uv run python -m src.agent.ragas_testset --count 300
```

합성에는 OpenAI API 비용이 발생할 수 있습니다. 기본 경로에 파일이 이미 있으면 덮어쓰지 않습니다. 의도적으로 다시 만들 때만 `--force`를 추가하세요. 새 문항은 모두 `draft_needs_human_review` 상태이므로 질문, 정답, 근거, 박물관 ID를 검수해야 합니다.

## 평가 실행

저장소 루트에서 PowerShell로 실행합니다. `.bat` 파일은 필요하지 않습니다.

```powershell
uv run python -m src.agent.ragas_eval --check-only
uv run python -m src.agent.ragas_eval
```

첫 명령은 평가셋 형식, Ragas 설치, `.env`의 Neo4j 설정, Aura 접속을 점검하며 OpenAI API는 호출하지 않습니다. 두 번째 명령은 GraphRAG의 Cypher 생성·답변 작성과 Ragas 채점을 모두 실행합니다.

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

파일: `LangGraph_Ragas_평가셋_300문항.csv`

현재 300문항은 답변 가능 294개, 근거 부족 6개입니다. 따라서 Ragas 네 지표는 답변 가능 294개에서 계산하고, evidence presence는 전체 300개에서 계산합니다. 근거 부족 문항은 6개뿐이라 답변 거부 성능 평가는 참고 수준입니다.

합성된 문항의 정답·근거 라벨을 확인한 뒤 각 `label_status`를 `human_verified`로 바꾸세요. 현재 300개 모두 `draft_needs_human_review`이며, 검수 전에도 실행은 가능하지만 출력 점수는 잠정 결과로 표시됩니다.

## 결과

각 실행은 `outputs/langgraph_ragas_eval/run_<시각>/` 아래에 저장됩니다.

- `report.md`: 평균 점수와 라벨 상태
- `summary.json`: 설정 및 전체 요약
- `per_question.csv`: 질문별 답변, 검색된 박물관·구간 ID, Ragas 점수

검색은 Neo4j 읽기 전용이며 DB를 수정하지 않습니다.
