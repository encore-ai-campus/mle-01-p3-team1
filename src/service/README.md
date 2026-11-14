# Vector 검색 서비스와 별도 UI

`vector_search_service.py`, `vector_search_analyzer.py`, `vector_search_chroma.py`, `vector_search_rag_agent.py`는 Vector 검색과 질의 분석 및 선택적 LLM 관련성 평가를 제공합니다. Hybrid 경로는 Vector 내부 LLM 재평가를 끄고 RRF 이후 별도 Cross-Encoder를 사용합니다.

`app.py`, `ui/`, `static/`은 별도의 Streamlit 화면입니다. 이 UI의 검색·답변 흐름은 터미널 Supervisor와 통합되어 있지 않습니다. 사용자 설치 및 터미널 챗봇 실행은 [루트 README](../../README.md)를 사용하세요.


## 별도 Streamlit UI

`chatbot.py`는 자체 Chroma 검색·답변·가드레일, `kg.py`는 UI용 Neo4j 질의, `data.py`는 화면용 CSV 로딩을 담당합니다. 대시보드·지도·테마 및 스타일은 나머지 모듈에 있습니다. 이 경로는 Supervisor CLI의 Hybrid 검색 경로와 별개입니다.


## 정적 파일

`fonts/`는 별도 Streamlit 화면에서 사용하는 글꼴과 라이선스입니다. 터미널 Supervisor 실행과는 독립적입니다.


## UI 글꼴

Streamlit 화면의 IBM Plex Sans KR 글꼴과 `IBMPlexSansKR-OFL.txt` 라이선스를 보관합니다.
