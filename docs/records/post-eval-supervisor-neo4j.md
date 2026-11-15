# 평가 후 Supervisor–Neo4j 확인 메모

## 현재 상태

- Ragas 평가는 사용자의 요청으로 중단했으며, 부분 체크포인트는 보존했다.
- 정확도는 낮추지 않는다. 검색 분석과 Supervisor 답변 검증을 끄지 않는다.
- `src/agent/supervisor/run.py`의 `--with-neo4j`와 구조화 속성의 Graph 라우팅 지침을 추가했다. 여주미술관·만해기념관 요금 질문을 실제 Supervisor Graph 경로로 실행해 `answered`를 확인했다.

## 요금 질문이 보류된 이유

여주미술관·만해기념관의 위치와 전시 내용은 E1·E2 설명문에서 확인됐지만, 성인·청소년·어린이 요금은 검색 결과의 별도 메타데이터에만 있었다. Supervisor 검증기는 인용된 설명문이 요금 값을 뒷받침하지 않는다고 판단해 답변을 보류했다.

`--route hybrid`는 BM25·Chroma Hybrid 경로를 고정하므로 Neo4j를 조회하지 않는다. 이전 CLI는 Hybrid만 연결했고, Neo4j retriever는 Python 연결 함수에만 선택적으로 지원됐다. 따라서 `auto`도 Neo4j가 연결되지 않은 상태에서는 Hybrid로 대체될 수 있었다.

`src/agent/supervisor/nodes.py`는 Graph 시도 후 검증에 실패하면 Graph를 유지해 재시도하도록 변경했다. 기관명이 명시된 이름 검색에서는 요금 관련 일반 단어가 `$terms`에 섞이지 않도록 처리했다.

## 중단한 Ragas 실행

- 실행 ID: `20261113_043143_468077Z`
- 실행 명령: 150문항, 기본 6개 경로, `workers=8`, `ragas-workers=16`
- 평가 프로세스 두 개를 종료했다. 종료 시 `precomputed/`에 검색 후보 파일 53개가 저장되어 있었다.
- `checkpoint.json`에는 Ragas 점수/상태가 비어 있고 per-mode 결과 파일도 없어, 확인 가능한 체크포인트 기준으로는 Ragas 채점이 시작되기 전 중단됐다.
- 출력 폴더와 부분 캐시는 삭제하지 않았다.

## 평가 종료 후 확인할 것

1. 여러 종류의 질문을 `--route auto`로 실행해 구조화 속성 질문이 Graph로, 일반 설명 검색이 적절한 검색 경로로 가는지 확인한다.
2. 요금 값이 반환되지 않거나 출처가 연결되지 않으면 값을 추측하거나 검증을 우회하지 말고 Cypher 결과와 데이터 출처 연결을 먼저 점검한다. 앞서 확인한 두 박물관 결과에는 문서 ID는 있었으나 출처 URL은 비어 있었다.

평가 종료 후 사용할 Graph 경로 명령:

```powershell
.\.venv\Scripts\python.exe -m src.agent.supervisor.run --team-hybrid --with-neo4j --interactive --route graph --top-k 5
```
