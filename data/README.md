# 데이터

- `raw/`: 수집한 원본 CSV.
- `processed/`: 정제 CSV. `museum_final_738.csv`는 Supervisor 원문 출처 연결과 Neo4j 입력, `museum_final_1027.csv`는 별도 Streamlit 화면의 입력입니다. 서로 다른 데이터이므로 합치지 않습니다.
- [`vector_db/`](vector_db/README.md): 로컬 Chroma DB. DB 전체 폴더가 필요하며 실행 중인 DB를 이동하거나 덮어쓰지 마세요.

평가셋은 [evaluations/datasets](../evaluations/datasets/README.md), 평가 결과는 `outputs/evaluation/`에 따로 있습니다.


## 원본 데이터

수집한 원본 CSV를 보관합니다. 정제본과 실행용 DB는 각각 `../processed/`와 `../vector_db/`에 있습니다. 원본 데이터의 열·출처를 확인한 뒤 가공하세요.


## 정제 데이터

- `museum_final_738.csv`: Neo4j 적재와 Supervisor 원문 출처 연결의 기준.
- `museum_final_1027.csv`: 별도 Streamlit UI 입력.
- `museum_chroma_ready.csv`: Vector DB 구축 과정에서 만든 중간 데이터.

파일마다 용도와 행 수가 다릅니다. 평가 실행 중 원본 파일을 바꾸지 마세요.
