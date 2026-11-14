# Vector DB 검색 평가

- 컬렉션: museum_documents
- 질의 임베딩: text-embedding-3-small
- 답변 가능 문항: 24
- 근거 부족 문항: 6 (순위 지표 제외)

| 지표 | 평균 |
|---|---:|
| Hit@1 | 0.708 |
| Hit@3 | 0.792 |
| Hit@5 | 0.792 |
| Recall@5 | 0.792 |
| MRR@10 | 0.755 |

라벨 검수 상태는 summary.json에서 확인하세요. 이 평가는 검색 순위만 측정하며 LLM 답변 품질은 측정하지 않습니다.
