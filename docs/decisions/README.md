# 기술 결정

현재 구현 구조는 [architecture](../architecture/README.md), 문제 해결과 측정 결과는 [records](../records/README.md)에 둡니다.

| 문서 | 선택 이유 |
|---|---|
| [Hybrid 설계](2026-11-13-museum-bm25-hybrid-design.md) | BM25·Vector 결합과 당시 대안 검토 |
| [후보 필터](ontology-filter-routing.md) | 기록된 구조 조건으로 후보를 제한하는 이유와 한계 |
| [지역·주제 라우팅](region-theme-routing.md) | 지역 필터와 의미 검색의 역할 |
| [지역 별칭](2026-11-13-chroma-sido-alias-normalization-design.md) | 저장 데이터 수정 없이 표기를 함께 처리하는 선택 |
| [병렬 평가](2026-11-12-langgraph-ragas-parallel-collection-design.md) | 스레드별 앱과 결과 순서 보존 |

날짜가 붙은 설계는 당시 기록입니다. 현재 구현과 다른 제안이 남아 있을 수 있으므로 현행 구조 설명과 구분합니다. 새 결정에는 문제, 대안, 선택 이유, 적용 범위, 코드·테스트, 실험 근거, 한계를 남깁니다.
