# Hybrid RAG 통합 평가

`src.evaluation.hybrid.ragas_eval`은 Chroma/Hybrid, Supervisor, Neo4j GraphRAG를 같은 평가셋으로 비교합니다.

- **기본 평가셋:** [v2 196문항](../../evaluations/datasets/supervisor_v2/README.md) (`Supervisor_Ragas_v2_draft.csv`). 2026-11-13 이전의 v1 150문항은 그대로 포함되어 있고, 원본은 [보관 폴더](../../evaluations/datasets/archive/README.md)에 있습니다.
- **후보 공유:** Chroma/BM25 후보는 질문마다 한 번만 준비하고, Vector·Hybrid RRF·Cross-Encoder·Supervisor 평가가 재사용합니다. 이 후보에는 온톨로지 후보 필터가 적용됩니다.
- **질의 분석:** Vector 질의 분석은 기본적으로 꺼져 있고, `MUSEUM_QUERY_ANALYSIS_ENABLED=true`일 때만 실행합니다.
- **병렬도:** 기본 질문 8개, Ragas 판정 16개입니다. API rate limit이 나면 `--workers 4 --ragas-workers 8`로 낮추세요.
- **체크포인트:** 문항 결과는 개별 체크포인트로 저장합니다.

## 비교 경로

| 모드 | 실제 실행 경로 |
|---|---|
| `bm25` | Chroma 문서로 만든 BM25 검색 |
| `vector` | 기존 VectorSearchService와 Chroma 검색. LLM 질의 분석은 선택 설정 |
| `hybrid_rrf` | BM25 + Vector + weighted RRF |
| `hybrid_rerank` | BM25 + Vector + weighted RRF + Cross-Encoder |
| `supervisor` | Supervisor 답변·근거 검증. **경로를 Hybrid로 고정**한 비교용 |
| `supervisor_full` | **실제 CLI 흐름 전체**: 자동 라우팅, 후보 필터·지역 필터 고정 경로, 기관 질문 Graph, 기록 없음 보류. Neo4j 필요 |
| `graph` | 기존 Neo4j Text2Cypher GraphRAG 단독 |

**모드마다 기록하는 값**
- 검색 순위(Hit@1/3/5, Recall@5, MRR@10), 답변 Ragas 점수, 근거 미검색·오검색, 오류 수
- Supervisor 계열은 검증 통과율도 기록합니다.
- 검색 단위가 다릅니다. BM25와 Vector는 Chroma 문서 단위, Neo4j는 그래프 증거 단위이므로 결과를 해석할 때 반영하세요.

## 실행

```powershell
# 설정만 확인 (API 호출 없음)
uv run python -m src.evaluation.hybrid.ragas_eval --modes supervisor_full,hybrid_rerank --check-only

# 실제 흐름 전체
uv run python -m src.evaluation.hybrid.ragas_eval --modes supervisor_full --top-k 5

# 이전 기준선과 같은 조건 (Hybrid Cross-Encoder, top-k 5)
uv run python -m src.evaluation.hybrid.ragas_eval --modes hybrid_rerank --top-k 5

# 30문항 스모크 평가 (보관된 v1 30문항)
uv run python -m src.evaluation.hybrid.ragas_eval --evalset "evaluations/datasets/archive/v1_2026-11-13/langgraph/LangGraph_Ragas_평가셋_30문항.csv" --top-k 10
```

- 기본값은 7개 경로 전체, 평가셋 전체 문항(`--limit 0`)입니다.
- `--modes hybrid_rrf,hybrid_rerank,supervisor`처럼 경로를 골라 실행할 수 있습니다.
- 후보 재사용으로 검색 중복은 줄였지만, 경로마다 답변 생성과 Ragas 판정은 별도 API 호출이라 비용과 시간이 듭니다.

## 환경 변수

루트 `.env`에 다음 값을 설정합니다.

- `OPENAI_API_KEY`
- `SUPERVISOR_MODEL` (`supervisor`, `supervisor_full` 포함 시)
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (`graph`, `supervisor_full` 포함 시)
- 선택: `OPENAI_CHAT_MODEL`, `RAGAS_JUDGE_MODEL`, `HYBRID_ONTOLOGY_FILTER=off`(필터 없이 이전 방식으로 비교)

Cross-Encoder 모델은 기존 `HYBRID_RERANK_*` 설정과 로컬 캐시를 사용합니다. 모델이 동작하지 않았는지는 `per_question.csv`의 `rerank_applied`와 오류·경고로 확인할 수 있습니다.

## 결과 파일

각 실행은 `outputs/evaluation/hybrid_ragas/run_<실행 ID>/` 아래에 저장됩니다.

| 파일 | 내용 |
|---|---|
| `summary.md` | 경로별 비교표, 평균·최대 검색/답변 시간, Ragas 채점 시간, 지표 설명 |
| `summary.csv` | 경로별 집계표와 시간 |
| `per_question.csv` | 경로×문항별 정답 ID, 검색 근거, 답변, 라우트, 검증/재시도, Ragas 점수, 시간(ms) |
| `checkpoint.json` | 이어하기 데이터와 실행 설정 |
| `results/` | 문항 단위 저장 파일. 중간 종료 시 여기서부터 재사용 |
| `precomputed/` | 공유 검색 후보 |
| `judge_cache/` | Ragas 판정 응답 캐시 |

중단한 실행은 같은 설정으로 실행 폴더를 지정해 이어 갑니다.

```powershell
.\.venv\Scripts\python.exe -m src.evaluation.hybrid.ragas_eval --modes hybrid_rerank --top-k 5 --resume "outputs/evaluation/hybrid_ragas/run_<실행 ID>"
```

- `--resume`에는 실행 폴더 경로나 출력 폴더 아래의 실행 ID를 넣습니다.
- 평가셋 내용, 문항 범위, 모드, 모델, top-k가 기존 실행과 다르면 이어하기를 거부합니다.
- 문항 결과와 검색 후보는 재사용하고, Ragas 채점은 다시 실행될 수 있습니다.

## 점수 해석

- 모든 라벨이 사람 검수 전이라 점수는 **비교용 잠정치**입니다.
  - v1 문항: `draft_needs_human_review`
  - v2 새 문항: `auto_generated_needs_human_review`
- 이전 결과와 비교할 때는 `per_question.csv`에서 `question_id`가 v1(`Q…`)인 문항만 골라 [평가 기준선](../../evaluations/reports/baseline_2026-11-13/README.md)과 맞춰 보세요.
- 새 흐름의 효과는 `V2-…` 문항을 보면 됩니다.
  - 후보 필터, 기관 Graph, 기록 없음 보류가 각각 기대 동작(`expected_behavior`)대로 나오는지 확인합니다.
  - `supervisor_full`과 `supervisor`(Hybrid 고정)를 같이 돌리면 라우팅 변화의 효과를 분리할 수 있습니다.
