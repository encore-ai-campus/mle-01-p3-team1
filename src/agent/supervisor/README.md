# Supervisor

`run.py`는 터미널 실행, `connect.py`는 Hybrid·선택적 Vector/Neo4j·가드레일 연결, `graph.py`와 `nodes.py`는 상태 흐름과 검증·재시도, `llm.py`는 LLM 호출, `adapters.py`와 `provenance.py`는 검색 결과와 CSV 원문 출처 연결을 담당합니다.

```powershell
.\.venv\Scripts\python.exe -m src.agent.supervisor.run --team-hybrid --interactive --timings --model gpt-6-luna
```

Neo4j를 연결하려면 `--with-neo4j`를 추가하고 `.env`에 접속 정보를 설정하세요. 기본 연결은 Hybrid입니다. Streamlit UI는 이 Supervisor를 호출하는 경로가 아닙니다. 중간 노드 스트림에는 검사 전 답변 초안이 나갈 수 있으므로 사용자에게는 `invoke()` 최종 결과를 표시합니다. 설정과 근거 검증은 [통합 문서](../../../docs/architecture/supervisor-integration.md)를 참고하세요.

요금 질문에서는 Neo4j의 `adult_fee=0`을 데이터에 기록된 **성인 기본 관람료 무료**로 해석합니다. `BASE_FEE_ZERO_CHECK_EXCEPTIONS` 상태여도 이 기준으로 답변할 수 있습니다. 현재 요금, 특별전 요금, 다른 연령대 요금까지 무료라고 단정하지는 않습니다. `서울역사박물관과 같은 서울특별시에 있으면서 종로구가 아닌 무료 미술관은?` 형태는 시도·제외 구·미술관 이름·0원 조건을 준비된 Cypher로 함께 조회합니다.

`인천광역시립박물관과 같은 인천광역시에 있지만 연수구 밖에 있는 미술관은?`처럼 같은 시도와 제외할 시군구를 지정한 질문도 준비된 Cypher로 조회합니다. 비교 대상 박물관의 위치는 별도 앵커 근거로 반환해 후보 미술관과 같은 시도인지 검증합니다.

라우터에는 실제 연결된 검색 경로가 전달됩니다. Hybrid는 Vector와 BM25 검색이며 Neo4j 검색을 포함하지 않습니다. 지역·요금 등 구조화된 근거가 부족할 때 Neo4j가 연결되어 있으면 자동 경로의 재시도에서 Graph를 선택합니다. 명시적으로 지정한 경로는 유지합니다. 실행 결과의 `route`와 `reason`에서 선택 이유를 확인할 수 있습니다.

`--timings`는 전체 요청과 입력·출력 가드레일, 경로 선택, 검색, 답변 생성, 검증 시간을 초 단위로 표시합니다. Graph 검색은 준비된 쿼리 확인, Cypher 생성 및 Neo4j 조회 시간과 호출 횟수를 보여줍니다. Hybrid 검색은 단계별 시간과 Cross-Encoder 모델 로딩·추론 시간을 보여줍니다. 재시도는 각각 별도 표시합니다. 검색의 세부 시간은 검색 시간에 포함되며 Vector/BM25 병렬 처리 시간은 서로 겹칠 수 있습니다. 모델 로딩 0초는 같은 프로세스에서 이미 로드한 경우입니다.

한 질문의 전체 결과와 시간 기록을 JSON으로 남기려면 `--interactive` 없이 `--question "질문" --out outputs/supervisor/timing.json --timings`를 사용합니다. 총 시간은 `timing_request_ms`, 각 노드와 검색 세부 시간은 `trace`에 밀리초로 저장됩니다. 실행마다 동일 경로를 쓰면 덮어씁니다.
