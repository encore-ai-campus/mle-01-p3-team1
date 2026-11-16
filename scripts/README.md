# 스크립트

## 벡터 DB 재구축

`build_vector_db.py`는 `data/processed/museum_final_738.csv`를 OpenAI `text-embedding-3-small`로 임베딩해 Chroma 컬렉션 `museum_documents`를 다시 만듭니다. [벡터 DB 구축 노트북](../notebooks/README.md)과 같은 적재 방식이며, 738건에 약 10초 걸립니다.

```bash
uv run python scripts/build_vector_db.py --force             # 기존 컬렉션을 지우고 다시 구축
uv run python scripts/build_vector_db.py --db-path tmp/chroma # 다른 경로에 구축
```

`--force` 없이 실행하면 컬렉션이 이미 있을 때 덮어쓰지 않고 멈춥니다. 평가나 챗봇이 DB를 쓰는 중에는 `--force`로 덮어쓰지 마세요.

## 설치 스크립트

`setup_hybrid.ps1`(Windows)과 `setup_hybrid.sh`(Linux/macOS)는 `uv sync`로 선언된 패키지를 설치한 다음 로컬 Cross-Encoder 모델을 준비합니다. 처음 모델을 받는 데 시간과 저장 공간이 필요합니다.

```powershell
.\scripts\setup_hybrid.ps1
```

모델 준비 상태만 확인하려면 프로젝트 루트에서 `uv run --no-sync python -m src.hybrid.prepare_models --check-only`를 실행합니다. 패키지는 이미 `pyproject.toml`에 선언되어 있으므로 별도 `uv add`가 필요하지 않습니다. 전체 설치·챗봇 실행은 [루트 README](../README.md), 검색 구조는 [Hybrid README](../src/hybrid/README.md)를 참고하세요. 실행 중인 평가와 같은 가상환경에서 설치나 동기화를 하지 마세요.
