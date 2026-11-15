# 평가 코드

- [hybrid](#hybrid-ragas-평가): BM25·Vector·Hybrid·Supervisor·Graph 비교와 Ragas.
- [langgraph](#neo4j-graphrag-ragas-평가): Neo4j GraphRAG와 Ragas.
- [vector_db](#vector-db-평가): Chroma 검색 순위 평가.
- `timing.py`: 질문별 소요 시간 표시 공통 함수.

평가셋은 [evaluations/datasets](../../evaluations/datasets/README.md), 실행 결과는 `outputs/evaluation/`에 있습니다. [평가 문서 색인](../../docs/evaluation/README.md)에 각 명령과 결과 해석을 모았습니다.


## Vector DB 평가

`evaluate.py`는 Chroma 검색 결과의 Hit@k·Recall·MRR을 계산합니다. LLM 답변이나 Hybrid Cross-Encoder 재정렬은 이 평가에 포함하지 않습니다. `generate_testset.py`는 초안 생성 도구입니다. 절차는 [Vector 평가 안내](../../docs/evaluation/vector-db.md)를 참고하세요.


## Hybrid Ragas 평가

`ragas_eval.py`는 선택한 BM25·Vector·RRF·Cross-Encoder·Supervisor·Graph 경로를 비교합니다. 기본 데이터는 v2 196문항 초안(`evaluations/datasets/supervisor_v2/`)입니다. `supervisor_full` 모드는 실제 CLI와 같은 자동 라우팅·후보 필터·Neo4j 연결로 평가합니다. 검색 후보와 문항 결과는 실행 폴더에 체크포인트로 저장됩니다.

```powershell
.\.venv\Scripts\python.exe -m src.evaluation.hybrid.ragas_eval --modes hybrid_rerank --top-k 5
```

시간, 출력 파일, 이어하기는 [Hybrid 평가 안내](../../docs/evaluation/hybrid-ragas.md)를 참고하세요.


## Neo4j GraphRAG Ragas 평가

`ragas_eval.py`는 Neo4j 그래프 검색·답변 경로를 평가합니다. `ragas_testset.py`는 평가셋 생성 도구입니다. 평가셋과 출력 위치는 [Neo4j 평가 안내](../../docs/evaluation/langgraph-ragas.md) 및 [평가셋 색인](../../evaluations/README.md)에 있습니다.
