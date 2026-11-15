# 평가셋 v1 (2026-11-13, 보관)

2026-11-14 흐름 변경 이전에 쓰던 LangGraph 평가셋입니다. **내용은 바꾸지 않았습니다.**

| 파일 | 문항 | 당시 용도 | sha256 앞 16자리 |
|---|---:|---|---|
| `langgraph/LangGraph_Ragas_150_draft.csv` | 150 (답변 가능 144, 불가 6) | Hybrid·Supervisor·GraphRAG 비교 기본값 | `3ab95ff0acadf714` |
| `langgraph/LangGraph_Ragas_평가셋_30문항.csv` | 30 | 소규모 스모크 평가, `ragas_testset` 시드 | `e202cccf20921638` |

- 이 평가셋으로 낸 결과는 [baseline_2026-11-13](../../../reports/baseline_2026-11-13/README.md)에 있습니다.
- 150문항은 [v2](../../supervisor_v2/README.md)에 같은 `question_id`로 그대로 들어 있습니다.
- `src.evaluation.langgraph.ragas_testset`은 여전히 30문항 파일을 기본 시드로 씁니다.
- 당시 폴더 안내문은 [langgraph/README.md](langgraph/README.md)에 원문 그대로 있습니다.
