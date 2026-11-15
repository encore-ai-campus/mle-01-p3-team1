# LangGraph Ragas 평가

- 질문 수: 10 (답변 가능 10, 근거 부족 0)
- Judge 모델: gpt-6-luna
- GraphRAG 생성 모델: gpt-6-luna
- 검색 top-k: 5
- 라벨 상태: `{"draft_needs_human_review": 10}`
- 전체 evidence presence accuracy: 1.000
- 정답 박물관 ID recall: 0.900

| Ragas 지표 | 평균 |
|---|---:|
| faithfulness | 0.978 |
| context_recall | 0.850 |
| context_precision_with_reference | 0.950 |
| factual_correctness | N/A |

Ragas 점수는 답변 가능 문항에 대해서만 계산했습니다. `evidence_presence_accuracy`는 답변 가능/불가능 정답 라벨과 검색 결과 유무를 비교합니다.
`gold_museum_id_recall`은 정답 박물관 ID 중 검색 결과에 포함된 비율이며, 정답 후보를 찾았는지 Ragas 점수와 별도로 확인합니다.
라벨이 `draft_needs_human_review`인 문항은 검수 전 잠정 점수입니다.
