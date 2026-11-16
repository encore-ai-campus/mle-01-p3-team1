# 노트북

`vector_db/`에는 Chroma 데이터 구축과 확인용 노트북이 있습니다. 노트북은 DB 및 CSV에 쓰기 작업을 할 수 있으므로 진행 중인 평가의 DB와 겹치지 않게 주의하세요. 자세한 안내는 아래 Vector DB 구축 안내을 참고하세요.


## Vector DB 구축 노트북

`vector_db_builder.ipynb`는 `data/processed/museum_final_738.csv`와 OpenAI 임베딩을 사용해 Chroma 컬렉션을 구축합니다. `vector_db_builder_test.ipynb`는 별도 확인용 노트북입니다. 두 노트북은 동일 파일이 아닙니다.

```powershell
uv run jupyter lab notebooks/vector_db/vector_db_builder.ipynb
```

실행 전 `.env`의 `OPENAI_API_KEY`, 노트북의 DB 경로·컬렉션·쓰기 셀을 확인하세요. 임베딩 API 비용이 발생하며, 기존 Chroma DB를 쓰는 평가가 끝나기 전에는 같은 경로에 구축하지 마세요. 완성된 Chroma DB(738건)는 저장소에 포함되어 있어 새로 클론해도 바로 쓸 수 있습니다. 노트북 없이 명령 한 줄로 다시 만들려면 `uv run python scripts/build_vector_db.py --force`를 사용합니다(약 10초, 같은 적재 방식).
