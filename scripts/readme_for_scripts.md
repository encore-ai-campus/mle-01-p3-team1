# 모델 준비 및 다운로드 방지 패치

**기존 하이브리드 검색 코드를 유지한 전체 패키지**입니다. `src/hybrid/`은 프로젝트 루트의 동일 경로에 복사하고, `scripts/setup_hybrid.ps1`도 프로젝트의 `scripts/` 폴더에 복사하세요.

`uv sync` 자체는 모델 다운로드를 실행하지 않습니다. 아래 설치 스크립트로 한 번에 준비하세요.

```powershell
# 처음 pyproject.toml에 의존성이 없다면 1회
uv add rank-bm25 kiwipiepy sentence-transformers huggingface-hub

# 평소 환경 구성: uv sync + 모델 준비 (동일 로컬 모델이면 즉시 통과)
.\scripts\setup_hybrid.ps1

# 검색 시 다운로드하지 않고 이미 준비된 로컬 모델 로딩
uv run python -m src.hybrid.hybrid_rag_agent "역사 박물관"
```

원래 설치돼 있던 Python 패키지는 `uv add`를 중복 실행할 필요가 없습니다. **프로젝트 `pyproject.toml`/`uv.lock`은 제공받지 않았으므로 변경하지 않았습니다.** 전반적인 설치 방식, 주의사항은 `src/hybrid/README.md`를 참고하세요.
