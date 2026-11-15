# 노트북

`vector_db/`에는 Chroma 데이터 구축과 확인용 노트북이 있습니다. 노트북은 DB 및 CSV에 쓰기 작업을 할 수 있으므로 진행 중인 평가의 DB와 겹치지 않게 주의하세요. 자세한 안내는 아래 Vector DB 구축 안내을 참고하세요.


## Vector DB 구축 노트북

`vector_db_builder.ipynb`는 `data/processed/museum_final_738.csv`와 OpenAI 임베딩을 사용해 Chroma 컬렉션을 구축합니다. `vector_db_builder_test.ipynb`는 별도 확인용 노트북입니다. 두 노트북은 동일 파일이 아닙니다.

```powershell
uv run jupyter lab notebooks/vector_db/vector_db_builder.ipynb
```

실행 전 `.env`의 `OPENAI_API_KEY`, 노트북의 DB 경로·컬렉션·쓰기 셀을 확인하세요. 임베딩 API 비용이 발생하며, 기존 Chroma DB를 쓰는 평가가 끝나기 전에는 같은 경로에 구축하지 마세요. 새 클론에는 Git에서 제외된 Chroma 인덱스 파일이 없을 수 있으므로 완전한 폴더를 팀에서 받거나 새 환경에서 구축해야 합니다.
