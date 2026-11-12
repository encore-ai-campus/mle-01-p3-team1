# 박물관 Vector DB 평가셋

평가 코드는 `src/evaluation/vector_db/`, 평가 CSV는 `evaluations/datasets/vector_db/`에 있습니다.

중요: 이전에 있던 CSV는 Git에 저장되지 않아 원본 그대로 복구할 수 없었습니다. 아래 30문항은 현재 원문 데이터에서 근거를 다시 연결해 만든 대체 초안이며, 기존 평가셋과 동일한 데이터가 아닙니다.

## 파일

- `evaluations/datasets/vector_db/VectorDB_평가셋_30문항.csv`: 답변 가능 24문항, 근거 부족 6문항
- `src/evaluation/vector_db/generate_testset.py`: 원문 CSV에서 근거와 원본 문서 ID를 연결해 초안 CSV 생성
- `src/evaluation/vector_db/evaluate.py`: 현재 Chroma 컬렉션을 검색하고 순위 지표 계산
- `docs/evaluation/vector_db.md`: 실행 및 라벨 검수 안내

질문 유형은 direct 8개, semantic 12개, geo_semantic 4개, unanswerable 6개입니다. 답변 가능 문항의 evidence_quote는 원문 text 안에 존재하는지 생성 과정에서 확인했고, text_spans_json을 이용해 원본 문서 ID를 연결했습니다.

## 처음 할 일: 초안 라벨 검수

CSV의 모든 행은 draft_needs_human_review 상태입니다. 질문에 맞는 박물관이 모두 정답으로 포함됐는지, evidence_quote가 질문에 답을 주는지 사람이 확인한 뒤 label_status를 human_verified로 변경하세요. 근거 부족 6문항은 해당 정보가 코퍼스에 실제로 없는지도 검토하세요.

## 초안 재생성

생성기는 `data/processed/museum_final_738.csv`를 사용합니다. 저장소 루트에서 실행합니다.

~~~powershell
uv run python -m src.evaluation.vector_db.generate_testset
~~~

CSV가 이미 있으면 기본 실행은 덮어쓰지 않고 종료합니다. 검수 내용을 버리고 새 초안으로 교체할 때만 --force를 지정하세요.

## 준비 확인과 평가 실행

PowerShell에서:

~~~powershell
uv run python -m src.evaluation.vector_db.evaluate --check-only
~~~

준비 확인은 로컬 DB, 평가 CSV, 정답 시설 ID를 검사하며 임베딩 API를 호출하지 않습니다. 현재 DB는 프로젝트 루트의 data/vector_db/museum_chroma에 있고 컬렉션 이름은 museum_documents입니다.

라벨 검수를 마친 뒤 전체 평가:

~~~powershell
uv run python -m src.evaluation.vector_db.evaluate
~~~

전체 평가는 질문 임베딩을 위해 OpenAI API를 호출합니다. 프로젝트 루트의 `.env` 또는 프로세스 환경변수에 `OPENAI_API_KEY`가 있어야 합니다. 결과는 `outputs/evaluation/vector_db/`에 저장됩니다.

## 지표와 범위

Hit@1/3/5, Recall@5, MRR@10은 answerable=yes 문항만으로 계산합니다. answerable=no 문항은 검색 결과를 기록하지만 순위 점수 분모에는 넣지 않습니다. 검색기는 유사 문서를 항상 반환하므로, 근거 부족 질문에서 답변을 보류하는 능력은 별도 정책과 지표로 평가해야 합니다.

이 평가는 검색 결과의 순위만 측정합니다. LangGraph가 생성한 답변의 사실성, 근거 충실도, 환각 여부는 측정하지 않습니다.
