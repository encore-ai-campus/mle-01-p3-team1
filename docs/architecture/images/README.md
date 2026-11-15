# 구조 이미지

현재 동작의 기준은 이미지가 아니라 [Supervisor 연결](../supervisor-integration.md)의 라우팅 우선순위입니다. 이미지는 그 내용을 한눈에 보기 위한 요약도입니다.

| 이미지 | 상태 | 내용 |
|---|---|---|
| [supervisor-hybrid-flow-clarified.png](supervisor-hybrid-flow-clarified.png) | **2026-11-14 기준으로 갱신** | 입력 가드레일 → 경로 선택(4가지) → Hybrid 검색(0단계 온톨로지 후보 필터, Vector·BM25, RRF, 이름 보장, Cross-Encoder) 또는 Graph → 출처 연결 → 답변 → 검증(재시도·보류) → 출력 가드레일. 주황색이 이번에 추가된 부분 |
| [supervisor-optional-ui-flow.png](supervisor-optional-ui-flow.png) | 유효 | Supervisor의 직접 Vector·Graph 연결은 선택 사항이고, Streamlit UI는 별도 경로임을 보여 줍니다. UI 경로는 이번 작업에서 수정하지 않았습니다. |
| [02-streamlit-chatbot-flow.png](02-streamlit-chatbot-flow.png) | 유효 (UI 전용) | 별도 Streamlit 챗봇 흐름. UI의 출력 LLM 검사는 스트리밍 후 실행됩니다. 후보 필터와 이름 보장은 아직 이 경로에 적용되지 않습니다. |
| [archive/](archive/) | 보관 | 갱신 전(2026-11-13) 흐름도. 지역 필터만 있고 후보 필터·준비된 쿼리 라우팅·Graph 실패 시 Hybrid 전환이 없는 당시 모습 |

## 갱신 방법

- Mermaid 원본은 [../supervisor-hybrid-flow-clarified.mmd](../supervisor-hybrid-flow-clarified.mmd)입니다.
- PNG는 [draw_supervisor_flow.py](draw_supervisor_flow.py)(matplotlib만 사용)로 그립니다. 같은 파일이 나오는 것을 확인했습니다.
- **PNG는 `.mmd`에서 렌더링한 것이 아닙니다.** 같은 구조를 두 곳에 적었으므로 흐름이 바뀌면 둘 다 고쳐야 합니다.

```powershell
.\.venv\Scripts\python.exe docs/architecture/images/draw_supervisor_flow.py docs/architecture/images/supervisor-hybrid-flow-clarified.png
```

## 생략한 것

요약도라서 다음은 그리지 않았습니다.
- 직접 Vector 선택 경로, 선택적 LLM 질문 분석, 시간 측정
- Cross-Encoder 오류 시 RRF 폴백
- 기관 질문의 기준 시설(anchor) 근거와 `structured_match` 근거 전달

`build_supervisor()`를 직접 호출하는 경우 가드레일은 별도로 주입해야 합니다. 실제 실행 조건은 [폴더 구조](../folder-structure.md)와 [Supervisor 연결](../supervisor-integration.md)이 기준이고, 지역·주제 질문을 Hybrid로 보내는 이유는 [지역·주제 검색 설계](../../decisions/region-theme-routing.md)에 있습니다.
